from __future__ import annotations

import json
import logging
import os
import hmac
import hashlib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

import jwt
import psycopg2
import requests
from kafka import KafkaConsumer, KafkaProducer
from psycopg2.extras import RealDictCursor
from cryptography.fernet import Fernet, InvalidToken


@dataclass
class InstallationToken:
    token: str
    expires_at: datetime


@dataclass
class TenantContext:
    tenant_id: str
    installation_id: str


@dataclass
class TenantCircuitState:
    failures: int = 0
    open_until_epoch: float = 0.0


class GithubBridge:
    def __init__(self):
        self.log = logging.getLogger("agent-service.github-bridge")

        self.enabled = os.getenv("GITHUB_BRIDGE_ENABLED", "true").lower() == "true"
        self.kafka_brokers = [b.strip() for b in os.getenv("KAFKA_BROKERS", "kafka:9092").split(",") if b.strip()]
        self.input_topic = os.getenv("GITHUB_BRIDGE_INPUT_TOPIC", "pr.checks")
        self.dlq_topic = os.getenv("GITHUB_BRIDGE_DLQ_TOPIC", "pr.checks.dlq")
        self.consumer_group = os.getenv("GITHUB_BRIDGE_CONSUMER_GROUP", "agent-github-bridge-v1")

        self.github_api_base = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")
        self.target_repo = os.getenv("GITHUB_TARGET_REPO", "").strip()
        self.check_name = os.getenv("GITHUB_CHECK_NAME", "KA-CHOW Policy Gate")
        self.max_attempts = int(os.getenv("GITHUB_DELIVERY_MAX_ATTEMPTS", "3"))
        self.retry_base_delay_ms = int(os.getenv("GITHUB_DELIVERY_RETRY_BASE_DELAY_MS", "500"))
        self.rate_limit_per_minute = int(os.getenv("GITHUB_TENANT_RATE_LIMIT_PER_MINUTE", "120"))
        self.circuit_failure_threshold = int(os.getenv("GITHUB_TENANT_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
        self.circuit_cooldown_sec = int(os.getenv("GITHUB_TENANT_CIRCUIT_BREAKER_COOLDOWN_SEC", "120"))
        self.webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")

        self._tenant_rate_windows: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._tenant_circuit: Dict[str, TenantCircuitState] = defaultdict(TenantCircuitState)

        self.app_id = os.getenv("GITHUB_APP_ID", "").strip()
        self.installation_id = os.getenv("GITHUB_INSTALLATION_ID", "").strip()
        self.private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "/run/secrets/github_app.pem").strip()
        self.metadata_encryption_key = os.getenv("TENANT_METADATA_ENCRYPTION_KEY", "").strip()
        self._fernet: Optional[Fernet] = None
        if self.metadata_encryption_key:
            try:
                self._fernet = Fernet(self.metadata_encryption_key.encode("utf-8"))
            except Exception:
                self.log.warning("TENANT_METADATA_ENCRYPTION_KEY is invalid; tenant metadata will be stored as plaintext")

        self.pg_cfg = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "user": os.getenv("POSTGRES_USER", "brain"),
            "password": os.getenv("POSTGRES_PASSWORD", "brain"),
            "dbname": os.getenv("POSTGRES_DB", "brain"),
        }

        self._consumer: Optional[KafkaConsumer] = None
        self._producer: Optional[KafkaProducer] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cached_installation_tokens: Dict[str, InstallationToken] = {}

        self.state: Dict[str, Any] = {
            "enabled": self.enabled,
            "running": False,
            "processed": 0,
            "delivered": 0,
            "deduped": 0,
            "failed": 0,
            "skipped": 0,
            "last_error": None,
            "last_processed_at": None,
        }

    def _db_conn(self):
        return psycopg2.connect(**self.pg_cfg)

    def _ensure_schema(self):
        with self._db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE SCHEMA IF NOT EXISTS meta;

                                        CREATE TABLE IF NOT EXISTS meta.github_delivery_state (
                      id BIGSERIAL PRIMARY KEY,
                      comment_key TEXT NOT NULL UNIQUE,
                                            tenant_id TEXT,
                                            installation_id TEXT,
                      repo_full_name TEXT NOT NULL,
                      pr_number BIGINT NOT NULL,
                      check_run_id BIGINT,
                      comment_id BIGINT,
                      last_action TEXT,
                      last_status TEXT,
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );

                                        CREATE TABLE IF NOT EXISTS meta.github_delivery_attempts (
                      id BIGSERIAL PRIMARY KEY,
                      comment_key TEXT,
                                            tenant_id TEXT,
                                            installation_id TEXT,
                      repo_full_name TEXT,
                      pr_number BIGINT,
                      action TEXT,
                      success BOOLEAN NOT NULL,
                      status_code INT,
                      error TEXT,
                      request_payload JSONB,
                      response_payload JSONB,
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );

                                        CREATE TABLE IF NOT EXISTS meta.tenant_installations (
                                            id BIGSERIAL PRIMARY KEY,
                                            tenant_id TEXT NOT NULL,
                                            repo_full_name TEXT NOT NULL,
                                            installation_id TEXT NOT NULL,
                                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                                            metadata JSONB,
                                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                            UNIQUE (tenant_id, repo_full_name)
                                        );

                                        CREATE INDEX IF NOT EXISTS idx_github_delivery_state_repo_pr ON meta.github_delivery_state (repo_full_name, pr_number);
                    CREATE INDEX IF NOT EXISTS idx_github_delivery_attempts_created ON meta.github_delivery_attempts (created_at DESC);
                                        CREATE INDEX IF NOT EXISTS idx_tenant_installations_tenant_repo ON meta.tenant_installations (tenant_id, repo_full_name);

                                        ALTER TABLE meta.github_delivery_state ADD COLUMN IF NOT EXISTS tenant_id TEXT;
                                        ALTER TABLE meta.github_delivery_state ADD COLUMN IF NOT EXISTS installation_id TEXT;
                                        ALTER TABLE meta.github_delivery_attempts ADD COLUMN IF NOT EXISTS tenant_id TEXT;
                                        ALTER TABLE meta.github_delivery_attempts ADD COLUMN IF NOT EXISTS installation_id TEXT;
                    """
                )
            conn.commit()

    def _read_private_key(self) -> str:
        with open(self.private_key_path, "r", encoding="utf-8") as f:
            return f.read()

    def _encrypt_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        if self._fernet is None:
            return metadata
        plaintext = json.dumps(metadata or {}, sort_keys=True).encode("utf-8")
        ciphertext = self._fernet.encrypt(plaintext).decode("utf-8")
        return {"_enc": "fernet", "ciphertext": ciphertext}

    def _decrypt_metadata(self, stored: Any) -> Dict[str, Any]:
        if not isinstance(stored, dict):
            return {}
        if stored.get("_enc") != "fernet":
            return stored
        if self._fernet is None:
            return {"_error": "encrypted-metadata-present-but-no-key"}
        try:
            plaintext = self._fernet.decrypt(str(stored.get("ciphertext", "")).encode("utf-8"))
            return json.loads(plaintext.decode("utf-8"))
        except (InvalidToken, ValueError, TypeError):
            return {"_error": "metadata-decryption-failed"}

    def _tenant_rate_limit_ok(self, tenant_id: str) -> bool:
        if self.rate_limit_per_minute <= 0:
            return True
        now = time.time()
        bucket = self._tenant_rate_windows[tenant_id]
        window_start = float(bucket.get("window_start", 0.0))
        count = int(bucket.get("count", 0))

        if now - window_start >= 60:
            bucket["window_start"] = now
            bucket["count"] = 1
            return True

        if count >= self.rate_limit_per_minute:
            return False

        bucket["count"] = count + 1
        return True

    def _tenant_circuit_open(self, tenant_id: str) -> bool:
        state = self._tenant_circuit[tenant_id]
        return state.open_until_epoch > time.time()

    def _tenant_record_success(self, tenant_id: str):
        state = self._tenant_circuit[tenant_id]
        state.failures = 0
        state.open_until_epoch = 0.0

    def _tenant_record_failure(self, tenant_id: str):
        state = self._tenant_circuit[tenant_id]
        state.failures += 1
        if state.failures >= self.circuit_failure_threshold:
            state.open_until_epoch = time.time() + self.circuit_cooldown_sec

    def verify_webhook_signature(self, body: bytes, signature_header: Optional[str]) -> bool:
        if not self.webhook_secret:
            return False
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        provided = signature_header.split("=", 1)[1]
        computed = hmac.new(self.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(provided, computed)

    def _derive_tenant_from_installation_payload(self, payload: Dict[str, Any], installation_id: str) -> str:
        account = ((payload.get("installation") or {}).get("account") or {})
        login = account.get("login")
        if login:
            return f"gh:{login}"
        return f"installation:{installation_id}"

    def process_github_webhook(self, event_type: str, payload: Dict[str, Any], delivery_id: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_schema()

        if event_type not in {"installation", "installation_repositories"}:
            return {"ok": True, "ignored": True, "event_type": event_type, "delivery_id": delivery_id}

        action = str(payload.get("action") or "")
        installation = payload.get("installation") or {}
        installation_id = str(installation.get("id") or "").strip()
        if not installation_id:
            return {"ok": False, "ignored": True, "reason": "missing_installation_id", "delivery_id": delivery_id}

        tenant_id = self._derive_tenant_from_installation_payload(payload, installation_id)

        repositories: list[Dict[str, Any]] = []
        if event_type == "installation":
            repositories = payload.get("repositories") or []
        elif event_type == "installation_repositories":
            repositories = (payload.get("repositories_added") or []) + (payload.get("repositories_removed") or [])

        updated = []
        for repo in repositories:
            full_name = repo.get("full_name")
            if not full_name:
                continue
            enabled = True
            if action in {"deleted", "suspend"}:
                enabled = False
            if event_type == "installation_repositories" and repo in (payload.get("repositories_removed") or []):
                enabled = False

            rec = self.upsert_tenant_installation(
                tenant_id=tenant_id,
                repo_full_name=full_name,
                installation_id=installation_id,
                enabled=enabled,
                metadata={
                    "source": "webhook",
                    "delivery_id": delivery_id,
                    "event_type": event_type,
                    "action": action,
                },
            )
            updated.append(rec)

        return {
            "ok": True,
            "event_type": event_type,
            "action": action,
            "tenant_id": tenant_id,
            "installation_id": installation_id,
            "updated_count": len(updated),
            "delivery_id": delivery_id,
        }

    def _create_app_jwt(self) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "iat": int((now - timedelta(seconds=60)).timestamp()),
            "exp": int((now + timedelta(minutes=9)).timestamp()),
            "iss": self.app_id,
        }
        private_key = self._read_private_key()
        token = jwt.encode(payload, private_key, algorithm="RS256")
        return token

    def _installation_token(self, installation_id: str) -> str:
        now = datetime.now(timezone.utc)
        cached = self._cached_installation_tokens.get(installation_id)
        if cached and cached.expires_at - timedelta(minutes=1) > now:
            return cached.token

        app_jwt = self._create_app_jwt()
        url = f"{self.github_api_base}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        resp = requests.post(url, headers=headers, timeout=20)
        resp.raise_for_status()
        body = resp.json()

        expires_at = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        self._cached_installation_tokens[installation_id] = InstallationToken(token=body["token"], expires_at=expires_at)
        return body["token"]

    def _resolve_tenant_context(self, conn, event: Dict[str, Any], repo_full_name: str) -> Optional[TenantContext]:
        tenant_payload = event.get("tenant") or {}
        tenant_id = (event.get("tenant_id") or tenant_payload.get("id") or "").strip() or None
        installation_id = (
            event.get("installation_id")
            or tenant_payload.get("installation_id")
            or event.get("github_installation_id")
            or None
        )

        if installation_id:
            resolved_tenant = tenant_id or f"installation:{installation_id}"
            return TenantContext(tenant_id=resolved_tenant, installation_id=str(installation_id))

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if tenant_id:
                cur.execute(
                    """
                    SELECT tenant_id, installation_id
                    FROM meta.tenant_installations
                    WHERE enabled = TRUE
                      AND tenant_id = %s
                      AND (repo_full_name = %s OR repo_full_name = '*')
                    ORDER BY CASE WHEN repo_full_name = %s THEN 0 ELSE 1 END, updated_at DESC
                    LIMIT 1
                    """,
                    (tenant_id, repo_full_name, repo_full_name),
                )
            else:
                cur.execute(
                    """
                    SELECT tenant_id, installation_id
                    FROM meta.tenant_installations
                    WHERE enabled = TRUE
                      AND (repo_full_name = %s OR repo_full_name = '*')
                    ORDER BY CASE WHEN repo_full_name = %s THEN 0 ELSE 1 END, updated_at DESC
                    LIMIT 1
                    """,
                    (repo_full_name, repo_full_name),
                )

            row = cur.fetchone()
            if row:
                return TenantContext(tenant_id=row["tenant_id"], installation_id=row["installation_id"])

        if self.installation_id:
            fallback_tenant = tenant_id or "default"
            return TenantContext(tenant_id=fallback_tenant, installation_id=self.installation_id)

        return None

    @staticmethod
    def _conclusion_for(summary_status: str) -> str:
        mapping = {
            "fail": "failure",
            "warn": "neutral",
            "info": "neutral",
            "pass": "success",
        }
        return mapping.get((summary_status or "").lower(), "neutral")

    def _fetch_pr_head_sha(self, repo_full_name: str, pr_number: int, token: str) -> str:
        url = f"{self.github_api_base}/repos/{repo_full_name}/pulls/{pr_number}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json()["head"]["sha"]

    @staticmethod
    def _looks_like_commit_sha(value: Optional[str]) -> bool:
        if not value:
            return False
        candidate = value.strip()
        if len(candidate) != 40:
            return False
        return all(ch in "0123456789abcdefABCDEF" for ch in candidate)

    def _upsert_state(self, conn, comment_key: str, tenant_id: str, installation_id: str, repo_full_name: str, pr_number: int):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM meta.github_delivery_state WHERE comment_key = %s",
                (comment_key,),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE meta.github_delivery_state
                    SET tenant_id = %s,
                        installation_id = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (tenant_id, installation_id, row["id"]),
                )
                return row

            cur.execute(
                """
                INSERT INTO meta.github_delivery_state (comment_key, tenant_id, installation_id, repo_full_name, pr_number, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,NOW(),NOW())
                RETURNING *
                """,
                (comment_key, tenant_id, installation_id, repo_full_name, pr_number),
            )
            return cur.fetchone()

    def _record_attempt(
        self,
        conn,
        *,
        comment_key: str,
        tenant_id: str,
        installation_id: str,
        repo_full_name: str,
        pr_number: int,
        action: str,
        success: bool,
        status_code: Optional[int],
        error: Optional[str],
        request_payload: Optional[Dict[str, Any]],
        response_payload: Optional[Dict[str, Any]],
    ):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.github_delivery_attempts (
                                    comment_key, tenant_id, installation_id, repo_full_name, pr_number, action, success, status_code, error, request_payload, response_payload, created_at
                                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,NOW())
                """,
                (
                    comment_key,
                                        tenant_id,
                                        installation_id,
                    repo_full_name,
                    pr_number,
                    action,
                    success,
                    status_code,
                    error,
                    json.dumps(request_payload or {}),
                    json.dumps(response_payload or {}),
                ),
            )

    def _record_failed_attempt(
        self,
        event: Dict[str, Any],
        action: str,
        error: str,
        status_code: Optional[int],
        tenant_ctx: Optional[TenantContext],
    ):
        repo_full_name = event.get("repo_full_name") or event.get("repo") or self.target_repo or "unknown"
        pr_number = int(event.get("pr_number") or 0)
        comment_key = event.get("comment_key") or f"{repo_full_name}:{pr_number}:rules-v1"
        tenant_id = tenant_ctx.tenant_id if tenant_ctx else (event.get("tenant_id") or "unknown")
        installation_id = tenant_ctx.installation_id if tenant_ctx else str(event.get("installation_id") or "unknown")

        try:
            with self._db_conn() as conn:
                conn.autocommit = False
                state_row = self._upsert_state(conn, comment_key, tenant_id, installation_id, repo_full_name, pr_number)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE meta.github_delivery_state
                        SET last_action = %s,
                            last_status = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (action, "delivery_failed", state_row["id"]),
                    )

                self._record_attempt(
                    conn,
                    comment_key=comment_key,
                    tenant_id=tenant_id,
                    installation_id=installation_id,
                    repo_full_name=repo_full_name,
                    pr_number=pr_number,
                    action=action,
                    success=False,
                    status_code=status_code,
                    error=error,
                    request_payload=event,
                    response_payload={"status": status_code} if status_code else {},
                )
                conn.commit()
        except Exception:
            # Do not let audit persistence failures block DLQ publishing.
            pass

    def _create_or_update_check_run(
        self,
        *,
        token: str,
        repo_full_name: str,
        head_sha: str,
        summary_status: str,
        markdown_comment: str,
        external_id: str,
        existing_check_run_id: Optional[int],
    ) -> Tuple[int, Dict[str, Any], Dict[str, Any], int]:
        conclusion = self._conclusion_for(summary_status)
        payload = {
            "name": self.check_name,
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion,
            "external_id": external_id,
            "output": {
                "title": f"{self.check_name} ({summary_status})",
                "summary": (markdown_comment or "")[:65500],
            },
        }
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if existing_check_run_id:
            url = f"{self.github_api_base}/repos/{repo_full_name}/check-runs/{existing_check_run_id}"
            resp = requests.patch(url, headers=headers, json=payload, timeout=30)
        else:
            url = f"{self.github_api_base}/repos/{repo_full_name}/check-runs"
            resp = requests.post(url, headers=headers, json=payload, timeout=30)

        resp.raise_for_status()
        body = resp.json()
        return int(body["id"]), payload, body, resp.status_code

    def _create_or_update_comment(
        self,
        *,
        token: str,
        repo_full_name: str,
        pr_number: int,
        markdown_comment: str,
        action: str,
        existing_comment_id: Optional[int],
    ) -> Tuple[Optional[int], Dict[str, Any], Dict[str, Any], int]:
        if action == "noop":
            return existing_comment_id, {}, {}, 204

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"body": markdown_comment}

        if action == "update_comment" and existing_comment_id:
            url = f"{self.github_api_base}/repos/{repo_full_name}/issues/comments/{existing_comment_id}"
            resp = requests.patch(url, headers=headers, json=payload, timeout=30)
        else:
            url = f"{self.github_api_base}/repos/{repo_full_name}/issues/{pr_number}/comments"
            resp = requests.post(url, headers=headers, json=payload, timeout=30)

        resp.raise_for_status()
        body = resp.json()
        return int(body["id"]), payload, body, resp.status_code

    def _publish_dlq(self, event: Dict[str, Any], error: str):
        if self._producer is None:
            return
        dlq = {
            "schema_version": "1.0.0",
            "event_type": "pr_check_delivery_failed",
            "error": error,
            "source_topic": self.input_topic,
            "produced_at": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        self._producer.send(
            self.dlq_topic,
            key=str(event.get("comment_key") or "github-bridge-dlq").encode("utf-8"),
            value=json.dumps(dlq).encode("utf-8"),
        )
        self._producer.flush(timeout=5)

    def _deliver(self, event: Dict[str, Any]):
        pr_number = event.get("pr_number")
        if not pr_number:
            self.state["skipped"] += 1
            return

        repo_full_name = event.get("repo_full_name") or self.target_repo
        if not repo_full_name:
            self.state["skipped"] += 1
            return

        if self.target_repo and repo_full_name != self.target_repo:
            self.state["skipped"] += 1
            return

        action = event.get("action") or "create_comment"
        with self._db_conn() as conn:
            conn.autocommit = False
            tenant_ctx = self._resolve_tenant_context(conn, event, repo_full_name)
            if tenant_ctx is None:
                raise RuntimeError(f"No tenant installation mapping found for repo {repo_full_name}")

            if not self._tenant_rate_limit_ok(tenant_ctx.tenant_id):
                raise RuntimeError(f"Tenant {tenant_ctx.tenant_id} exceeded per-minute delivery limit")
            if self._tenant_circuit_open(tenant_ctx.tenant_id):
                raise RuntimeError(f"Tenant {tenant_ctx.tenant_id} circuit breaker is open")

            comment_key = event.get("comment_key") or f"{tenant_ctx.tenant_id}:{repo_full_name}:{pr_number}:rules-v1"
            token = self._installation_token(tenant_ctx.installation_id)
            provided_head_sha = event.get("head_sha")
            if self._looks_like_commit_sha(provided_head_sha):
                head_sha = provided_head_sha
            else:
                head_sha = self._fetch_pr_head_sha(repo_full_name, int(pr_number), token)

            state_row = self._upsert_state(
                conn,
                comment_key,
                tenant_ctx.tenant_id,
                tenant_ctx.installation_id,
                repo_full_name,
                int(pr_number),
            )

            check_run_id, check_req, check_resp, check_status = self._create_or_update_check_run(
                token=token,
                repo_full_name=repo_full_name,
                head_sha=head_sha,
                summary_status=event.get("summary_status", "warn"),
                markdown_comment=event.get("markdown_comment", ""),
                external_id=comment_key,
                existing_check_run_id=state_row.get("check_run_id"),
            )

            comment_id, comment_req, comment_resp, comment_status = self._create_or_update_comment(
                token=token,
                repo_full_name=repo_full_name,
                pr_number=int(pr_number),
                markdown_comment=event.get("markdown_comment", ""),
                action=action,
                existing_comment_id=state_row.get("comment_id"),
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.github_delivery_state
                    SET check_run_id = %s,
                        comment_id = %s,
                        last_action = %s,
                        last_status = %s,
                        tenant_id = %s,
                        installation_id = %s,
                        updated_at = NOW()
                    WHERE comment_key = %s
                    """,
                    (
                        check_run_id,
                        comment_id,
                        action,
                        event.get("summary_status"),
                        tenant_ctx.tenant_id,
                        tenant_ctx.installation_id,
                        comment_key,
                    ),
                )

            self._record_attempt(
                conn,
                comment_key=comment_key,
                tenant_id=tenant_ctx.tenant_id,
                installation_id=tenant_ctx.installation_id,
                repo_full_name=repo_full_name,
                pr_number=int(pr_number),
                action=action,
                success=True,
                status_code=check_status if check_status >= (comment_status or 0) else comment_status,
                error=None,
                request_payload={"check": check_req, "comment": comment_req},
                response_payload={"check": check_resp, "comment": comment_resp},
            )
            conn.commit()

        self._tenant_record_success(tenant_ctx.tenant_id)
        self.state["delivered"] += 1

    def _handle_message(self, event: Dict[str, Any]):
        tenant_ctx_for_failure: Optional[TenantContext] = None
        tenant_payload = event.get("tenant") or {}
        installation_id = event.get("installation_id") or tenant_payload.get("installation_id")
        tenant_id = event.get("tenant_id") or tenant_payload.get("id")
        if installation_id:
            tenant_ctx_for_failure = TenantContext(
                tenant_id=str(tenant_id or f"installation:{installation_id}"),
                installation_id=str(installation_id),
            )

        for attempt in range(1, self.max_attempts + 1):
            try:
                if event.get("action") == "noop":
                    self.state["deduped"] += 1
                    return
                self._deliver(event)
                return
            except Exception as exc:
                self.state["last_error"] = str(exc)
                if attempt < self.max_attempts:
                    time.sleep((self.retry_base_delay_ms * (2 ** (attempt - 1))) / 1000.0)
                else:
                    self.state["failed"] += 1
                    status_code = None
                    if isinstance(exc, requests.HTTPError) and exc.response is not None:
                        status_code = exc.response.status_code
                    tenant_marker = event.get("tenant_id") or ((event.get("tenant") or {}).get("id"))
                    if tenant_marker:
                        self._tenant_record_failure(str(tenant_marker))
                    self._record_failed_attempt(
                        event,
                        event.get("action") or "create_comment",
                        str(exc),
                        status_code,
                        tenant_ctx_for_failure,
                    )
                    self._publish_dlq(event, str(exc))

    def _run(self):
        self.state["running"] = True
        try:
            if not self.app_id or not os.path.exists(self.private_key_path):
                self.state["last_error"] = "GitHub bridge credentials not configured"
                return

            self._ensure_schema()

            self._consumer = KafkaConsumer(
                self.input_topic,
                bootstrap_servers=self.kafka_brokers,
                group_id=self.consumer_group,
                enable_auto_commit=True,
                auto_offset_reset="latest",
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
                consumer_timeout_ms=1000,
            )
            self._producer = KafkaProducer(bootstrap_servers=self.kafka_brokers)

            while not self._stop.is_set():
                batch = self._consumer.poll(timeout_ms=1000, max_records=50)
                for records in batch.values():
                    for record in records:
                        self.state["processed"] += 1
                        self.state["last_processed_at"] = datetime.now(timezone.utc).isoformat()
                        self._handle_message(record.value)
        except Exception as exc:
            self.state["last_error"] = str(exc)
            try:
                self.log.exception("github bridge loop crashed")
            except Exception:
                pass
        finally:
            self.state["running"] = False
            if self._consumer:
                try:
                    self._consumer.close()
                except Exception:
                    pass
            if self._producer:
                try:
                    self._producer.close()
                except Exception:
                    pass

    def start(self):
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="github-bridge")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def health(self) -> Dict[str, Any]:
        return {
            **self.state,
            "topic_in": self.input_topic,
            "topic_dlq": self.dlq_topic,
            "consumer_group": self.consumer_group,
            "target_repo": self.target_repo,
            "configured": bool(self.app_id and os.path.exists(self.private_key_path)),
            "webhook_signature_enabled": bool(self.webhook_secret),
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_cooldown_sec": self.circuit_cooldown_sec,
        }

    def upsert_tenant_installation(
        self,
        tenant_id: str,
        repo_full_name: str,
        installation_id: str,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._ensure_schema()
        normalized_tenant = tenant_id.strip()
        normalized_repo = repo_full_name.strip()
        normalized_installation = str(installation_id).strip()
        stored_metadata = self._encrypt_metadata(metadata or {})

        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO meta.tenant_installations (tenant_id, repo_full_name, installation_id, enabled, metadata, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb,NOW(),NOW())
                    ON CONFLICT (tenant_id, repo_full_name)
                    DO UPDATE SET
                      installation_id = EXCLUDED.installation_id,
                      enabled = EXCLUDED.enabled,
                      metadata = EXCLUDED.metadata,
                      updated_at = NOW()
                    RETURNING id, tenant_id, repo_full_name, installation_id, enabled, metadata, created_at, updated_at
                    """,
                    (
                        normalized_tenant,
                        normalized_repo,
                        normalized_installation,
                        enabled,
                        json.dumps(stored_metadata),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            out = dict(row)
            out["metadata"] = self._decrypt_metadata(out.get("metadata") or {})
            return out

    def list_tenant_installations(self, tenant_id: Optional[str] = None) -> list[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if tenant_id:
                    cur.execute(
                        """
                        SELECT id, tenant_id, repo_full_name, installation_id, enabled, metadata, created_at, updated_at
                        FROM meta.tenant_installations
                        WHERE tenant_id = %s
                        ORDER BY updated_at DESC
                        """,
                        (tenant_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, tenant_id, repo_full_name, installation_id, enabled, metadata, created_at, updated_at
                        FROM meta.tenant_installations
                        ORDER BY updated_at DESC
                        """
                    )
                rows = cur.fetchall()
            items = [dict(r) for r in rows]
            for item in items:
                item["metadata"] = self._decrypt_metadata(item.get("metadata") or {})
            return items
