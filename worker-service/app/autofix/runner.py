"""
KA-CHOW Self-Healing Autofix Runner — LLM-Powered Patch Generation.

Replaces stub-only job creation with:
  1. LLM-powered code patch generation (unified diffs)
  2. LLM-powered documentation fix generation
  3. Confidence scoring and reasoning chains
  4. Fix persistence to PostgreSQL
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ..llm import get_llm_client
from ..llm.prompts import AutofixPrompt

log = logging.getLogger("ka-chow.autofix")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_ENSURE_SQL = """
CREATE SCHEMA IF NOT EXISTS meta;
CREATE TABLE IF NOT EXISTS meta.autofix_runs (
    id              BIGSERIAL PRIMARY KEY,
    repo            TEXT NOT NULL,
    pr_number       BIGINT,
    fix_type        TEXT NOT NULL,        -- code_fix | doc_fix | contract_fix
    finding_id      TEXT,
    graph_node_ids  JSONB NOT NULL DEFAULT '[]', -- Neo4j entity IDs this fix is traced to
    patches         JSONB NOT NULL DEFAULT '[]',
    confidence      FLOAT DEFAULT 0,
    reasoning       TEXT,
    risk_level      TEXT DEFAULT 'medium',
    status          TEXT NOT NULL DEFAULT 'generated',  -- generated | applied | pr_created | failed
    pr_url          TEXT,
    llm_model       TEXT,
    llm_tokens      INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE IF EXISTS meta.autofix_runs
    ADD COLUMN IF NOT EXISTS graph_node_ids JSONB NOT NULL DEFAULT '[]';
CREATE INDEX IF NOT EXISTS idx_autofix_repo ON meta.autofix_runs (repo);
"""


def _ensure_schema(pg_cfg: Dict[str, Any]) -> None:
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(_ENSURE_SQL)
            conn.commit()
    except Exception as exc:
        log.warning("Autofix schema setup failed: %s", exc)


def _derive_graph_node_ids(finding: Dict[str, Any]) -> List[str]:
    """
    Derive Neo4j graph node IDs from a finding's entity_refs.

    entity_refs follow the format used in graph_mapper.py:
      - service:<repo>:<name>
      - endpoint:<service_id>:<METHOD>:<path>
    We pass them through as-is since they are the stable graph node IDs.
    """
    refs = finding.get("entity_refs") or []
    return [str(r) for r in refs if r]


def _persist_fix(
    pg_cfg: Dict[str, Any],
    *,
    repo: str,
    pr_number: Optional[int],
    fix_type: str,
    finding_id: Optional[str],
    graph_node_ids: List[str],
    patches: List[Dict[str, Any]],
    confidence: float,
    reasoning: str,
    risk_level: str,
    llm_model: str,
    llm_tokens: int,
) -> int:
    """Persist a generated fix. Returns row ID."""
    _ensure_schema(pg_cfg)
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.autofix_runs
                        (repo, pr_number, fix_type, finding_id, graph_node_ids, patches,
                         confidence, reasoning, risk_level, status, llm_model, llm_tokens, created_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, 'generated', %s, %s, NOW())
                    RETURNING id
                    """,
                    (
                        repo, pr_number, fix_type, finding_id,
                        json.dumps(graph_node_ids),
                        json.dumps(patches), confidence, reasoning,
                        risk_level, llm_model, llm_tokens,
                    ),
                )
                row_id = cur.fetchone()[0]
            conn.commit()
        return int(row_id)
    except Exception as exc:
        log.warning("Autofix persistence failed: %s", exc)
        return -1


def _update_fix_status(
    pg_cfg: Dict[str, Any], fix_id: int, status: str, pr_url: Optional[str] = None
) -> None:
    """Update a fix run's status (e.g., after PR creation)."""
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                if pr_url:
                    cur.execute(
                        "UPDATE meta.autofix_runs SET status = %s, pr_url = %s WHERE id = %s",
                        (status, pr_url, fix_id),
                    )
                else:
                    cur.execute(
                        "UPDATE meta.autofix_runs SET status = %s WHERE id = %s",
                        (status, fix_id),
                    )
            conn.commit()
    except Exception as exc:
        log.warning("Autofix status update failed: %s", exc)


# ---------------------------------------------------------------------------
# LLM-powered fix generation
# ---------------------------------------------------------------------------

def generate_code_fix(
    finding: Dict[str, Any],
    *,
    code_context: Optional[str] = None,
    file_path: Optional[str] = None,
    repo: str,
    pr_number: Optional[int] = None,
    pg_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a code fix for a policy finding using LLM.

    Returns a dict with patches, confidence, reasoning, and risk assessment.
    """
    llm = get_llm_client()

    prompt = AutofixPrompt.user_prompt(
        finding=finding,
        code_context=code_context,
        file_path=file_path,
    )

    try:
        resp = llm.generate(
            prompt,
            system_prompt=AutofixPrompt.system_prompt,
            json_mode=True,
            json_schema=AutofixPrompt.response_schema(),
            temperature=0.2,
            use_cache=False,
        )
        result = resp.as_json()
        if not isinstance(result, dict):
            result = {"patches": [], "confidence": 0.0, "reasoning": str(result)}

        llm_model = resp.model
        llm_tokens = resp.input_tokens + resp.output_tokens
    except Exception as exc:
        log.error("Code fix generation failed: %s", exc)
        result = {
            "patches": [],
            "confidence": 0.0,
            "reasoning": f"LLM call failed: {exc}",
            "risk_level": "high",
        }
        llm_model = "error"
        llm_tokens = 0

    # Persist
    fix_id = -1
    if pg_cfg:
        graph_node_ids = _derive_graph_node_ids(finding)
        fix_id = _persist_fix(
            pg_cfg,
            repo=repo,
            pr_number=pr_number,
            fix_type="code_fix",
            finding_id=finding.get("rule_id"),
            graph_node_ids=graph_node_ids,
            patches=result.get("patches", []),
            confidence=float(result.get("confidence", 0)),
            reasoning=result.get("reasoning", ""),
            risk_level=result.get("risk_level", "medium"),
            llm_model=llm_model,
            llm_tokens=llm_tokens,
        )

    result["_meta"] = {
        "fix_id": fix_id,
        "fix_type": "code_fix",
        "graph_node_ids": graph_node_ids if pg_cfg else _derive_graph_node_ids(finding),
        "llm_model": llm_model,
        "llm_tokens": llm_tokens,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def generate_doc_fix(
    finding: Dict[str, Any],
    *,
    current_doc: Optional[str] = None,
    repo: str,
    pr_number: Optional[int] = None,
    pg_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a documentation fix for a policy finding using LLM.
    """
    llm = get_llm_client()

    prompt = json.dumps({
        "finding": finding,
        "current_documentation": (current_doc or "")[:5000],
        "task": (
            "Generate corrected documentation that addresses this finding. "
            "Include: the updated content in Markdown, explanation of changes, "
            "and a confidence score."
        ),
    })

    try:
        resp = llm.generate(
            prompt,
            system_prompt=(
                "You are a technical writer fixing documentation issues. "
                "Generate clean, accurate documentation. Return JSON with fields: "
                "content (the new doc text), explanation, confidence (0-1)."
            ),
            json_mode=True,
            temperature=0.2,
        )
        result = resp.as_json()
        if not isinstance(result, dict):
            result = {"content": str(result), "explanation": "", "confidence": 0.3}

        llm_model = resp.model
        llm_tokens = resp.input_tokens + resp.output_tokens
    except Exception as exc:
        log.error("Doc fix generation failed: %s", exc)
        result = {
            "content": "",
            "explanation": f"Generation failed: {exc}",
            "confidence": 0.0,
        }
        llm_model = "error"
        llm_tokens = 0

    # Wrap as patches format for consistency
    patches = []
    if result.get("content"):
        patches.append({
            "file_path": finding.get("file_path", "docs/update.md"),
            "content": result["content"],
            "explanation": result.get("explanation", ""),
            "patch_type": "doc_fix",
        })

    # Persist
    fix_id = -1
    if pg_cfg:
        graph_node_ids = _derive_graph_node_ids(finding)
        fix_id = _persist_fix(
            pg_cfg,
            repo=repo,
            pr_number=pr_number,
            fix_type="doc_fix",
            finding_id=finding.get("rule_id"),
            graph_node_ids=graph_node_ids,
            patches=patches,
            confidence=float(result.get("confidence", 0)),
            reasoning=result.get("explanation", ""),
            risk_level="low",
            llm_model=llm_model,
            llm_tokens=llm_tokens,
        )

    result["_meta"] = {
        "fix_id": fix_id,
        "fix_type": "doc_fix",
        "graph_node_ids": graph_node_ids if pg_cfg else _derive_graph_node_ids(finding),
        "patches": patches,
        "llm_model": llm_model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def generate_contract_fix(
    finding: Dict[str, Any],
    *,
    base_spec: Optional[Dict[str, Any]] = None,
    head_spec: Optional[Dict[str, Any]] = None,
    repo: str,
    pr_number: Optional[int] = None,
    pg_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate an API contract fix (OpenAPI spec correction) using LLM.
    """
    llm = get_llm_client()

    prompt = json.dumps({
        "finding": finding,
        "base_spec": base_spec or {},
        "head_spec": head_spec or {},
        "task": (
            "Fix the API contract issue described in the finding. "
            "Generate: a corrected OpenAPI spec fragment, unified diff, "
            "and explanation of the breaking change resolution."
        ),
    })

    try:
        resp = llm.generate_json(
            prompt,
            system_prompt=(
                "You are an API contract specialist. Fix breaking changes while "
                "maintaining backward compatibility. Suggest versioning if needed."
            ),
        )
        if not isinstance(resp, dict):
            resp = {"fix": str(resp), "confidence": 0.3, "reasoning": ""}

        llm_model = llm.model
        llm_tokens = 0
    except Exception as exc:
        resp = {"fix": "", "confidence": 0.0, "reasoning": f"Failed: {exc}"}
        llm_model = "error"
        llm_tokens = 0

    patches = []
    if resp.get("fix"):
        patches.append({
            "file_path": "api/openapi.yaml",
            "content": resp["fix"],
            "explanation": resp.get("reasoning", ""),
            "patch_type": "contract_fix",
        })

    if pg_cfg:
        graph_node_ids = _derive_graph_node_ids(finding)
        _persist_fix(
            pg_cfg,
            repo=repo,
            pr_number=pr_number,
            fix_type="contract_fix",
            finding_id=finding.get("rule_id"),
            graph_node_ids=graph_node_ids,
            patches=patches,
            confidence=float(resp.get("confidence", 0)),
            reasoning=resp.get("reasoning", ""),
            risk_level=resp.get("risk_level", "medium"),
            llm_model=llm_model,
            llm_tokens=llm_tokens,
        )
        resp["_meta"] = {"graph_node_ids": graph_node_ids}

    resp["patches"] = patches
    return resp


def list_fixes(
    pg_cfg: Dict[str, Any],
    *,
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    fix_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """List past autofix runs."""
    _ensure_schema(pg_cfg)
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, repo, pr_number, fix_type, finding_id, graph_node_ids,
                           patches, confidence, reasoning, risk_level, status, pr_url,
                           llm_model, llm_tokens, created_at
                    FROM meta.autofix_runs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                      AND (%s IS NULL OR fix_type = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (repo, repo, pr_number, pr_number, fix_type, fix_type, min(limit, 100)),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    for k, v in r.items():
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                return rows
    except Exception as exc:
        log.warning("Autofix listing failed: %s", exc)
        return []
