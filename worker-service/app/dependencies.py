import os
import sys
import json
import logging
import psycopg2
from typing import Optional
from datetime import datetime, timezone
from fastapi import Request, HTTPException, status, Depends
from .policy.pipeline import PolicyPipeline
from .security.authz import AuthContext, build_auth_dependency, enforce_repo_scope

from .llm import get_llm_client, get_embedding_client
from .llm.embeddings import EmbeddingStore
from .simulation.impact_analyzer import ImpactAnalyzer

log = logging.getLogger("worker-service")

# Initialize PG_CFG first as it's needed by multiple components
PG_CFG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "user": os.getenv("POSTGRES_USER", "brain"),
    "password": os.getenv("POSTGRES_PASSWORD", "brain"),
    "dbname": os.getenv("POSTGRES_DB", "brain"),
}

# Initialize ImpactAnalyzer
impact_analyzer = ImpactAnalyzer(
    graph_service_url=os.getenv("GRAPH_SERVICE_URL", "graph-service:50051"),
    pg_cfg=PG_CFG,
)

# Initialize PolicyPipeline with ImpactAnalyzer
pipeline = PolicyPipeline(log, impact_analyzer=impact_analyzer)


def validate_ingestion_env_vars():
    """
    Validate ingestion environment variables at startup.

    Variables needed for GitHub App repo crawling and Slack integration are
    optional at startup — missing values are logged as warnings so the service
    boots and the /ingestion/trigger endpoint is reachable.  The IngestionPipeline
    will surface a clear error in the background task if credentials are absent
    when an actual crawl is attempted.
    """
    # These are only needed for the GitHub App crawler — warn, do not crash.
    optional_github = [
        "GITHUB_APP_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_INSTALLATION_ID",
        "GITHUB_WEBHOOK_SECRET",
    ]
    # Slack adapter vars — warn, do not crash.
    optional_slack = [
        "SLACK_SIGNING_SECRET",
        "SLACK_BOT_TOKEN",
    ]

    missing = []
    for var in optional_github + optional_slack:
        if not os.getenv(var, "").strip():
            missing.append(var)

    if missing:
        log.warning(
            "Optional integration env vars not set: %s. "
            "GitHub crawling and Slack adapter will be unavailable until these are "
            "configured, but all other endpoints (including /ingestion/trigger) are "
            "fully operational.",
            ", ".join(missing),
        )
    else:
        log.info("All integration environment variables present.")

# LLM singletons — lazy-initialised on first access
llm_client = get_llm_client()
embedding_client = get_embedding_client()
embedding_store = EmbeddingStore(
    db_conn_factory=lambda: psycopg2.connect(**PG_CFG),
    embedding_client=embedding_client,
)

# Ingestion pipeline singleton (lazy-initialized)
_ingestion_pipeline: Optional["IngestionPipeline"] = None

def get_ingestion_pipeline():
    """Get or create the ingestion pipeline singleton."""
    global _ingestion_pipeline
    if _ingestion_pipeline is None:
        from .ingestion.ingestion_pipeline import IngestionPipeline
        from .ingestion.crawler import GitHubRepoCrawler
        from .ingestion.chunker import CodeChunker
        from .ingestion.service_detector import ServiceDetector, DependencyExtractor
        from .ingestion.graph_populator import GraphPopulator
        from .ingestion.embedding_populator import EmbeddingPopulator
        
        # Initialize components
        private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "")
        if private_key_path and os.path.exists(private_key_path):
            with open(private_key_path, 'r') as f:
                private_key = f.read()
        else:
            # Fallback to environment variable
            private_key = os.getenv("GITHUB_APP_PRIVATE_KEY", "")

        crawler = GitHubRepoCrawler(
            app_id=os.getenv("GITHUB_APP_ID", ""),
            private_key=private_key,
            installation_id=os.getenv("GITHUB_INSTALLATION_ID", ""),
            max_concurrent=int(os.getenv("INGESTION_MAX_CONCURRENT_FETCHES", "10")),
            max_file_size_kb=int(os.getenv("INGESTION_MAX_FILE_SIZE_KB", "500")),
        )
        
        chunker = CodeChunker(max_chunk_chars=2000)
        service_detector = ServiceDetector()
        dep_extractor = DependencyExtractor()
        
        graph_populator = GraphPopulator(
            graph_service_url=os.getenv("GRAPH_SERVICE_URL", "graph-service:50051"),
            pg_cfg=PG_CFG,
        )
        
        embedding_populator = EmbeddingPopulator(
            embedding_store=embedding_store,
            pg_cfg=PG_CFG,
            batch_size=int(os.getenv("INGESTION_BATCH_SIZE", "50")),
        )
        
        kafka_brokers = [
            b.strip() for b in os.getenv("KAFKA_BROKERS", "kafka:9092").split(",") if b.strip()
        ]
        
        _ingestion_pipeline = IngestionPipeline(
            crawler=crawler,
            chunker=chunker,
            service_detector=service_detector,
            dep_extractor=dep_extractor,
            graph_populator=graph_populator,
            embedding_populator=embedding_populator,
            pg_cfg=PG_CFG,
            kafka_brokers=kafka_brokers,
        )
    
    return _ingestion_pipeline

ADMIN_ROLES = {"platform-admin", "security-admin"}
ARCHITECT_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect"}
READ_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect", "developer", "sre"}
AUTOFIX_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect"}

def get_db_conn():
    return psycopg2.connect(**PG_CFG)

def audit_event(
    *,
    actor: str,
    action: str,
    result: dict,
    role: Optional[str] = None,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    entities: Optional[dict] = None,
    metadata: Optional[dict] = None,
):
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.audit_logs (timestamp, actor, action, correlation_id, request_id, entities, result, metadata)
                    VALUES (NOW(), %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    """,
                    (
                        actor,
                        action,
                        correlation_id,
                        request_id,
                        json.dumps(entities or {}),
                        json.dumps(result or {}),
                        json.dumps({"role": role, "tenant_id": tenant_id, **(metadata or {})}),
                    ),
                )
            conn.commit()
    except Exception:
        pass

def audit_denied(request: Request, ctx: Optional[AuthContext], detail: str, status_code: int):
    audit_event(
        actor=(ctx.subject if ctx else "unknown"),
        action="authz_denied",
        result={"status": "denied", "status_code": status_code, "detail": detail},
        role=(ctx.role if ctx else None),
        tenant_id=(ctx.tenant_id if ctx else None),
        correlation_id=request.headers.get("x-correlation-id"),
        request_id=request.headers.get("x-request-id"),
        entities={"path": str(request.url.path), "method": request.method},
        metadata={"query": dict(request.query_params)},
    )

def repo_from_query(request: Request) -> Optional[str]:
    repo = request.query_params.get("repo")
    return repo.strip() if repo else None

def parse_optional_ts(value: Optional[str], *, field_name: str) -> Optional[datetime]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid ISO-8601 datetime",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


auth_admin = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=ADMIN_ROLES,
    require_auth=True,
    on_denied=audit_denied,
)

auth_read_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=READ_ROLES,
    require_auth=True,
    repo_getter=repo_from_query,
    on_denied=audit_denied,
)

auth_arch_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=ARCHITECT_ROLES,
    require_auth=True,
    repo_getter=repo_from_query,
    on_denied=audit_denied,
)

auth_autofix_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=AUTOFIX_ROLES,
    require_auth=True,
    repo_getter=repo_from_query,
    on_denied=audit_denied,
)
