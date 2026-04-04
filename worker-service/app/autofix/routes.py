
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Request, HTTPException, status
from psycopg2.extras import RealDictCursor
import json

from ..dependencies import (
    get_db_conn, PG_CFG, auth_autofix_scoped,
    audit_event, enforce_repo_scope, AuthContext
)
from ..architecture.graph_integration import persist_autofix_graph_node

router = APIRouter()

from ..autofix.runner import (
    generate_code_fix,
    generate_doc_fix,
    generate_contract_fix,
    list_fixes,
    _update_fix_status,
)
from ..autofix.github_pr import GitHubPRCreator


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AutofixGenerateRequest(BaseModel):
    repo: str
    finding: dict
    fix_type: str = Field(default="code_fix", description="code_fix|doc_fix|contract_fix")
    code_context: Optional[str] = None
    file_path: Optional[str] = None
    pr_number: Optional[int] = None


class AutofixApplyRequest(BaseModel):
    repo: str
    finding: dict
    fix_type: str = Field(default="code_fix")
    code_context: Optional[str] = None
    file_path: Optional[str] = None
    pr_number: Optional[int] = None
    base_branch: str = Field(default="main")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/autofix/generate")
def autofix_generate(
    request: AutofixGenerateRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_autofix_scoped),
):
    """Generate an autofix without applying it (dry run)."""
    enforce_repo_scope(auth, request.repo)

    if request.fix_type == "doc_fix":
        result = generate_doc_fix(
            request.finding,
            current_doc=request.code_context,
            repo=request.repo,
            pr_number=request.pr_number,
            pg_cfg=PG_CFG,
        )
    elif request.fix_type == "contract_fix":
        result = generate_contract_fix(
            request.finding,
            repo=request.repo,
            pr_number=request.pr_number,
            pg_cfg=PG_CFG,
        )
    else:
        result = generate_code_fix(
            request.finding,
            code_context=request.code_context,
            file_path=request.file_path,
            repo=request.repo,
            pr_number=request.pr_number,
            pg_cfg=PG_CFG,
        )

    audit_event(
        actor=auth.subject,
        action="autofix_generate",
        result={"status": "success", "fix_type": request.fix_type},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo},
    )
    return result


@router.post("/autofix/apply")
def autofix_apply(
    request: AutofixApplyRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_autofix_scoped),
):
    """Generate an autofix AND create a GitHub PR."""
    enforce_repo_scope(auth, request.repo)

    # Step 1: Generate fix
    if request.fix_type == "doc_fix":
        result = generate_doc_fix(
            request.finding,
            current_doc=request.code_context,
            repo=request.repo,
            pr_number=request.pr_number,
            pg_cfg=PG_CFG,
        )
    elif request.fix_type == "contract_fix":
        result = generate_contract_fix(
            request.finding,
            repo=request.repo,
            pr_number=request.pr_number,
            pg_cfg=PG_CFG,
        )
    else:
        result = generate_code_fix(
            request.finding,
            code_context=request.code_context,
            file_path=request.file_path,
            repo=request.repo,
            pr_number=request.pr_number,
            pg_cfg=PG_CFG,
        )

    patches = result.get("patches", [])
    if not patches:
        return {**result, "pr_created": False, "reason": "No patches generated"}

    # Step 2: Create PR
    pr_creator = GitHubPRCreator()
    pr_result = pr_creator.create_fix_pr(
        repo=request.repo,
        patches=patches,
        finding_id=request.finding.get("rule_id", "unknown"),
        fix_type=request.fix_type,
        pr_number=request.pr_number,
        base_branch=request.base_branch,
        graph_node_ids=result.get("_meta", {}).get("graph_node_ids", []),
    )

    # Step 3: Update fix status + persist graph traceability
    fix_id = result.get("_meta", {}).get("fix_id")
    graph_node_ids = result.get("_meta", {}).get("graph_node_ids", [])
    if fix_id and fix_id > 0:
        if pr_result.get("success"):
            _update_fix_status(PG_CFG, fix_id, "pr_created", pr_result.get("pr_url"))
            # Trace fix back to Neo4j knowledge graph nodes
            try:
                from neo4j import GraphDatabase
                import os
                driver = GraphDatabase.driver(
                    os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
                    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "testtest")),
                )
                persist_autofix_graph_node(
                    driver,
                    fix_id=fix_id,
                    repo=request.repo,
                    finding_id=request.finding.get("rule_id", "unknown"),
                    fix_type=request.fix_type,
                    graph_node_ids=graph_node_ids,
                    pr_url=pr_result.get("pr_url", ""),
                    confidence=float(result.get("confidence", 0)),
                )
                driver.close()
            except Exception:
                pass  # graph traceability is best-effort
        else:
            _update_fix_status(PG_CFG, fix_id, "failed")

    audit_event(
        actor=auth.subject,
        action="autofix_apply",
        result={
            "status": "success" if pr_result.get("success") else "failed",
            "pr_url": pr_result.get("pr_url"),
        },
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo},
    )

    return {**result, "pr_result": pr_result}


@router.get("/autofix/history")
def autofix_history(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    fix_type: Optional[str] = None,
    limit: int = 20,
    auth: AuthContext = Depends(auth_autofix_scoped),
):
    """List past autofix runs."""
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    runs = list_fixes(PG_CFG, repo=repo, pr_number=pr_number, fix_type=fix_type, limit=limit)
    return {"items": runs, "total": len(runs)}
