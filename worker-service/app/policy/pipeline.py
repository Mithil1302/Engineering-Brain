"""
pipeline.py — Policy pipeline orchestrator.

PolicyPipeline owns the Kafka consumer/producer lifecycle and the core
policy evaluation loop.  All other concerns are delegated:

  schema.py        — DB DDL (ensure_schema)
  kafka_emitter.py — Kafka produce helpers (KafkaEmitter)
  request_builder.py — payload → PolicyEvaluationRequest
  retry_worker.py  — emit-retry job orchestration (EmitRetryWorker)
  event_store.py   — DB persistence (EventStore)
  reporting_store.py — DB read/reporting queries (ReportingStore)
  governance_store.py — policy template / waiver queries
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg2
from kafka import KafkaConsumer, KafkaProducer

from .engine import evaluate_policies_with_meta, resolve_policy_pack, summary_status
from .models import PolicyConfig
from .merge_gate import build_merge_gate_decision
from .doc_refresh import build_doc_refresh_plan
from .doc_rewrite import build_doc_rewrite_bundle
from .health_score import build_knowledge_health_score
from .patches import build_suggested_patches
from .renderer import assemble_response
from .governance_store import PolicyGovernanceStore
from .event_store import EventStore
from .reporting_store import ReportingStore
from .schema import ensure_schema
from .kafka_emitter import KafkaEmitter
from .request_builder import build_request
from .retry_worker import EmitRetryWorker


class PolicyPipeline:
    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, logger, impact_analyzer=None):
        self.log = logger
        self.impact_analyzer = impact_analyzer
        self.enabled = os.getenv("POLICY_PIPELINE_ENABLED", "true").lower() == "true"

        # Kafka config
        self.kafka_brokers   = [b.strip() for b in os.getenv("KAFKA_BROKERS", "kafka:9092").split(",") if b.strip()]
        self.consumer_topic  = os.getenv("POLICY_INPUT_TOPIC",       "repo.events")
        self.output_topic    = os.getenv("POLICY_OUTPUT_TOPIC",       "pr.checks")
        self.docs_refresh_topic = os.getenv("POLICY_DOC_REFRESH_TOPIC", "docs.refresh")
        self.docs_rewrite_topic = os.getenv("POLICY_DOC_REWRITE_TOPIC", "docs.rewrite")
        self.consumer_group  = os.getenv("POLICY_CONSUMER_GROUP",    "worker-policy-checks-v1")

        # Policy config
        self.rule_set              = os.getenv("POLICY_RULE_SET",              "rules-v1")
        self.default_service_id    = os.getenv("POLICY_DEFAULT_SERVICE_ID",    "unknown-service")
        self.doc_refresh_enabled   = os.getenv("POLICY_DOC_REFRESH_ENABLED",   "true").lower() == "true"
        self.doc_rewrite_enabled   = os.getenv("POLICY_DOC_REWRITE_ENABLED",   "true").lower() == "true"
        self.doc_rewrite_min_health_score = float(os.getenv("POLICY_DOC_REWRITE_MIN_HEALTH_SCORE", "20.0"))
        self.fail_blocks_merge     = os.getenv("POLICY_FAIL_BLOCKS_MERGE",     "true").lower()  == "true"
        self.warn_blocks_merge     = os.getenv("POLICY_WARN_BLOCKS_MERGE",     "false").lower() == "true"
        self.health_weight_policy  = float(os.getenv("POLICY_HEALTH_WEIGHT_POLICY",    "0.45"))
        self.health_weight_docs    = float(os.getenv("POLICY_HEALTH_WEIGHT_DOCS",      "0.35"))
        self.health_weight_ownership = float(os.getenv("POLICY_HEALTH_WEIGHT_OWNERSHIP", "0.20"))
        self.policy_admin_token    = os.getenv("POLICY_ADMIN_TOKEN", "").strip()

        # Emit retry config
        self.emit_retry_enabled        = os.getenv("POLICY_EMIT_RETRY_ENABLED",      "true").lower() == "true"
        self.emit_retry_batch_size     = int(os.getenv("POLICY_EMIT_RETRY_BATCH_SIZE",    "25"))
        self.emit_retry_max_attempts   = int(os.getenv("POLICY_EMIT_RETRY_MAX_ATTEMPTS",  "5"))
        self.emit_retry_backoff_seconds = int(os.getenv("POLICY_EMIT_RETRY_BACKOFF_SECONDS", "10"))

        # Postgres config
        self.pg_cfg = {
            "host":     os.getenv("POSTGRES_HOST",     "postgres"),
            "port":     int(os.getenv("POSTGRES_PORT", "5432")),
            "user":     os.getenv("POSTGRES_USER",     "brain"),
            "password": os.getenv("POSTGRES_PASSWORD", "brain"),
            "dbname":   os.getenv("POSTGRES_DB",       "brain"),
        }

        # Initialize time travel system
        from ..simulation.time_travel import TemporalGraphStore
        self.time_travel = TemporalGraphStore(pg_cfg=self.pg_cfg)

        # Threading / Kafka handles (set during _run_loop)
        self.stop_event = threading.Event()
        self.thread:   Optional[threading.Thread] = None
        self.consumer: Optional[KafkaConsumer]    = None
        self.producer: Optional[KafkaProducer]    = None

        # Runtime state counters
        self.state: Dict[str, Any] = {
            "enabled": self.enabled,
            "running": False,
            "processed_events": 0,
            "emitted_checks": 0,
            "deduped_checks": 0,
            "replay_skipped_events": 0,
            "emitted_doc_refresh": 0,
            "emitted_doc_rewrite": 0,
            "emitted_health_snapshots": 0,
            "emit_failures": 0,
            "queued_emit_retries": 0,
            "processed_retry_jobs": 0,
            "retry_emit_success": 0,
            "retry_emit_failures": 0,
            "dead_lettered_retry_jobs": 0,
            "skipped_events": 0,
            "last_error": None,
            "last_processed_at": None,
        }
        self._last_backlog_count: Optional[int]      = None
        self._last_backlog_sampled_at: Optional[datetime] = None

        # Validate rule set early to catch misconfiguration at startup
        resolve_policy_pack(self.rule_set)

        # Instantiate delegated modules
        self.event_store = EventStore(
            db_conn_func=self._db_conn,
            rule_set=self.rule_set,
            ensure_schema=lambda: ensure_schema(self._db_conn),
            emit_retry_idempotency_key_fn=self._emit_retry_idempotency_key,
        )
        self.reporting_store = ReportingStore(
            db_conn_func=self._db_conn,
            ensure_schema=lambda: ensure_schema(self._db_conn),
        )
        self.governance_store = PolicyGovernanceStore(
            db_conn_factory=self._db_conn,
            ensure_schema=lambda: ensure_schema(self._db_conn),
            resolve_policy_pack_fn=resolve_policy_pack,
        )
        # KafkaEmitter and EmitRetryWorker are wired after Kafka starts (see _run_loop)
        self.emitter: Optional[KafkaEmitter] = None
        self.retry_worker: Optional[EmitRetryWorker] = None

    # ------------------------------------------------------------------
    # DB connection
    # ------------------------------------------------------------------

    def _db_conn(self):
        return psycopg2.connect(**self.pg_cfg)

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def _log_error(self, message: str, err: Exception) -> None:
        try:
            self.log.error("%s: %s", message, str(err))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # State counter helper (used as callback in EmitRetryWorker)
    # ------------------------------------------------------------------

    def _inc_state(self, key: str, delta: int = 1) -> None:
        self.state[key] = self.state.get(key, 0) + delta

    # ------------------------------------------------------------------
    # Idempotency Key
    # ------------------------------------------------------------------

    def _emit_retry_idempotency_key(self, emit_type: str, base_idempotency_key: str, repo: str, pr_number: int, correlation_id: Optional[str] = None) -> str:
        key_parts = [
            "emit-retry",
            emit_type,
            repo,
            str(pr_number),
            base_idempotency_key
        ]
        if correlation_id:
            key_parts.append(correlation_id)
        return ":".join(key_parts)
    
    # ------------------------------------------------------------------
    # Governance / runtime controls
    # ------------------------------------------------------------------

    def _resolve_effective_runtime_controls(
        self,
        payload: Dict[str, Any],
        request,
    ) -> Dict[str, Any]:
        policy_ctx = payload.get("policy_context") or {}
        team = payload.get("team") or policy_ctx.get("team")
        org = payload.get("org") or policy_ctx.get("org") or (
            request.repo.split("/", 1)[0] if "/" in request.repo else None
        )
        template = self.governance_store.resolve_effective_policy_template(
            repo=request.repo, team=team, org=org
        )

        selected_rule_set = self.rule_set
        fail_blocks_merge = self.fail_blocks_merge
        warn_blocks_merge = self.warn_blocks_merge
        no_docs_no_merge  = False
        merged_rules: Dict[str, Any] = {}

        if template:
            merged_rules.update(template.get("rules") or {})
            if template.get("rule_pack"):
                selected_rule_set = str(template["rule_pack"])
            fail_blocks_merge = bool(template.get("fail_blocks_merge", fail_blocks_merge))
            warn_blocks_merge = bool(template.get("warn_blocks_merge", warn_blocks_merge))
            no_docs_no_merge  = bool(template.get("no_docs_no_merge", False))

        if request.config and request.config.rules:
            merged_rules.update({k: v.model_dump() for k, v in request.config.rules.items()})
        if request.config and request.config.rule_pack:
            selected_rule_set = request.config.rule_pack

        request.config = PolicyConfig.model_validate(
            {"rule_pack": selected_rule_set, "rules": merged_rules}
        )

        return {
            "selected_rule_set": selected_rule_set,
            "fail_blocks_merge": fail_blocks_merge,
            "warn_blocks_merge": warn_blocks_merge,
            "no_docs_no_merge":  no_docs_no_merge,
            "applied_template":  template,
            "team": team,
            "org":  org,
        }

    # ------------------------------------------------------------------
    # Fingerprinting / dedup helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _stable_payload_hash(payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _event_dedup_key(self, payload, request, selected_rule_set: str) -> str:
        event_idempotency = payload.get("idempotency_key") or self._stable_payload_hash(payload)
        return f"policy:{request.repo}:{request.pr_number}:{selected_rule_set}:{event_idempotency}"

    @staticmethod
    def _fingerprint(response_payload: Dict[str, Any]) -> str:
        normalized = [
            {
                "rule_id":         f.get("rule_id"),
                "severity":        f.get("severity"),
                "status":          f.get("status"),
                "title":           f.get("title"),
                "description":     f.get("description"),
                "entity_refs":     f.get("entity_refs", []),
                "evidence":        f.get("evidence", []),
                "suggested_action": f.get("suggested_action"),
            }
            for f in response_payload.get("findings", [])
        ]
        raw = json.dumps(
            {
                "summary_status":   response_payload.get("summary_status"),
                "markdown_comment": response_payload.get("markdown_comment"),
                "findings":         normalized,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Core message handler
    # ------------------------------------------------------------------

    def _is_policy_event(self, payload: Dict[str, Any]) -> bool:
        return payload.get("event_type") in {"pull_request", "spec", "schema", "doc"}

    def _handle_message(
        self,
        payload: Dict[str, Any],
        *,
        source_topic: Optional[str] = None,
        source_partition: Optional[int] = None,
        source_offset: Optional[str] = None,
    ) -> None:
        if not self._is_policy_event(payload):
            self.state["skipped_events"] += 1
            return

        request = build_request(payload, self.default_service_id)
        if request is None or request.pr_number is None:
            self.state["skipped_events"] += 1
            return

        controls = self._resolve_effective_runtime_controls(payload, request)
        selected_rule_set = controls["selected_rule_set"]
        dedup_key = self._event_dedup_key(payload, request, selected_rule_set)

        # Dedup / persist event
        with self._db_conn() as conn:
            conn.autocommit = False
            inserted = self.event_store._register_processed_event(
                conn,
                event_key=dedup_key,
                source_topic=source_topic or self.consumer_topic,
                source_partition=int(source_partition) if source_partition is not None else -1,
                source_offset=source_offset or "unknown",
                correlation_id=payload.get("correlation_id"),
                payload=payload,
            )
            if not inserted:
                conn.rollback()
                self.state["deduped_checks"] += 1
                self.state["replay_skipped_events"] += 1
                return
            conn.commit()

        # Policy evaluation
        findings, eval_meta = evaluate_policies_with_meta(request, rule_set=selected_rule_set)
        patches     = build_suggested_patches(findings)
        eval_status = summary_status(findings)
        merge_gate  = build_merge_gate_decision(
            findings,
            rule_set=selected_rule_set,
            fail_blocks_merge=bool(controls["fail_blocks_merge"]),
            warn_blocks_merge=bool(controls["warn_blocks_merge"]),
        )

        # Apply active waiver
        active_waiver = self.get_active_waiver(
            repo=request.repo, pr_number=request.pr_number, rule_set=selected_rule_set
        )
        if active_waiver and merge_gate.get("decision") == "block":
            merge_gate["decision"] = "allow_with_waiver"
            merge_gate["waiver"] = {
                "waiver_id":     active_waiver.get("id"),
                "requested_by":  active_waiver.get("requested_by"),
                "requested_role": active_waiver.get("requested_role"),
                "decided_by":    active_waiver.get("decided_by"),
                "decided_role":  active_waiver.get("decided_role"),
                "expires_at":    active_waiver.get("expires_at"),
            }
            reasons = list(merge_gate.get("reasons") or [])
            reasons.append("Approved waiver in effect; merge gate overridden.")
            merge_gate["reasons"] = reasons

        doc_refresh_plan = build_doc_refresh_plan(
            request=request, findings=findings,
            suggested_patches=patches, merge_gate=merge_gate, action="pending",
        )

        # no-docs-no-merge enforcement
        if bool(controls.get("no_docs_no_merge")) and int(doc_refresh_plan.get("doc_finding_count") or 0) > 0:
            merge_gate["decision"] = "block"
            blocking = set(merge_gate.get("blocking_rule_ids") or [])
            blocking.add("NO_DOCS_NO_MERGE")
            merge_gate["blocking_rule_ids"] = sorted(blocking)
            reasons = list(merge_gate.get("reasons") or [])
            reasons.append("Template enforces no-docs-no-merge; documentation drift must be resolved.")
            merge_gate["reasons"] = reasons

        # Enforce branch protection on GitHub
        try:
            from .branch_protection import BranchProtectionEnforcer
            enforcer = BranchProtectionEnforcer()
            bp_result = enforcer.enforce_merge_block(
                repo=request.repo,
                gate_decision=merge_gate,
                branch="main"
            )
            merge_gate["branch_protection_result"] = bp_result
        except Exception as exc:
            self._log_error("branch protection enforcement failed", exc)
            merge_gate["branch_protection_result"] = {"enforced": False, "error": str(exc)}

        response         = assemble_response(request, eval_status, findings, patches)
        response_payload = response.model_dump()
        knowledge_health = build_knowledge_health_score(
            request=request, findings=findings,
            merge_gate=merge_gate, doc_refresh_plan=doc_refresh_plan,
            weights={
                "policy":    self.health_weight_policy,
                "docs":      self.health_weight_docs,
                "ownership": self.health_weight_ownership,
            },
        )

        event_idempotency = payload.get("idempotency_key") or dedup_key
        fingerprint = self._fingerprint(response_payload)

        repo_payload = payload.get("repo")
        if isinstance(repo_payload, dict):
            repo_full_name = str(repo_payload.get("full_name") or request.repo)
        elif isinstance(repo_payload, str):
            repo_full_name = repo_payload
        else:
            repo_full_name = request.repo

        event_head_sha = (
            payload.get("head_sha")
            or (payload.get("pull_request") or {}).get("head_sha")
            or (((payload.get("pull_request") or {}).get("head") or {}).get("sha"))
        )

        # Persist check run
        with self._db_conn() as conn:
            conn.autocommit = False
            comment_state_id, comment_key, action, deduped = self.event_store._upsert_comment_state(
                conn, request.repo, request.pr_number, fingerprint
            )
            merge_gate["policy_action"] = action
            merge_gate["policy_profile"] = {
                "org":        controls.get("org"),
                "team":       controls.get("team"),
                "template_name": (controls.get("applied_template") or {}).get("template_name") if controls.get("applied_template") else None,
                "scope_type":    (controls.get("applied_template") or {}).get("scope_type")    if controls.get("applied_template") else None,
                "scope_value":   (controls.get("applied_template") or {}).get("scope_value")   if controls.get("applied_template") else None,
                "no_docs_no_merge": bool(controls.get("no_docs_no_merge")),
            }
            doc_refresh_plan["action"] = action
            check_run_id = self.event_store._persist_check_run(
                conn, request, response_payload, merge_gate,
                doc_refresh_plan, knowledge_health,
                event_idempotency, action, deduped, comment_state_id,
            )
            doc_refresh_job_id = self.event_store._persist_doc_refresh_job(
                conn, request, event_idempotency, selected_rule_set, action, doc_refresh_plan
            )
            self.event_store._persist_knowledge_health_snapshot(
                conn, request, event_idempotency, selected_rule_set,
                str(response_payload.get("summary_status") or "warn"), knowledge_health,
            )
            conn.commit()

        # Record policy findings as temporal events (Task 3.4.3)
        self._record_policy_temporal(request.repo, check_run_id, findings)

        self.state["processed_events"] += 1
        self.state["last_processed_at"] = datetime.now(timezone.utc).isoformat()

        if deduped:
            self.state["deduped_checks"] += 1
            # Even when content is deduped (noop comment/check output), the webhook handler
            # may have created a fresh in_progress check run for this PR SHA. Complete that
            # run so GitHub does not remain stuck in in_progress.
            if event_head_sha:
                import asyncio
                try:
                    asyncio.run(
                        self._update_check_run_from_policy(
                            repo=request.repo,
                            pr_number=request.pr_number,
                            head_sha=event_head_sha,
                            outcome=eval_status,
                        )
                    )
                except Exception as check_exc:
                    self.log.error(
                        f"Failed to update deduped check run for {request.repo} PR#{request.pr_number}: {check_exc}",
                        exc_info=True,
                    )
            return

        # Emit policy-check event
        out_event = {
            "schema_version": "1.0.0",
            "event_type": "pr_policy_check",
            "rule_set": selected_rule_set,
            "policy_pack_meta": eval_meta,
            "governance": {
                "team": controls.get("team"),
                "no_docs_no_merge": bool(controls.get("no_docs_no_merge")),
                "applied_template": controls.get("applied_template"),
                "active_waiver":    active_waiver,
            },
            "merge_gate":        merge_gate,
            "doc_refresh_plan":  doc_refresh_plan,
            "knowledge_health":  knowledge_health,
            "repo":              request.repo,
            "repo_full_name":    repo_full_name,
            "tenant_id":         payload.get("tenant_id") or ((payload.get("tenant") or {}).get("id")),
            "installation_id":   payload.get("installation_id") or ((payload.get("tenant") or {}).get("installation_id")),
            "pr_number":         request.pr_number,
            "head_sha":          event_head_sha,
            "correlation_id":    request.correlation_id,
            "idempotency_key":   event_idempotency,
            "summary_status":    response_payload.get("summary_status"),
            "action":            action,
            "comment_key":       comment_key,
            "markdown_comment":  response_payload.get("markdown_comment"),
            "findings":          response_payload.get("findings", []),
            "citations":         response_payload.get("citations", []),
            "check_annotations": response_payload.get("check_annotations", []),
            "suggested_patches": response_payload.get("suggested_patches", []),
            "produced_at":       datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.emitter.emit_check_event(out_event)
            self.state["emitted_checks"] += 1
            with self._db_conn() as conn3:
                conn3.autocommit = False
                self.event_store._update_emit_status(conn3, table="policy_check_runs", row_id=check_run_id, status="emitted")
                conn3.commit()
            
            # Task 4.4.3: Update GitHub Check Run after pr.checks event is emitted
            import asyncio
            head_sha = out_event.get("head_sha")
            if head_sha:
                try:
                    asyncio.run(self._update_check_run_from_policy(
                        repo=request.repo,
                        pr_number=request.pr_number,
                        head_sha=head_sha,
                        outcome=eval_status
                    ))
                except Exception as check_exc:
                    self.log.error(
                        f"Failed to update check run for {request.repo} PR#{request.pr_number}: {check_exc}",
                        exc_info=True
                    )
        except Exception as exc:
            self.state["emit_failures"] += 1
            with self._db_conn() as conn3:
                conn3.autocommit = False
                self.event_store._update_emit_status(conn3, table="policy_check_runs", row_id=check_run_id, status="failed", error=str(exc))
                queued = self.retry_worker.queue_job(
                    conn3, emit_type="policy_check",
                    base_idempotency_key=event_idempotency,
                    repo=request.repo, pr_number=request.pr_number,
                    correlation_id=request.correlation_id,
                    event_payload=out_event, error=str(exc),
                )
                conn3.commit()
            if queued:
                self.state["queued_emit_retries"] += 1
            self._log_error("policy check emit failed; queued retry", exc)

        # Emit doc-refresh and optionally doc-rewrite
        if self.doc_refresh_enabled and bool(doc_refresh_plan.get("should_emit")) and action != "noop":
            doc_event = {
                "schema_version": "1.0.0",
                "event_type": "doc_refresh_plan",
                "rule_set":    selected_rule_set,
                "repo":        request.repo,
                "repo_full_name": repo_full_name,
                "pr_number":   request.pr_number,
                "correlation_id":  request.correlation_id,
                "idempotency_key": event_idempotency,
                "doc_refresh_key": f"{request.repo}:{request.pr_number}:{selected_rule_set}",
                "plan":        doc_refresh_plan,
                "produced_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                self.emitter.emit_doc_refresh_event(doc_event)
                self.state["emitted_doc_refresh"] += 1
                with self._db_conn() as conn3:
                    conn3.autocommit = False
                    self.event_store._update_emit_status(conn3, table="doc_refresh_jobs", row_id=doc_refresh_job_id, status="emitted")
                    conn3.commit()
            except Exception as exc:
                self.state["emit_failures"] += 1
                with self._db_conn() as conn3:
                    conn3.autocommit = False
                    self.event_store._update_emit_status(conn3, table="doc_refresh_jobs", row_id=doc_refresh_job_id, status="failed", error=str(exc))
                    queued = self.retry_worker.queue_job(
                        conn3, emit_type="doc_refresh",
                        base_idempotency_key=event_idempotency,
                        repo=request.repo, pr_number=request.pr_number,
                        correlation_id=request.correlation_id,
                        event_payload=doc_event, error=str(exc),
                    )
                    conn3.commit()
                if queued:
                    self.state["queued_emit_retries"] += 1
                self._log_error("doc refresh emit failed; queued retry", exc)

            if self.doc_rewrite_enabled:
                self._handle_doc_rewrite(
                    payload=payload, request=request,
                    findings=findings, doc_refresh_plan=doc_refresh_plan,
                    merge_gate=merge_gate, knowledge_health=knowledge_health,
                    selected_rule_set=selected_rule_set,
                    event_idempotency=event_idempotency,
                    doc_refresh_job_id=doc_refresh_job_id,
                )

        self.state["emitted_health_snapshots"] += 1

    def _handle_doc_rewrite(
        self, *, payload, request, findings, doc_refresh_plan,
        merge_gate, knowledge_health, selected_rule_set,
        event_idempotency, doc_refresh_job_id,
    ) -> None:
        """Build, persist, and optionally emit a doc-rewrite bundle."""
        bundle = build_doc_rewrite_bundle(
            request=request, findings=findings,
            doc_refresh_plan=doc_refresh_plan, merge_gate=merge_gate,
            knowledge_health=knowledge_health,
        )
        quality_score = float(knowledge_health.get("score") or 0.0)

        with self._db_conn() as conn2:
            conn2.autocommit = False
            if quality_score < self.doc_rewrite_min_health_score:
                self.event_store._persist_doc_rewrite_run(
                    conn2, request=request, idempotency_key=event_idempotency,
                    selected_rule_set=selected_rule_set,
                    status="blocked_quality_gate",
                    reason="knowledge health below doc rewrite threshold",
                    quality_gate_score=quality_score, bundle=bundle,
                )
            else:
                conflict_reason = self._detect_doc_rewrite_conflict(
                    conn2, request.repo, request.pr_number, bundle
                )
                if conflict_reason:
                    self.event_store._persist_doc_rewrite_run(
                        conn2, request=request, idempotency_key=event_idempotency,
                        selected_rule_set=selected_rule_set, status="conflict",
                        reason=conflict_reason, quality_gate_score=quality_score, bundle=bundle,
                    )
                else:
                    rewrite_event = {
                        "schema_version": "1.0.0",
                        "event_type": "doc_rewrite_bundle",
                        "repo": request.repo, "pr_number": request.pr_number,
                        "rule_set": selected_rule_set,
                        "correlation_id": request.correlation_id,
                        "idempotency_key": event_idempotency,
                        "doc_refresh_job_id": doc_refresh_job_id,
                        "rewrite_key": f"{request.repo}:{request.pr_number}:{selected_rule_set}",
                        "quality_gate_score": quality_score,
                        "bundle": bundle,
                        "produced_at": datetime.now(timezone.utc).isoformat(),
                    }
                    rewrite_run_id = self.event_store._persist_doc_rewrite_run(
                        conn2, request=request, idempotency_key=event_idempotency,
                        selected_rule_set=selected_rule_set, status="queued_for_emit",
                        reason="rewrite bundle queued for emit",
                        quality_gate_score=quality_score, bundle=bundle,
                        emitted_event=rewrite_event,
                    )
                    conn2.commit()

                    try:
                        self.emitter.emit_doc_rewrite_event(rewrite_event)
                        self.state["emitted_doc_rewrite"] += 1
                        with self._db_conn() as conn3:
                            conn3.autocommit = False
                            self.event_store._update_emit_status(conn3, table="doc_rewrite_runs", row_id=rewrite_run_id, status="emitted")
                            conn3.commit()
                    except Exception as exc:
                        self.state["emit_failures"] += 1
                        with self._db_conn() as conn3:
                            conn3.autocommit = False
                            self.event_store._update_emit_status(conn3, table="doc_rewrite_runs", row_id=rewrite_run_id, status="failed", error=str(exc))
                            queued = self.retry_worker.queue_job(
                                conn3, emit_type="doc_rewrite",
                                base_idempotency_key=event_idempotency,
                                repo=request.repo, pr_number=request.pr_number,
                                correlation_id=request.correlation_id,
                                event_payload=rewrite_event, error=str(exc),
                            )
                            conn3.commit()
                        if queued:
                            self.state["queued_emit_retries"] += 1
                        self._log_error("doc rewrite emit failed; queued retry", exc)
                    return  # conn2 already committed above
            if conn2.closed == 0:
                conn2.commit()

    def _detect_doc_rewrite_conflict(
        self,
        conn,
        repo: str,
        pr_number: int,
        bundle: Dict[str, Any],
    ) -> Optional[str]:
        """
        Detect whether a doc rewrite is already in-flight for the same repo/PR.

        Returns a human-readable reason string when a conflict exists, else None.
        """
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM meta.doc_rewrite_runs
                    WHERE repo = %s
                      AND pr_number = %s
                      AND status IN ('queued_for_emit', 'emitted')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (repo, pr_number),
                )
                if cur.fetchone() is not None:
                    return "doc rewrite already queued for this PR"
        except Exception:
            # Conflict detection is best-effort and should not block policy handling.
            return None
        return None

    # ------------------------------------------------------------------
    # Ingestion event consumer
    # ------------------------------------------------------------------

    def _consume_ingestion_events(self, payload: Dict[str, Any]) -> None:
        """
        Consume repo.ingestion Kafka events and dispatch to ingestion pipeline.
        
        Dispatches to ingest_repo() when changed_files is None (full ingestion).
        Dispatches to ingest_on_push() when changed_files is a non-empty list (incremental).
        
        Args:
            payload: Kafka event payload with repo, changed_files, triggered_by, commit_sha
        """
        try:
            from ..dependencies import get_ingestion_pipeline
            import asyncio
            import uuid
            
            repo = payload.get("repo")
            changed_files = payload.get("changed_files")
            triggered_by = payload.get("triggered_by", "kafka")
            commit_sha = payload.get("commit_sha")
            
            if not repo:
                self.log.warning("Ignoring repo.ingestion event with missing repo field")
                return
            
            pipeline = get_ingestion_pipeline()
            run_id = str(uuid.uuid4())
            
            # Dispatch based on changed_files
            if changed_files is None:
                # Full ingestion
                self.log.info(f"Triggering full ingestion for {repo} (run_id={run_id})")
                asyncio.run(pipeline.ingest_repo(
                    repo=repo,
                    run_id=run_id,
                    triggered_by=triggered_by,
                    commit_sha=commit_sha,
                ))
            elif isinstance(changed_files, list) and len(changed_files) > 0:
                # Incremental ingestion
                self.log.info(f"Triggering incremental ingestion for {repo}: {len(changed_files)} files (run_id={run_id})")
                asyncio.run(pipeline.ingest_on_push(
                    repo=repo,
                    run_id=run_id,
                    changed_files=changed_files,
                    triggered_by=triggered_by,
                    commit_sha=commit_sha,
                ))
            else:
                self.log.warning(f"Ignoring repo.ingestion event with empty changed_files list for {repo}")
                
        except Exception as exc:
            self.log.error(f"Failed to process repo.ingestion event: {exc}", exc_info=True)

    # ------------------------------------------------------------------
    # Ingestion complete handler
    # ------------------------------------------------------------------

    async def _handle_ingestion_complete(self, payload: Dict[str, Any]) -> None:
        """
        Handle repo.ingestion.complete Kafka events.
        
        Records temporal snapshot first, then invalidates the impact analyzer cache for the repo.
        Order is important: snapshot before stale cache is cleared.
        
        Args:
            payload: Kafka event payload with repo field and ingestion result data
        """
        repo = payload.get("repo")
        if not repo:
            self.log.warning("Ignoring repo.ingestion.complete event with missing repo field")
            return
        
        # Record temporal snapshot (Task 3.4.1 & 3.4.2)
        # Must happen BEFORE cache invalidation to capture state before it's cleared
        try:
            from app.ingestion.ingestion_pipeline import IngestionResult
            # Filter out fields not in IngestionResult dataclass (e.g., triggered_at)
            result_fields = {
                "repo": payload.get("repo"),
                "run_id": payload.get("run_id"),
                "files_processed": payload.get("files_processed", 0),
                "chunks_created": payload.get("chunks_created", 0),
                "embeddings_created": payload.get("embeddings_created", 0),
                "services_detected": payload.get("services_detected", 0),
                "duration_seconds": payload.get("duration_seconds", 0.0),
                "status": payload.get("status", "unknown"),
            }
            ingestion_result = IngestionResult(**result_fields)
            snapshot_id = await self.time_travel.record_ingestion_snapshot(repo, ingestion_result)
            self.log.info(f"Recorded temporal snapshot {snapshot_id} for repo {repo}")
        except Exception as exc:
            self.log.error(f"Failed to record temporal snapshot for {repo}: {exc}", exc_info=True)
        
        # Invalidate impact analyzer cache (Task 2.2.1)
        if self.impact_analyzer:
            try:
                self.impact_analyzer.invalidate_cache(repo)
                self.log.info(f"Invalidated impact analyzer cache for repo {repo}")
            except Exception as exc:
                self.log.error(f"Failed to invalidate impact analyzer cache for {repo}: {exc}", exc_info=True)
        else:
            self.log.debug(f"Impact analyzer not configured, skipping cache invalidation for {repo}")

    def _record_policy_temporal(self, repo: str, run_id: int, findings: list[dict]) -> None:
        """
        Record policy findings as temporal snapshot events (Task 3.4.3).
        
        Called after policy evaluation completes in _handle_message().
        Only records DOC_DRIFT_* and BREAKING_* findings.
        
        Args:
            repo: Repository name
            run_id: Policy check run ID
            findings: List of finding dictionaries from policy evaluation
        """
        try:
            self.time_travel.record_policy_event(repo, run_id, findings)
            # Count relevant findings for logging
            relevant_count = sum(
                1 for f in findings
                if f.get("rule_id", "").startswith(("DOC_DRIFT_", "BREAKING_"))
            )
            if relevant_count > 0:
                self.log.info(f"Recorded {relevant_count} policy findings for {repo} run {run_id}")
        except Exception as exc:
            self.log.error(f"Failed to record policy temporal events for {repo} run {run_id}: {exc}", exc_info=True)

    async def _update_check_run_from_policy(
        self, repo: str, pr_number: int, head_sha: str, outcome: str
    ) -> None:
        """
        Update GitHub Check Run status from policy evaluation result (Task 4.4.1 & 4.4.2).
        
        Queries meta.check_run_tracking to find the check_run_id created by the webhook handler,
        then PATCH /repos/{owner}/{repo}/check-runs/{check_run_id} with status="completed",
        conclusion="success" when outcome == "pass" else "failure", completed_at=now.isoformat().
        
        Returns silently if no row is found (webhook may not have created a check run yet).
        
        Args:
            repo: Repository name (e.g., "owner/repo")
            pr_number: Pull request number
            head_sha: Git commit SHA for the PR head
            outcome: Policy evaluation outcome ("pass", "fail", "warn", "info")
        """
        try:
            with self._db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT check_run_id
                        FROM meta.check_run_tracking
                        WHERE repo = %s AND pr_number = %s AND head_sha = %s
                        """,
                        (repo, pr_number, head_sha)
                    )
                    row = cur.fetchone()
                    
                    if row is None:
                        # No check run tracking found - return silently as per spec
                        self.log.debug(
                            f"No check_run_id found for {repo} PR#{pr_number} SHA {head_sha[:7]}"
                        )
                        return
                    
                    check_run_id = row[0]
                    self.log.info(
                        f"Found check_run_id {check_run_id} for {repo} PR#{pr_number} SHA {head_sha[:7]}"
                    )
            
            # Task 4.4.2: PATCH check run with completed status
            # Determine conclusion based on outcome
            conclusion = "success" if outcome == "pass" else "failure"
            
            # Get GitHub token (reusing the pattern from agent-service/github_bridge.py)
            # We need to get the installation_id from the tenant context
            # For now, use the default installation_id from environment
            import os
            import jwt
            import requests
            from datetime import datetime, timedelta, timezone
            
            github_api_base = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")
            app_id = os.getenv("GITHUB_APP_ID", "").strip()
            private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "/run/secrets/github_app.pem").strip()
            installation_id = os.getenv("GITHUB_INSTALLATION_ID", "").strip()
            
            if not all([app_id, private_key_path, installation_id]):
                self.log.error("Missing GitHub App credentials for check run update")
                return
            
            # Create JWT
            now = datetime.now(timezone.utc)
            jwt_payload = {
                "iat": int((now - timedelta(seconds=60)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": app_id,
            }
            with open(private_key_path, "r", encoding="utf-8") as f:
                private_key = f.read()
            app_jwt = jwt.encode(jwt_payload, private_key, algorithm="RS256")
            
            # Get installation token
            token_url = f"{github_api_base}/app/installations/{installation_id}/access_tokens"
            token_headers = {
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            token_resp = requests.post(token_url, headers=token_headers, timeout=20)
            token_resp.raise_for_status()
            token = token_resp.json()["token"]
            
            # PATCH check run
            check_run_url = f"{github_api_base}/repos/{repo}/check-runs/{check_run_id}"
            check_run_headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            check_run_payload = {
                "status": "completed",
                "conclusion": conclusion,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            
            check_run_resp = requests.patch(
                check_run_url,
                headers=check_run_headers,
                json=check_run_payload,
                timeout=30
            )
            check_run_resp.raise_for_status()
            
            self.log.info(
                f"Updated check_run_id {check_run_id} for {repo} PR#{pr_number}: "
                f"status=completed, conclusion={conclusion}"
            )
                    
        except Exception as exc:
            self.log.error(
                f"Failed to update check run for {repo} PR#{pr_number}: {exc}",
                exc_info=True
            )

    # ------------------------------------------------------------------
    # Kafka consumer loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        self.state["running"] = True
        try:
            ensure_schema(self._db_conn)
            
            # Verify temporal index (advisory check only, does not block startup)
            self.time_travel._verify_temporal_index()
            
            # Subscribe to repo.events, repo.ingestion, and repo.ingestion.complete topics
            self.consumer = KafkaConsumer(
                self.consumer_topic,
                "repo.ingestion",  # Add ingestion topic
                "repo.ingestion.complete",  # Add ingestion complete topic
                bootstrap_servers=self.kafka_brokers,
                group_id=self.consumer_group,
                enable_auto_commit=True,
                auto_offset_reset="latest",
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
                consumer_timeout_ms=1000,
            )
            self.producer = KafkaProducer(bootstrap_servers=self.kafka_brokers)

            # Wire Kafka-dependent modules now that producer is up
            self.emitter = KafkaEmitter(
                self.producer,
                output_topic=self.output_topic,
                docs_refresh_topic=self.docs_refresh_topic,
                docs_rewrite_topic=self.docs_rewrite_topic,
            )
            self.retry_worker = EmitRetryWorker(
                event_store=self.event_store,
                emitter=self.emitter,
                db_conn_func=self._db_conn,
                enabled=self.emit_retry_enabled,
                batch_size=self.emit_retry_batch_size,
                max_attempts=self.emit_retry_max_attempts,
                backoff_seconds=self.emit_retry_backoff_seconds,
                on_state_update=self._inc_state,
                on_error=self._log_error,
            )

            while not self.stop_event.is_set():
                try:
                    self.retry_worker.process_jobs()
                except Exception as exc:
                    self.state["last_error"] = str(exc)
                    self._log_error("emit retry processing failed", exc)

                batch = self.consumer.poll(timeout_ms=1000, max_records=50)
                for topic_partition, records in batch.items():
                    for record in records:
                        try:
                            # Route to appropriate handler based on topic
                            if record.topic == "repo.ingestion":
                                self._consume_ingestion_events(record.value)
                            elif record.topic == "repo.ingestion.complete":
                                import asyncio
                                asyncio.run(self._handle_ingestion_complete(record.value))
                            else:
                                self._handle_message(
                                    record.value,
                                    source_topic=getattr(record, "topic", self.consumer_topic),
                                    source_partition=getattr(record, "partition", -1),
                                    source_offset=str(getattr(record, "offset", "unknown")),
                                )
                        except Exception as exc:
                            self.state["last_error"] = str(exc)
                            self._log_error("policy pipeline message handling failed", exc)

        except Exception as exc:
            self.state["last_error"] = str(exc)
            self._log_error("policy pipeline crashed", exc)
        finally:
            self.state["running"] = False
            if self.consumer:
                try:
                    self.consumer.close()
                except Exception:
                    pass
            if self.producer:
                try:
                    self.producer.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self.enabled:
            self.log.info("policy pipeline disabled by configuration")
            return
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="policy-pipeline")
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Health / readiness  (delegates to ReportingStore for metrics)
    # ------------------------------------------------------------------

    def _readiness(self) -> Dict[str, Any]:
        db_ok = False
        try:
            with self._db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    db_ok = (cur.fetchone() or [None])[0] == 1
        except Exception:
            db_ok = False

        consumer_ok = False
        producer_ok = False
        try:
            if self.consumer is not None and hasattr(self.consumer, "bootstrap_connected"):
                consumer_ok = bool(self.consumer.bootstrap_connected())
        except Exception:
            pass
        try:
            if self.producer is not None and hasattr(self.producer, "bootstrap_connected"):
                producer_ok = bool(self.producer.bootstrap_connected())
        except Exception:
            pass

        return {
            "db_connected":             db_ok,
            "kafka_consumer_connected": consumer_ok,
            "kafka_producer_connected": producer_ok,
            "ready": bool(db_ok and self.state.get("running") and producer_ok),
            "last_backlog_sampled_at": (
                self._last_backlog_sampled_at.isoformat()
                if self._last_backlog_sampled_at else None
            ),
        }

    def health(self) -> Dict[str, Any]:
        readiness     = self._readiness()
        retry_metrics = self.reporting_store.emit_retry_metrics(window_minutes=60, update_backlog_sample=False)
        return {
            **self.state,
            "topic_in":         self.consumer_topic,
            "topic_out":        self.output_topic,
            "topic_doc_refresh": self.docs_refresh_topic,
            "topic_doc_rewrite": self.docs_rewrite_topic,
            "consumer_group":   self.consumer_group,
            "health_weights": {
                "policy":    self.health_weight_policy,
                "docs":      self.health_weight_docs,
                "ownership": self.health_weight_ownership,
            },
            "doc_rewrite_quality_gate": self.doc_rewrite_min_health_score,
            "emit_retry": {
                "enabled":         self.emit_retry_enabled,
                "batch_size":      self.emit_retry_batch_size,
                "max_attempts":    self.emit_retry_max_attempts,
                "backoff_seconds": self.emit_retry_backoff_seconds,
            },
            "emit_retry_metrics": retry_metrics,
            "readiness":          readiness,
        }

    def readiness_signals(self) -> Dict[str, Any]:
        backlog = {}
        backlog_error = None
        try:
            backlog = self.reporting_store.emit_retry_metrics(
                window_minutes=60, update_backlog_sample=False
            ).get("backlog", {})
        except Exception as exc:
            backlog_error = str(exc)
        return {
            **self._readiness(),
            "emit_retry_backlog":       backlog,
            "emit_retry_backlog_error": backlog_error,
            "generated_at":             datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Governance pass-throughs (called by routes_admin.py)
    # ------------------------------------------------------------------

    def get_active_waiver(self, *, repo: str, pr_number: int, rule_set: str):
        return self.governance_store.get_active_waiver(
            repo=repo, pr_number=pr_number, rule_set=rule_set
        )

    # ------------------------------------------------------------------
    # Reporting pass-throughs (called by routes_dash.py via pipeline.*)
    # ------------------------------------------------------------------

    def list_health_snapshots(self, **kwargs):
        return self.reporting_store.list_health_snapshots(**kwargs)

    def list_doc_refresh_jobs(self, **kwargs):
        return self.reporting_store.list_doc_refresh_jobs(**kwargs)

    def list_doc_rewrite_runs(self, **kwargs):
        return self.reporting_store.list_doc_rewrite_runs(**kwargs)

    def list_emit_retry_jobs(self, **kwargs):
        return self.reporting_store.list_emit_retry_jobs(**kwargs)

    def list_emit_retry_dead_letters(self, **kwargs):
        return self.reporting_store.list_emit_retry_dead_letters(**kwargs)

    def emit_retry_overview(self, **kwargs):
        return self.reporting_store.emit_retry_overview(**kwargs)

    def emit_retry_metrics(self, **kwargs):
        return self.reporting_store.emit_retry_metrics(**kwargs)

    def emit_retry_alerts(self, **kwargs):
        return self.reporting_store.emit_retry_alerts(**kwargs)

    def dashboard_overview(self, **kwargs):
        return self.reporting_store.dashboard_overview(**kwargs)

    def requeue_emit_retry_dead_letter(self, **kwargs):
        return self.event_store.requeue_emit_retry_dead_letter(**kwargs)
