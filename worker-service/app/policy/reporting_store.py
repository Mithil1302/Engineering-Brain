import json
import logging
import os
from typing import Callable, Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from psycopg2.extras import RealDictCursor

class ReportingStore:
    def __init__(self, db_conn_func, *, ensure_schema: Callable[[], None] = lambda: None):
        self._db_conn = db_conn_func
        self._ensure_schema = ensure_schema
        self.log = logging.getLogger('worker-service')

        # Backlog tracking state (used by emit_retry_metrics)
        self._last_backlog_count: Optional[int] = None
        self._last_backlog_sampled_at: Optional[datetime] = None

        # Alert thresholds (configurable via env vars)
        self.emit_alert_failure_rate_threshold_pct = float(os.getenv("EMIT_ALERT_FAILURE_RATE_THRESHOLD_PCT", "25"))
        self.emit_alert_backlog_growth_delta = int(os.getenv("EMIT_ALERT_BACKLOG_GROWTH_DELTA", "10"))
        self.emit_alert_backlog_threshold = int(os.getenv("EMIT_ALERT_BACKLOG_THRESHOLD", "50"))
        self.emit_alert_backlog_oldest_age_sec = float(os.getenv("EMIT_ALERT_BACKLOG_OLDEST_AGE_SEC", "300"))
        self.emit_alert_delivery_failures_threshold = int(os.getenv("EMIT_ALERT_DELIVERY_FAILURES_THRESHOLD", "5"))

    def list_doc_rewrite_runs(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        limit: int = 50,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.doc_rewrite_runs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                      AND (%s IS NULL OR created_at >= %s)
                      AND (%s IS NULL OR created_at <= %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (
                        repo,
                        repo,
                        pr_number,
                        pr_number,
                        created_after,
                        created_after,
                        created_before,
                        created_before,
                        safe_limit,
                    ),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_health_snapshots(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        limit: int = 50,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           correlation_id,
                           idempotency_key,
                           rule_set,
                           summary_status,
                           score::float8 AS score,
                           grade,
                           snapshot,
                           created_at
                    FROM meta.knowledge_health_snapshots
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                      AND (%s IS NULL OR created_at >= %s)
                      AND (%s IS NULL OR created_at <= %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (
                        repo,
                        repo,
                        pr_number,
                        pr_number,
                        created_after,
                        created_after,
                        created_before,
                        created_before,
                        safe_limit,
                    ),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_doc_refresh_jobs(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        limit: int = 50,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           correlation_id,
                           idempotency_key,
                           rule_set,
                           action,
                           decision,
                           priority,
                           plan,
                           created_at
                    FROM meta.doc_refresh_jobs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                      AND (%s IS NULL OR created_at >= %s)
                      AND (%s IS NULL OR created_at <= %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (
                        repo,
                        repo,
                        pr_number,
                        pr_number,
                        created_after,
                        created_after,
                        created_before,
                        created_before,
                        safe_limit,
                    ),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_emit_retry_jobs(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, job_type, idempotency_key, correlation_id, status, payload, created_at, updated_at
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND (%s IS NULL OR status = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (status, status, safe_limit),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_emit_retry_dead_letters(
        self,
        *,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, source_topic, source_partition, source_offset, error, attempts,
                           payload_raw, correlation_id, idempotency_key, status, requeue_count,
                           requeued_at, created_at, updated_at
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def emit_retry_overview(
        self,
        *,
        repo: Optional[str] = None,
        window_hours: int = 24,
    ) -> Dict[str, Any]:
        safe_window = max(1, min(window_hours, 24 * 30))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*)::int AS count
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    GROUP BY status
                    """,
                    (repo, repo),
                )
                status_counts = {str(r["status"]): int(r["count"]) for r in cur.fetchall()}

                cur.execute(
                    """
                    SELECT id, idempotency_key, correlation_id, status, payload, created_at, updated_at
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status IN ('queued', 'processing')
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (repo, repo),
                )
                oldest_inflight = cur.fetchone()

                cur.execute(
                    """
                    SELECT id, idempotency_key, correlation_id, status, payload, created_at, updated_at
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status IN ('dead_letter', 'queued')
                      AND payload ? 'last_error'
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    ORDER BY updated_at DESC
                    LIMIT 5
                    """,
                    (repo, repo),
                )
                recent_job_errors = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                      AND (%s IS NULL OR (payload_raw::jsonb)->>'repo' = %s)
                    """,
                    (repo, repo),
                )
                poison_total = int((cur.fetchone() or {}).get("c") or 0)

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                      AND status = 'requeued'
                      AND (%s IS NULL OR (payload_raw::jsonb)->>'repo' = %s)
                    """,
                    (repo, repo),
                )
                poison_requeued = int((cur.fetchone() or {}).get("c") or 0)

                cur.execute(
                    """
                    SELECT id, idempotency_key, error, attempts, status, requeue_count, created_at, updated_at
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                      AND (%s IS NULL OR (payload_raw::jsonb)->>'repo' = %s)
                    ORDER BY id DESC
                    LIMIT 5
                    """,
                    (repo, repo),
                )
                recent_poison = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status = 'completed'
                      AND updated_at >= NOW() - make_interval(hours => %s)
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (safe_window, repo, repo),
                )
                completed_window = int((cur.fetchone() or {}).get("c") or 0)

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status = 'dead_letter'
                      AND updated_at >= NOW() - make_interval(hours => %s)
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (safe_window, repo, repo),
                )
                dead_letter_window = int((cur.fetchone() or {}).get("c") or 0)

        success_rate = None
        denom = completed_window + dead_letter_window
        if denom > 0:
            success_rate = round((completed_window / denom) * 100.0, 2)

        return {
            "scope": {"repo": repo, "window_hours": safe_window},
            "queue": {
                "status_counts": status_counts,
                "oldest_inflight": dict(oldest_inflight) if oldest_inflight else None,
                "recent_job_errors": recent_job_errors,
            },
            "dead_letter": {
                "total": poison_total,
                "requeued": poison_requeued,
                "recent": recent_poison,
            },
            "window_metrics": {
                "completed": completed_window,
                "dead_lettered": dead_letter_window,
                "success_rate_percent": success_rate,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def emit_retry_metrics(
        self,
        *,
        repo: Optional[str] = None,
        window_minutes: int = 60,
        update_backlog_sample: bool = True,
    ) -> Dict[str, Any]:
        safe_window = max(1, min(window_minutes, 24 * 60))
        self._ensure_schema()

        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*)::int AS count
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    GROUP BY status
                    """,
                    (repo, repo),
                )
                status_counts = {str(r["status"]): int(r["count"]) for r in cur.fetchall()}

                cur.execute(
                    """
                    SELECT
                      COALESCE(COUNT(*),0)::int AS completed,
                      COALESCE(SUM(CASE WHEN status = 'dead_letter' THEN 1 ELSE 0 END),0)::int AS dead_lettered
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status IN ('completed','dead_letter')
                      AND updated_at >= NOW() - make_interval(mins => %s)
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (safe_window, repo, repo),
                )
                aggregate = cur.fetchone() or {}

                cur.execute(
                                        """
                    SELECT
                      COALESCE(
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (updated_at - created_at))),
                        0
                      )::float8 AS p50_sec,
                      COALESCE(
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (updated_at - created_at))),
                        0
                      )::float8 AS p95_sec
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status = 'completed'
                      AND updated_at >= NOW() - make_interval(mins => %s)
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (safe_window, repo, repo),
                )
                latency = cur.fetchone() or {}

                cur.execute(
                    """
                    SELECT
                      COALESCE(SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END),0)::int AS queued,
                      COALESCE(SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END),0)::int AS processing,
                      COALESCE(MIN(EXTRACT(EPOCH FROM (NOW() - created_at))),0)::float8 AS oldest_backlog_age_sec
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status IN ('queued','processing')
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (repo, repo),
                )
                backlog = cur.fetchone() or {}

                cur.execute(
                                        """
                    SELECT COALESCE(COUNT(*),0)::int AS delivery_failures
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status = 'dead_letter'
                      AND updated_at >= NOW() - make_interval(mins => %s)
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (safe_window, repo, repo),
                )
                delivery_failures_window = int((cur.fetchone() or {}).get("delivery_failures") or 0)

        completed_window = int(aggregate.get("completed") or 0)
        dead_letter_window = int(aggregate.get("dead_lettered") or 0)
        denom = completed_window + dead_letter_window
        failure_rate_pct = round((dead_letter_window / denom) * 100.0, 2) if denom > 0 else 0.0

        queued = int(backlog.get("queued") or 0)
        processing = int(backlog.get("processing") or 0)
        backlog_count = queued + processing
        oldest_backlog_age_sec = round(float(backlog.get("oldest_backlog_age_sec") or 0.0), 2)

        backlog_delta = None
        if self._last_backlog_count is not None:
            backlog_delta = backlog_count - self._last_backlog_count

        now = datetime.now(timezone.utc)
        if update_backlog_sample:
            self._last_backlog_count = backlog_count
            self._last_backlog_sampled_at = now

        alerts = {
            "failure_rate_spike": {
                "triggered": failure_rate_pct >= self.emit_alert_failure_rate_threshold_pct and denom >= 3,
                "value": failure_rate_pct,
                "threshold": self.emit_alert_failure_rate_threshold_pct,
            },
            "backlog_growth": {
                "triggered": (
                    (backlog_delta is not None and backlog_delta >= self.emit_alert_backlog_growth_delta)
                    or (backlog_count >= self.emit_alert_backlog_threshold and oldest_backlog_age_sec >= self.emit_alert_backlog_oldest_age_sec)
                ),
                "value": {
                    "backlog_count": backlog_count,
                    "backlog_delta": backlog_delta,
                    "oldest_backlog_age_sec": oldest_backlog_age_sec,
                },
                "threshold": {
                    "backlog_count": self.emit_alert_backlog_threshold,
                    "backlog_delta": self.emit_alert_backlog_growth_delta,
                    "oldest_backlog_age_sec": self.emit_alert_backlog_oldest_age_sec,
                },
            },
            "delivery_failures": {
                "triggered": delivery_failures_window >= self.emit_alert_delivery_failures_threshold,
                "value": delivery_failures_window,
                "threshold": self.emit_alert_delivery_failures_threshold,
            },
        }

        return {
            "scope": {"repo": repo, "window_minutes": safe_window},
            "status_counts": status_counts,
            "pipeline": {
                "success_count": completed_window,
                "error_count": dead_letter_window,
                "failure_rate_pct": failure_rate_pct,
                "delivery_failures_window": delivery_failures_window,
            },
            "latency": {
                "p50_sec": round(float(latency.get("p50_sec") or 0.0), 3),
                "p95_sec": round(float(latency.get("p95_sec") or 0.0), 3),
            },
            "backlog": {
                "queued": queued,
                "processing": processing,
                "total": backlog_count,
                "delta": backlog_delta,
                "oldest_age_sec": oldest_backlog_age_sec,
            },
            "alerts": alerts,
            "generated_at": now.isoformat(),
        }

    def emit_retry_alerts(
        self,
        *,
        repo: Optional[str] = None,
        window_minutes: int = 60,
        update_backlog_sample: bool = True,
    ) -> Dict[str, Any]:
        metrics = self.emit_retry_metrics(
            repo=repo,
            window_minutes=window_minutes,
            update_backlog_sample=update_backlog_sample,
        )
        return {
            "scope": metrics.get("scope"),
            "alerts": metrics.get("alerts"),
            "generated_at": metrics.get("generated_at"),
        }

    def dashboard_overview(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        window: int = 20,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        safe_window = max(1, min(window, 200))
        self._ensure_schema()

        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           rule_set,
                           summary_status,
                           score::float8 AS score,
                           grade,
                           snapshot,
                           created_at
                                        FROM meta.knowledge_health_snapshots
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                                            AND (%s IS NULL OR created_at >= %s)
                                            AND (%s IS NULL OR created_at <= %s)
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                                        (
                                                repo,
                                                repo,
                                                pr_number,
                                                pr_number,
                                                created_after,
                                                created_after,
                                                created_before,
                                                created_before,
                                        ),
                )
                latest = cur.fetchone()

                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           score::float8 AS score,
                           grade,
                           summary_status,
                           created_at
                    FROM meta.knowledge_health_snapshots
                                        WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                                            AND (%s IS NULL OR created_at >= %s)
                                            AND (%s IS NULL OR created_at <= %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                                        (
                                                repo,
                                                repo,
                                                pr_number,
                                                pr_number,
                                                created_after,
                                                created_after,
                                                created_before,
                                                created_before,
                                                safe_window,
                                        ),
                )
                trend_rows = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    """
                    SELECT decision, COUNT(*)::int AS count
                    FROM meta.doc_refresh_jobs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                                            AND (%s IS NULL OR created_at >= %s)
                                            AND (%s IS NULL OR created_at <= %s)
                    GROUP BY decision
                    """,
                                        (
                                                repo,
                                                repo,
                                                pr_number,
                                                pr_number,
                                                created_after,
                                                created_after,
                                                created_before,
                                                created_before,
                                        ),
                )
                doc_decisions = {str(r["decision"]): int(r["count"]) for r in cur.fetchall()}

                cur.execute(
                    """
                    SELECT action, COUNT(*)::int AS count
                    FROM meta.policy_check_runs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                                            AND (%s IS NULL OR created_at >= %s)
                                            AND (%s IS NULL OR created_at <= %s)
                    GROUP BY action
                    """,
                                        (
                                                repo,
                                                repo,
                                                pr_number,
                                                pr_number,
                                                created_after,
                                                created_after,
                                                created_before,
                                                created_before,
                                        ),
                )
                action_breakdown = {str(r["action"]): int(r["count"]) for r in cur.fetchall()}

        avg_score = round(sum(r["score"] for r in trend_rows) / len(trend_rows), 2) if trend_rows else None
        return {
            "scope": {
                "repo": repo,
                "pr_number": pr_number,
                "window": safe_window,
                "created_after": created_after.isoformat() if created_after else None,
                "created_before": created_before.isoformat() if created_before else None,
            },
            "latest_snapshot": dict(latest) if latest else None,
            "trend": trend_rows,
            "metrics": {
                "avg_score": avg_score,
                "trend_points": len(trend_rows),
                "doc_refresh_decisions": doc_decisions,
                "policy_actions": action_breakdown,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

