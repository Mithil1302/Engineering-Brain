from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg2
from kafka import KafkaConsumer, KafkaProducer
from psycopg2.extras import RealDictCursor

from .engine import evaluate_policies, summary_status
from .models import (
    ChangedFile,
    EndpointSpec,
    ImpactEdge,
    PolicyEvaluationRequest,
    ServiceSpec,
)
from .patches import build_suggested_patches
from .renderer import assemble_response


class PolicyPipeline:
    def __init__(self, logger):
        self.log = logger
        self.enabled = os.getenv("POLICY_PIPELINE_ENABLED", "true").lower() == "true"
        self.kafka_brokers = [b.strip() for b in os.getenv("KAFKA_BROKERS", "kafka:9092").split(",") if b.strip()]
        self.consumer_topic = os.getenv("POLICY_INPUT_TOPIC", "repo.events")
        self.output_topic = os.getenv("POLICY_OUTPUT_TOPIC", "pr.checks")
        self.consumer_group = os.getenv("POLICY_CONSUMER_GROUP", "worker-policy-checks-v1")
        self.rule_set = os.getenv("POLICY_RULE_SET", "rules-v1")
        self.default_service_id = os.getenv("POLICY_DEFAULT_SERVICE_ID", "unknown-service")

        self.pg_cfg = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "user": os.getenv("POSTGRES_USER", "brain"),
            "password": os.getenv("POSTGRES_PASSWORD", "brain"),
            "dbname": os.getenv("POSTGRES_DB", "brain"),
        }

        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.consumer: Optional[KafkaConsumer] = None
        self.producer: Optional[KafkaProducer] = None

        self.state: Dict[str, Any] = {
            "enabled": self.enabled,
            "running": False,
            "processed_events": 0,
            "emitted_checks": 0,
            "deduped_checks": 0,
            "skipped_events": 0,
            "last_error": None,
            "last_processed_at": None,
        }

    def _db_conn(self):
        return psycopg2.connect(**self.pg_cfg)

    def _log_error(self, message: str, err: Exception):
        try:
            self.log.error("%s: %s", message, str(err))
        except Exception:
            pass

    def _is_policy_event(self, payload: Dict[str, Any]) -> bool:
        event_type = payload.get("event_type")
        return event_type in {"pull_request", "spec", "schema", "doc"}

    def _build_request(self, payload: Dict[str, Any]) -> Optional[PolicyEvaluationRequest]:
        repo = payload.get("repo") or {}
        repo_id = repo.get("full_name") or repo.get("name_with_owner") or repo.get("id")
        if not repo_id:
            return None

        changed_files = [
            ChangedFile(path=f.get("path", "unknown"), status=f.get("status", "modified"))
            for f in payload.get("changed_files", [])
        ]

        policy_ctx = payload.get("policy_context") or {}

        if policy_ctx.get("head_spec"):
            head_spec = ServiceSpec.model_validate(policy_ctx["head_spec"])
        else:
            inferred_endpoint = EndpointSpec(
                method="POST" if payload.get("event_type") == "pull_request" else "GET",
                path=f"/inferred/{payload.get('event_type', 'event')}",
                operation_id=f"inferred_{payload.get('event_type', 'event')}",
                owner=(payload.get("owner") or None),
                request_required_fields=[],
                request_enum_fields={},
                response_fields={"status": "string"},
                response_status_codes=["200"],
            )
            head_spec = ServiceSpec(service_id=self.default_service_id, endpoints=[inferred_endpoint])

        base_spec = None
        if policy_ctx.get("base_spec"):
            base_spec = ServiceSpec.model_validate(policy_ctx["base_spec"])

        impact_edges = []
        for edge in policy_ctx.get("impact_edges", []):
            try:
                impact_edges.append(ImpactEdge.model_validate(edge))
            except Exception:
                continue

        owners = policy_ctx.get("owners") or {}
        docs_touched = policy_ctx.get("docs_touched") or []

        pr = payload.get("pull_request") or {}
        pr_number = pr.get("number")

        return PolicyEvaluationRequest(
            repo=repo_id,
            pr_number=pr_number,
            correlation_id=payload.get("correlation_id"),
            head_spec=head_spec,
            base_spec=base_spec,
            changed_files=changed_files,
            owners=owners,
            docs_touched=docs_touched,
            impact_edges=impact_edges,
            config=policy_ctx.get("config"),
        )

    @staticmethod
    def _fingerprint(response_payload: Dict[str, Any]) -> str:
        normalized_findings = []
        for f in response_payload.get("findings", []):
            normalized_findings.append(
                {
                    "rule_id": f.get("rule_id"),
                    "severity": f.get("severity"),
                    "status": f.get("status"),
                    "title": f.get("title"),
                    "description": f.get("description"),
                    "entity_refs": f.get("entity_refs", []),
                    "evidence": f.get("evidence", []),
                    "suggested_action": f.get("suggested_action"),
                }
            )

        raw = json.dumps(
            {
                "summary_status": response_payload.get("summary_status"),
                "markdown_comment": response_payload.get("markdown_comment"),
                "findings": normalized_findings,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _upsert_comment_state(self, conn, repo: str, pr_number: int, fingerprint: str):
        comment_key = f"{repo}:{pr_number}:{self.rule_set}"
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, latest_fingerprint, delivery_count
                FROM meta.pr_comment_state
                WHERE comment_key = %s
                """,
                (comment_key,),
            )
            row = cur.fetchone()

            if row is None:
                cur.execute(
                    """
                    INSERT INTO meta.pr_comment_state (comment_key, repo, pr_number, rule_set, latest_fingerprint, delivery_count, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW())
                    RETURNING id
                    """,
                    (comment_key, repo, pr_number, self.rule_set, fingerprint),
                )
                state_id = cur.fetchone()["id"]
                return state_id, comment_key, "create_comment", False

            if row["latest_fingerprint"] == fingerprint:
                cur.execute(
                    """
                    UPDATE meta.pr_comment_state
                    SET updated_at = NOW()
                    WHERE id = %s
                    """,
                    (row["id"],),
                )
                return row["id"], comment_key, "noop", True

            cur.execute(
                """
                UPDATE meta.pr_comment_state
                SET latest_fingerprint = %s,
                    delivery_count = delivery_count + 1,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (fingerprint, row["id"]),
            )
            return row["id"], comment_key, "update_comment", False

    def _persist_check_run(
        self,
        conn,
        request: PolicyEvaluationRequest,
        response_payload: Dict[str, Any],
        idempotency_key: str,
        action: str,
        deduped: bool,
        comment_state_id: int,
    ):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.policy_check_runs (
                    repo,
                    pr_number,
                    correlation_id,
                    idempotency_key,
                    summary_status,
                    findings,
                    markdown_comment,
                    suggested_patches,
                    check_annotations,
                    action,
                    deduped,
                    comment_state_id,
                    created_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s,%s,%s,NOW())
                """,
                (
                    request.repo,
                    request.pr_number,
                    request.correlation_id,
                    idempotency_key,
                    response_payload.get("summary_status"),
                    json.dumps(response_payload.get("findings", [])),
                    response_payload.get("markdown_comment"),
                    json.dumps(response_payload.get("suggested_patches", [])),
                    json.dumps(response_payload.get("check_annotations", [])),
                    action,
                    deduped,
                    comment_state_id,
                ),
            )

    def _emit_check_event(self, event: Dict[str, Any]):
        if self.producer is None:
            raise RuntimeError("producer not initialized")

        self.producer.send(
            self.output_topic,
            key=(event.get("comment_key") or "policy-check").encode("utf-8"),
            value=json.dumps(event).encode("utf-8"),
            headers=[
                ("x-correlation-id", str(event.get("correlation_id") or "").encode("utf-8")),
                ("x-repo", str(event.get("repo") or "").encode("utf-8")),
                ("x-pr-number", str(event.get("pr_number") or "").encode("utf-8")),
            ],
        )
        self.producer.flush(timeout=5)

    def _handle_message(self, payload: Dict[str, Any]):
        if not self._is_policy_event(payload):
            self.state["skipped_events"] += 1
            return

        request = self._build_request(payload)
        if request is None or request.pr_number is None:
            self.state["skipped_events"] += 1
            return

        findings = evaluate_policies(request)
        patches = build_suggested_patches(findings)
        status = summary_status(findings)
        response = assemble_response(request, status, findings, patches)
        response_payload = response.model_dump()

        event_idempotency = payload.get("idempotency_key") or f"{request.repo}:{request.pr_number}:{int(time.time())}"
        fingerprint = self._fingerprint(response_payload)

        with self._db_conn() as conn:
            conn.autocommit = False
            comment_state_id, comment_key, action, deduped = self._upsert_comment_state(
                conn, request.repo, request.pr_number, fingerprint
            )
            self._persist_check_run(
                conn,
                request,
                response_payload,
                event_idempotency,
                action,
                deduped,
                comment_state_id,
            )
            conn.commit()

        self.state["processed_events"] += 1
        self.state["last_processed_at"] = datetime.now(timezone.utc).isoformat()

        if deduped:
            self.state["deduped_checks"] += 1
            return

        out_event = {
            "schema_version": "1.0.0",
            "event_type": "pr_policy_check",
            "rule_set": self.rule_set,
            "repo": request.repo,
            "repo_full_name": (payload.get("repo") or {}).get("full_name") or request.repo,
            "tenant_id": payload.get("tenant_id") or ((payload.get("tenant") or {}).get("id")),
            "installation_id": payload.get("installation_id") or ((payload.get("tenant") or {}).get("installation_id")),
            "pr_number": request.pr_number,
            "head_sha": ((payload.get("pull_request") or {}).get("head_sha") or (((payload.get("pull_request") or {}).get("head") or {}).get("sha"))),
            "correlation_id": request.correlation_id,
            "idempotency_key": event_idempotency,
            "summary_status": response_payload.get("summary_status"),
            "action": action,
            "comment_key": comment_key,
            "markdown_comment": response_payload.get("markdown_comment"),
            "findings": response_payload.get("findings", []),
            "citations": response_payload.get("citations", []),
            "check_annotations": response_payload.get("check_annotations", []),
            "suggested_patches": response_payload.get("suggested_patches", []),
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }
        self._emit_check_event(out_event)
        self.state["emitted_checks"] += 1

    def _run_loop(self):
        self.state["running"] = True
        try:
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

            while not self.stop_event.is_set():
                batch = self.consumer.poll(timeout_ms=1000, max_records=50)
                for records in batch.values():
                    for record in records:
                        try:
                            self._handle_message(record.value)
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

    def start(self):
        if not self.enabled:
            self.log.info("policy pipeline disabled by configuration")
            return
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="policy-pipeline")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    def health(self) -> Dict[str, Any]:
        return {
            **self.state,
            "topic_in": self.consumer_topic,
            "topic_out": self.output_topic,
            "consumer_group": self.consumer_group,
        }
