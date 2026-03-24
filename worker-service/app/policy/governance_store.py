from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from psycopg2.extras import RealDictCursor


class PolicyGovernanceStore:
    def __init__(
        self,
        *,
        db_conn_factory: Callable[[], Any],
        ensure_schema: Callable[[], None],
        resolve_policy_pack_fn: Callable[[str], Any],
    ):
        self._db_conn_factory = db_conn_factory
        self._ensure_schema = ensure_schema
        self._resolve_policy_pack = resolve_policy_pack_fn

    def _db_conn(self):
        return self._db_conn_factory()

    def _expire_due_waivers(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE meta.policy_waivers
                SET status = 'expired', updated_at = NOW()
                WHERE status IN ('pending','approved')
                  AND expires_at < NOW()
                """
            )

    def upsert_policy_template(
        self,
        *,
        template_name: str,
        scope_type: str,
        scope_value: str,
        rule_pack: Optional[str],
        rules: Dict[str, Any],
        fail_blocks_merge: bool,
        warn_blocks_merge: bool,
        no_docs_no_merge: bool,
        metadata: Optional[Dict[str, Any]],
        enabled: bool,
        priority: int,
    ) -> Dict[str, Any]:
        self._ensure_schema()
        st = scope_type.strip().lower()
        if st not in {"org", "team", "repo"}:
            raise ValueError("scope_type must be one of: org, team, repo")

        if rule_pack:
            self._resolve_policy_pack(rule_pack)

        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO meta.policy_templates (
                      template_name, scope_type, scope_value, rule_pack, rules,
                      fail_blocks_merge, warn_blocks_merge, no_docs_no_merge,
                      metadata, enabled, priority, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,NOW(),NOW())
                    ON CONFLICT (scope_type, scope_value, template_name)
                    DO UPDATE SET
                      rule_pack = EXCLUDED.rule_pack,
                      rules = EXCLUDED.rules,
                      fail_blocks_merge = EXCLUDED.fail_blocks_merge,
                      warn_blocks_merge = EXCLUDED.warn_blocks_merge,
                      no_docs_no_merge = EXCLUDED.no_docs_no_merge,
                      metadata = EXCLUDED.metadata,
                      enabled = EXCLUDED.enabled,
                      priority = EXCLUDED.priority,
                      updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        template_name.strip(),
                        st,
                        scope_value.strip(),
                        rule_pack,
                        json.dumps(rules or {}),
                        fail_blocks_merge,
                        warn_blocks_merge,
                        no_docs_no_merge,
                        json.dumps(metadata or {}),
                        enabled,
                        int(priority),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row)

    def list_policy_templates(
        self,
        *,
        scope_type: Optional[str] = None,
        scope_value: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_templates
                    WHERE (%s IS NULL OR scope_type = %s)
                      AND (%s IS NULL OR scope_value = %s)
                      AND (%s IS NULL OR enabled = %s)
                    ORDER BY scope_type, scope_value, priority ASC, updated_at DESC
                    """,
                    (scope_type, scope_type, scope_value, scope_value, enabled, enabled),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def resolve_effective_policy_template(
        self,
        *,
        repo: str,
        team: Optional[str] = None,
        org: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        org_value = (org or "").strip() or None
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_templates
                    WHERE enabled = TRUE
                      AND (
                        (scope_type = 'repo' AND scope_value = %s)
                        OR (%s IS NOT NULL AND scope_type = 'team' AND scope_value = %s)
                        OR (scope_type = 'org' AND (%s IS NULL AND scope_value = '*' OR %s IS NOT NULL AND (scope_value = %s OR scope_value = '*')))
                      )
                    ORDER BY
                      CASE scope_type
                        WHEN 'repo' THEN 3
                        WHEN 'team' THEN 2
                        WHEN 'org' THEN 1
                        ELSE 0
                      END DESC,
                      priority ASC,
                      updated_at DESC
                    LIMIT 1
                    """,
                    (repo, team, team, org_value, org_value, org_value),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_waiver_request(
        self,
        *,
        repo: str,
        pr_number: int,
        rule_set: str,
        requested_by: str,
        requested_role: str,
        reason: str,
        expires_at: str,
        required_approvals: int,
        approval_chain: List[str],
        scope: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._ensure_schema()
        self._resolve_policy_pack(rule_set)
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO meta.policy_waivers (
                      repo, pr_number, rule_set, requested_by, requested_role, reason,
                      status, expires_at, required_approvals, approval_chain, scope, metadata,
                      requested_at, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,NOW(),NOW(),NOW())
                    RETURNING *
                    """,
                    (
                        repo,
                        pr_number,
                        rule_set,
                        requested_by,
                        requested_role,
                        reason,
                        expires_at,
                        max(1, int(required_approvals)),
                        json.dumps(approval_chain or []),
                        json.dumps(scope or {}),
                        json.dumps(metadata or {}),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row)

    def decide_waiver(
        self,
        *,
        waiver_id: int,
        decision: str,
        approver: str,
        approver_role: str,
        notes: Optional[str],
    ) -> Dict[str, Any]:
        self._ensure_schema()
        d = decision.strip().lower()
        if d not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")

        with self._db_conn() as conn:
            conn.autocommit = False
            self._expire_due_waivers(conn)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM meta.policy_waivers WHERE id = %s FOR UPDATE", (waiver_id,))
                waiver = cur.fetchone()
                if waiver is None:
                    raise ValueError("waiver not found")

                if waiver["status"] in {"rejected", "expired"}:
                    raise ValueError(f"waiver cannot be updated from status={waiver['status']}")

                cur.execute(
                    """
                    INSERT INTO meta.policy_waiver_approvals (waiver_id, approver, approver_role, decision, notes, created_at)
                    VALUES (%s,%s,%s,%s,%s,NOW())
                    """,
                    (waiver_id, approver, approver_role, d, notes),
                )

                if d == "reject":
                    cur.execute(
                        """
                        UPDATE meta.policy_waivers
                        SET status = 'rejected',
                            decided_at = NOW(),
                            decided_by = %s,
                            decided_role = %s,
                            decision_notes = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (approver, approver_role, notes, waiver_id),
                    )
                    out = cur.fetchone()
                    conn.commit()
                    return dict(out)

                cur.execute(
                    """
                    SELECT COUNT(DISTINCT approver_role)::int AS c
                    FROM meta.policy_waiver_approvals
                    WHERE waiver_id = %s AND decision = 'approve'
                    """,
                    (waiver_id,),
                )
                approved_role_count = int(cur.fetchone()["c"])
                required = int(waiver.get("required_approvals") or 1)
                new_status = "approved" if approved_role_count >= required else "pending"

                cur.execute(
                    """
                    UPDATE meta.policy_waivers
                    SET status = %s,
                        decided_at = CASE WHEN %s = 'approved' THEN NOW() ELSE decided_at END,
                        decided_by = CASE WHEN %s = 'approved' THEN %s ELSE decided_by END,
                        decided_role = CASE WHEN %s = 'approved' THEN %s ELSE decided_role END,
                        decision_notes = CASE WHEN %s = 'approved' THEN %s ELSE decision_notes END,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (new_status, new_status, new_status, approver, new_status, approver_role, new_status, notes, waiver_id),
                )
                out = cur.fetchone()
            conn.commit()
        return dict(out)

    def list_waivers(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            conn.autocommit = False
            self._expire_due_waivers(conn)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_waivers
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                      AND (%s IS NULL OR status = %s)
                    ORDER BY id DESC
                    """,
                    (repo, repo, pr_number, pr_number, status, status),
                )
                rows = cur.fetchall()
            conn.commit()
        return [dict(r) for r in rows]

    def get_waiver_history(self, *, waiver_id: int) -> Dict[str, Any]:
        self._ensure_schema()
        with self._db_conn() as conn:
            conn.autocommit = False
            self._expire_due_waivers(conn)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM meta.policy_waivers WHERE id = %s", (waiver_id,))
                waiver = cur.fetchone()
                if waiver is None:
                    raise ValueError("waiver not found")

                cur.execute(
                    """
                    SELECT id, waiver_id, approver, approver_role, decision, notes, created_at
                    FROM meta.policy_waiver_approvals
                    WHERE waiver_id = %s
                    ORDER BY id ASC
                    """,
                    (waiver_id,),
                )
                approvals = [dict(r) for r in cur.fetchall()]
            conn.commit()

        return {
            "waiver": dict(waiver),
            "decisions": approvals,
        }

    def get_active_waiver(
        self,
        *,
        repo: str,
        pr_number: int,
        rule_set: str,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            conn.autocommit = False
            self._expire_due_waivers(conn)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_waivers
                    WHERE repo = %s
                      AND pr_number = %s
                      AND rule_set = %s
                      AND status = 'approved'
                      AND expires_at >= NOW()
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (repo, pr_number, rule_set),
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row) if row else None

    def list_policy_check_runs(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, repo, pr_number, summary_status, action, merge_gate, created_at
                    FROM meta.policy_check_runs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (repo, repo, pr_number, pr_number, safe_limit),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]
