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

    def __init__(self, logger):
        self.log = logger
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

        self.state["processed_events"] += 1
        self.state["last_processed_at"] = datetime.now(timezone.utc).isoformat()

        if deduped:
            self.state["deduped_checks"] += 1
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
            "repo_full_name":    (payload.get("repo") or {}).get("full_name") or request.repo,
            "tenant_id":         payload.get("tenant_id") or ((payload.get("tenant") or {}).get("id")),
            "installation_id":   payload.get("installation_id") or ((payload.get("tenant") or {}).get("installation_id")),
            "pr_number":         request.pr_number,
            "head_sha": (
                (payload.get("pull_request") or {}).get("head_sha")
                or (((payload.get("pull_request") or {}).get("head") or {}).get("sha"))
            ),
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
                "repo_full_name": (payload.get("repo") or {}).get("full_name") or request.repo,
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

    # ------------------------------------------------------------------
    # Kafka consumer loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        self.state["running"] = True
        try:
            ensure_schema(self._db_conn)
            self.consumer = KafkaConsumer(
                self.consumer_topic,
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
                for records in batch.values():
                    for record in records:
                        try:
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
