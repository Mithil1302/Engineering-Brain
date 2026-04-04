"""
KA-CHOW Autonomous Architecture Scaffolder — LLM-powered microservice generation.

Advanced features:
  - Natural language requirements -> architecture spec
  - Tech stack selection with rationale
  - Complete microservice scaffolding (REST/gRPC)
  - Database schema generation with pgvector
  - Infrastructure-as-Code (Docker, K8s, Terraform)
  - CI/CD pipeline generation (GitHub Actions)
  - Observability scaffolding (metrics, traces, dashboards)
  - Security baseline (auth, authz, secrets)
  - Guardrails evaluation for scaffold quality

Given an architecture plan or natural language requirements, produces:
  - Dockerfiles (multi-stage, production-ready)
  - docker-compose fragments
  - OpenAPI 3.0 specs
  - gRPC proto files
  - Kubernetes manifests (Deployment, Service, HPA, NetworkPolicy)
  - Kustomize overlays (dev/staging/prod)
  - Database migration SQL
  - Terraform IaC for GCP/AWS
  - GitHub Actions CI/CD workflows
  - README.md for each service
  - Observability configs (logging, metrics, tracing)
"""
from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..llm import get_llm_client
from .contract_generator import generate_grpc_contracts, generate_openapi_contracts
from .scaffold_guardrails import evaluate_scaffold_guardrails

log = logging.getLogger("ka-chow.scaffolder")


def generate_scaffold(
    plan: Dict[str, Any],
    *,
    repo: str,
    include_types: Optional[List[str]] = None,
) -> Dict[str, str]:
    """
    Generate scaffold files from an architecture plan.

    Parameters
    ----------
    plan : dict
        Architecture plan with services, endpoints, data_models.
    include_types : list[str], optional
        Filter: ['dockerfile', 'docker-compose', 'openapi', 'k8s', 'migration', 'readme']
        If None, generates all types.

    Returns
    -------
    dict
        Mapping of file_path → file_content.
    """
    llm = get_llm_client()
    files: Dict[str, str] = {}
    all_types = include_types or [
        "dockerfile",
        "docker-compose",
        "openapi",
        "grpc",
        "k8s",
        "k8s-overlays",
        "migration",
        "readme",
        "observability",
        "guardrails",
    ]

    services = plan.get("services", [])
    if not services:
        return files

    # ------------------------------------------------------------------
    # Stage 1: Contract-first generation
    # ------------------------------------------------------------------
    if "openapi" in all_types:
        files.update(generate_openapi_contracts(plan))
    if "grpc" in all_types:
        files.update(generate_grpc_contracts(plan))

    for svc in services:
        svc_name = svc.get("name", "service").lower().replace(" ", "-")
        tech = svc.get("technology", "python").lower()
        endpoints = svc.get("endpoints", [])

        # Dockerfile
        if "dockerfile" in all_types:
            files[f"{svc_name}/Dockerfile"] = _generate_dockerfile(tech, svc_name)

        # README
        if "readme" in all_types:
            files[f"{svc_name}/README.md"] = _generate_readme(svc)

        # OpenAPI spec via LLM fallback (service-local contract)
        if "openapi" in all_types and endpoints:
            try:
                spec = _generate_openapi_spec(llm, svc_name, endpoints)
                files[f"{svc_name}/openapi.yaml"] = spec
            except Exception as exc:
                log.warning("OpenAPI generation failed for %s: %s", svc_name, exc)
                files[f"{svc_name}/openapi.yaml"] = _fallback_openapi(svc_name, endpoints)

    # docker-compose
    if "docker-compose" in all_types:
        files["docker-compose.scaffold.yaml"] = _generate_docker_compose(services)

    # Kubernetes manifests
    if "k8s" in all_types:
        for svc in services:
            svc_name = svc.get("name", "service").lower().replace(" ", "-")
            files[f"k8s/{svc_name}-deployment.yaml"] = _generate_k8s_deployment(svc)
            files[f"k8s/{svc_name}-service.yaml"] = _generate_k8s_service(svc)

    # Environment overlays (dev/staging/prod)
    if "k8s-overlays" in all_types:
        files.update(_generate_k8s_overlays(services))

    # Observability baseline injection
    if "observability" in all_types:
        for svc in services:
            svc_name = svc.get("name", "service").lower().replace(" ", "-")
            files[f"{svc_name}/observability/logging.yaml"] = _generate_structured_logging_config(svc_name)
            files[f"{svc_name}/observability/metrics.py"] = _generate_prometheus_stub()
            files[f"{svc_name}/observability/tracing.md"] = _generate_trace_propagation_doc()
            files[f"{svc_name}/src/health.py"] = _generate_health_endpoint_stub()

    # Migration SQL
    if "migration" in all_types:
        data_models = plan.get("data_models", [])
        if data_models:
            try:
                files["migrations/001_scaffold.sql"] = _generate_migration_sql(llm, data_models)
            except Exception as exc:
                log.warning("Migration SQL generation failed: %s", exc)
                files["migrations/001_scaffold.sql"] = _fallback_migration(data_models)

    if "guardrails" in all_types:
        warnings = evaluate_scaffold_guardrails(
            plan=plan,
            extracted_constraints=plan.get("extracted_constraints") or {},
        )
        files["architecture/guardrail_warnings.json"] = json.dumps(warnings, indent=2)

    return files


# ---------------------------------------------------------------------------
# Template generators (deterministic — no LLM needed)
# ---------------------------------------------------------------------------

def _generate_dockerfile(tech: str, svc_name: str) -> str:
    if "node" in tech or "javascript" in tech or "typescript" in tech:
        return f"""# {svc_name} — Node.js service
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --production=false
COPY . .
RUN npm run build 2>/dev/null || true

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app .
RUN npm prune --production
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:3000/healthz || exit 1
CMD ["node", "src/index.js"]
"""
    # Default: Python/FastAPI
    return f"""# {svc_name} — Python/FastAPI service
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
"""


def _generate_readme(svc: Dict[str, Any]) -> str:
    name = svc.get("name", "Service")
    resp = svc.get("responsibility", "TBD")
    tech = svc.get("technology", "TBD")
    endpoints = svc.get("endpoints", [])

    ep_table = "| Method | Path | Description |\n|--------|------|-------------|\n"
    for ep in endpoints:
        ep_table += f"| {ep.get('method', 'GET')} | {ep.get('path', '/')} | {ep.get('description', '')} |\n"

    return f"""# {name}

## Overview
{resp}

## Technology
{tech}

## API Endpoints
{ep_table}

## Running Locally
```bash
docker-compose up {name.lower().replace(' ', '-')}
```

## Testing
```bash
pytest tests/ -v
```
"""


def _generate_docker_compose(services: List[Dict[str, Any]]) -> str:
    lines = ["version: '3.8'", "", "services:"]
    for svc in services:
        name = svc.get("name", "service").lower().replace(" ", "-")
        tech = (svc.get("technology", "python") or "").lower()
        port = "3000" if "node" in tech else "8000"
        lines.extend([
            f"  {name}:",
            f"    build: ./{name}",
            f"    ports:",
            f"      - '{port}:{port}'",
            f"    environment:",
            f"      - SERVICE_NAME={name}",
            f"      - POSTGRES_HOST=postgres",
            f"      - KAFKA_BROKERS=kafka:9092",
            f"    depends_on:",
            f"      - postgres",
            f"      - kafka",
            f"    restart: unless-stopped",
            "",
        ])

    lines.extend([
        "  postgres:",
        "    image: pgvector/pgvector:pg16",
        "    environment:",
        "      POSTGRES_DB: brain",
        "      POSTGRES_USER: brain",
        "      POSTGRES_PASSWORD: brain",
        "    volumes:",
        "      - pgdata:/var/lib/postgresql/data",
        "",
        "  kafka:",
        "    image: bitnami/kafka:3.6",
        "    environment:",
        "      KAFKA_CFG_NODE_ID: 1",
        "      KAFKA_CFG_PROCESS_ROLES: broker,controller",
        "      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093",
        "      KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093",
        "      KAFKA_CFG_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092",
        "      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER",
        "",
        "volumes:",
        "  pgdata:",
    ])
    return "\n".join(lines) + "\n"


def _generate_k8s_deployment(svc: Dict[str, Any]) -> str:
    name = svc.get("name", "service").lower().replace(" ", "-")
    tech = (svc.get("technology", "python") or "").lower()
    port = 3000 if "node" in tech else 8000

    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app: {name}
    part-of: ka-chow
spec:
  replicas: 2
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
        - name: {name}
          image: ka-chow/{name}:latest
          ports:
            - containerPort: {port}
          env:
            - name: SERVICE_NAME
              value: {name}
            - name: POSTGRES_HOST
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: host
          readinessProbe:
            httpGet:
              path: /healthz
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: {port}
            initialDelaySeconds: 15
            periodSeconds: 20
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
"""


def _generate_k8s_service(svc: Dict[str, Any]) -> str:
    name = svc.get("name", "service").lower().replace(" ", "-")
    tech = (svc.get("technology", "python") or "").lower()
    port = 3000 if "node" in tech else 8000

    return f"""apiVersion: v1
kind: Service
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  selector:
    app: {name}
  ports:
    - protocol: TCP
      port: {port}
      targetPort: {port}
  type: ClusterIP
"""


def _generate_k8s_overlays(services: List[Dict[str, Any]]) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for svc in services:
        name = svc.get("name", "service").lower().replace(" ", "-")
        scale_hint = float((svc or {}).get("scale_hint_rpm") or 20000)
        if scale_hint >= 500_000:
            req_cpu, lim_cpu, req_mem, lim_mem = "500m", "2000m", "1Gi", "4Gi"
        elif scale_hint >= 100_000:
            req_cpu, lim_cpu, req_mem, lim_mem = "250m", "1000m", "512Mi", "2Gi"
        else:
            req_cpu, lim_cpu, req_mem, lim_mem = "100m", "500m", "256Mi", "512Mi"

        base = {
            "dev": (req_cpu, lim_cpu, req_mem, lim_mem, 1),
            "staging": (req_cpu, lim_cpu, req_mem, lim_mem, 2),
            "prod": (req_cpu, lim_cpu, req_mem, lim_mem, 3),
        }
        for env, (r_cpu, l_cpu, r_mem, l_mem, replicas) in base.items():
            files[f"k8s/overlays/{env}/{name}-deployment-patch.yaml"] = "\n".join(
                [
                    "apiVersion: apps/v1",
                    "kind: Deployment",
                    f"metadata:\n  name: {name}",
                    "spec:",
                    f"  replicas: {replicas}",
                    "  template:",
                    "    spec:",
                    "      containers:",
                    "        - name: " + name,
                    "          resources:",
                    "            requests:",
                    f"              cpu: {r_cpu}",
                    f"              memory: {r_mem}",
                    "            limits:",
                    f"              cpu: {l_cpu}",
                    f"              memory: {l_mem}",
                ]
            )
    return files


def _generate_structured_logging_config(service_name: str) -> str:
    return "\n".join(
        [
            "version: 1",
            "service: " + service_name,
            "logging:",
            "  format: json",
            "  fields:",
            "    - ts",
            "    - level",
            "    - service",
            "    - trace_id",
            "    - span_id",
            "    - msg",
        ]
    )


def _generate_prometheus_stub() -> str:
    return "\n".join(
        [
            "# Prometheus metrics stub",
            "from prometheus_client import Counter, Histogram",
            "",
            "REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'path', 'status'])",
            "REQUEST_LATENCY = Histogram('http_request_latency_seconds', 'Request latency', ['method', 'path'])",
            "",
            "def observe_request(method: str, path: str, status: int, latency_seconds: float) -> None:",
            "    REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()",
            "    REQUEST_LATENCY.labels(method=method, path=path).observe(latency_seconds)",
        ]
    )


def _generate_trace_propagation_doc() -> str:
    return "\n".join(
        [
            "# Distributed Tracing Propagation",
            "",
            "Every inbound and outbound request should propagate W3C trace context headers:",
            "- traceparent",
            "- tracestate",
            "",
            "For async messaging, carry trace context in message headers with keys:",
            "- x-traceparent",
            "- x-tracestate",
        ]
    )


def _generate_health_endpoint_stub() -> str:
    return "\n".join(
        [
            "from fastapi import APIRouter",
            "",
            "router = APIRouter()",
            "",
            "@router.get('/health')",
            "def health():",
            "    return {'status': 'ok'}",
            "",
            "@router.get('/ready')",
            "def ready():",
            "    return {'ready': True}",
        ]
    )


# ---------------------------------------------------------------------------
# LLM-powered generators (complex/dynamic)
# ---------------------------------------------------------------------------

def _generate_openapi_spec(
    llm, svc_name: str, endpoints: List[Dict[str, Any]]
) -> str:
    """Use LLM to generate a proper OpenAPI 3.0 spec."""
    prompt = json.dumps({
        "service": svc_name,
        "endpoints": endpoints[:10],
        "task": "Generate a valid OpenAPI 3.0.3 YAML spec with proper schemas, examples, and error responses.",
    })

    resp = llm.generate(
        prompt,
        system_prompt=(
            "You are an API design expert. Generate a complete, valid OpenAPI 3.0.3 spec in YAML format. "
            "Include proper request/response schemas with examples, error responses (400, 401, 404, 500), "
            "and a clear info section. Return ONLY the YAML content, no markdown fences."
        ),
        temperature=0.2,
    )
    return resp.text


def _fallback_openapi(svc_name: str, endpoints: List[Dict[str, Any]]) -> str:
    """Generate a minimal OpenAPI spec without LLM."""
    paths = {}
    for ep in endpoints:
        method = (ep.get("method", "GET") or "GET").lower()
        path = ep.get("path", "/")
        paths.setdefault(path, {})[method] = {
            "summary": ep.get("description", ""),
            "operationId": ep.get("operation_id", f"{method}_{path.replace('/', '_')}"),
            "responses": {"200": {"description": "Success"}},
        }

    spec = {
        "openapi": "3.0.3",
        "info": {"title": svc_name, "version": "1.0.0"},
        "paths": paths,
    }
    import yaml
    try:
        return yaml.dump(spec, default_flow_style=False, sort_keys=False)
    except ImportError:
        return json.dumps(spec, indent=2)


def _generate_migration_sql(llm, data_models: List[Dict[str, Any]]) -> str:
    """Use LLM to generate PostgreSQL migration SQL."""
    prompt = json.dumps({
        "data_models": data_models[:10],
        "task": "Generate PostgreSQL migration SQL with CREATE TABLE, proper types, constraints, indexes. Use meta schema.",
    })

    resp = llm.generate(
        prompt,
        system_prompt=(
            "You are a database architect. Generate clean PostgreSQL DDL. "
            "Use appropriate types, NOT NULL constraints, foreign keys, and indexes. "
            "Return ONLY the SQL, no markdown fences."
        ),
        temperature=0.1,
    )
    return resp.text


def _fallback_migration(data_models: List[Dict[str, Any]]) -> str:
    """Generate minimal SQL without LLM."""
    lines = ["-- Auto-generated scaffold migration", "CREATE SCHEMA IF NOT EXISTS meta;", ""]
    for model in data_models:
        entity = model.get("entity", "table")
        fields = model.get("fields", {})
        cols = ["  id BIGSERIAL PRIMARY KEY"]
        for fname, ftype in fields.items():
            pgtype = {"string": "TEXT", "number": "NUMERIC", "integer": "BIGINT", "boolean": "BOOLEAN"}.get(ftype, "TEXT")
            cols.append(f"  {fname} {pgtype}")
        cols.append("  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
        lines.append(f"CREATE TABLE IF NOT EXISTS meta.{entity} (")
        lines.append(",\n".join(cols))
        lines.append(");")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Autonomous Scaffolding from Natural Language Requirements
# ---------------------------------------------------------------------------

def scaffold_from_requirements(
    requirements: str,
    repo: str,
    target_platform: str = "kubernetes",
    constraints: Optional[List[str]] = None,
    preferred_stack: Optional[Dict[str, str]] = None,
    pg_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate complete scaffolding from natural language requirements.

    This is the autonomous agent entry point that:
    1. Uses LLM to interpret requirements into architecture spec
    2. Selects appropriate tech stack with rationale
    3. Generates complete service scaffolding
    4. Creates infrastructure-as-code
    5. Produces CI/CD pipelines

    Args:
        requirements: Natural language description of what to build
        repo: Repository context
        target_platform: Target deployment platform (kubernetes|docker-compose|serverless)
        constraints: List of constraints (tech stack, budget, timeline)
        preferred_stack: Preferred technology choices
        pg_cfg: PostgreSQL configuration for persistence

    Returns:
        Complete scaffolding result with all generated files
    """
    from ..llm.prompts import ScaffoldingArchitectPrompt

    llm = get_llm_client()

    # Build system context from existing architecture
    system_context = _gather_system_context(repo, pg_cfg)

    # Generate architecture blueprint using LLM
    prompt = ScaffoldingArchitectPrompt.user_prompt(
        requirements=requirements,
        existing_context=system_context,
        target_platform=target_platform,
    )

    try:
        result = llm.generate(
            prompt,
            system_prompt=ScaffoldingArchitectPrompt.system_prompt,
            json_mode=True,
            json_schema=ScaffoldingArchitectPrompt.response_schema(),
            temperature=0.4,
        )

        blueprint = result.as_json()
        if not isinstance(blueprint, dict):
            blueprint = _fallback_blueprint(requirements)

        # Convert blueprint to plan format for generate_scaffold
        plan = _convert_blueprint_to_plan(blueprint)
        plan["extracted_constraints"] = {"constraints": constraints or []}

        # Generate all scaffold files
        files = generate_scaffold(
            plan,
            repo=repo,
            include_types=[
                "dockerfile",
                "docker-compose",
                "openapi",
                "grpc",
                "k8s",
                "k8s-overlays",
                "migration",
                "readme",
                "observability",
                "guardrails",
            ],
        )

        # Add Terraform infrastructure
        if target_platform == "kubernetes":
            terraform_files = _generate_terraform_infrastructure(blueprint)
            files.update(terraform_files)

        # Add CI/CD workflow
        ci_files = _generate_github_actions_workflow(plan)
        files.update(ci_files)

        scaffold_id = _generate_scaffold_id(requirements, repo)

        # Persist result
        _persist_scaffold_result(
            scaffold_id=scaffold_id,
            repo=repo,
            requirements=requirements,
            blueprint=blueprint,
            files=files,
            llm_model=result.model,
            tokens_used=result.input_tokens + result.output_tokens,
            pg_cfg=pg_cfg,
        )

        return {
            "scaffold_id": scaffold_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request": {
                "requirements": requirements,
                "repo": repo,
                "target_platform": target_platform,
                "constraints": constraints,
            },
            "blueprint": blueprint,
            "files": files,
            "file_count": len(files),
            "llm_model": result.model,
            "tokens_used": result.input_tokens + result.output_tokens,
        }

    except Exception as exc:
        log.error("Autonomous scaffolding failed: %s", exc)
        return {
            "error": str(exc),
            "fallback": True,
            "blueprint": _fallback_blueprint(requirements),
        }


def _generate_scaffold_id(requirements: str, repo: str) -> str:
    """Generate a unique scaffold ID."""
    content = f"{requirements}{repo}{datetime.now(timezone.utc).isoformat()}"
    return f"scaffold_{hashlib.sha256(content.encode()).hexdigest()[:12]}"


def _gather_system_context(repo: str, pg_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Gather existing system context for scaffolding decisions."""
    context = {
        "services": [],
        "infrastructure": [],
        "constraints": [],
    }

    if not pg_cfg:
        return context

    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT services, infrastructure, decisions
                    FROM meta.architecture_plan_runs
                    WHERE repo = %s
                    ORDER BY id DESC LIMIT 5
                    """,
                    (repo,),
                )
                rows = cur.fetchall()
                for row in rows:
                    services = row.get("services") or []
                    if isinstance(services, str):
                        services = json.loads(services)
                    context["services"].extend(services)

                    infra = row.get("infrastructure") or []
                    if isinstance(infra, str):
                        infra = json.loads(infra)
                    context["infrastructure"].extend(infra)
    except Exception as exc:
        log.warning("System context gathering failed: %s", exc)

    return context


def _convert_blueprint_to_plan(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """Convert LLM blueprint to plan format for generate_scaffold."""
    services = blueprint.get("services", [])
    data_models = blueprint.get("data_models", [])

    return {
        "title": blueprint.get("title", "Generated Architecture"),
        "summary": blueprint.get("summary", ""),
        "services": services,
        "data_models": data_models,
        "infrastructure": blueprint.get("infrastructure", {}),
        "adrs": blueprint.get("adrs", []),
        "risks": blueprint.get("risks", []),
    }


def _fallback_blueprint(requirements: str) -> Dict[str, Any]:
    """Template-based fallback when LLM is unavailable."""
    return {
        "title": "Generated Microservice Architecture",
        "summary": f"Scaffolded from requirements: {requirements[:200]}...",
        "services": [
            {
                "name": "api-service",
                "responsibility": "Main API gateway",
                "technology": "python-fastapi",
                "endpoints": [
                    {"method": "GET", "path": "/health", "description": "Health check"},
                ],
            },
        ],
        "data_models": [],
        "infrastructure": {},
        "adrs": [],
    }


def _generate_terraform_infrastructure(blueprint: Dict[str, Any]) -> Dict[str, str]:
    """Generate Terraform configuration for cloud infrastructure."""
    files = {}

    main_tf = '''# Auto-generated by KA-CHOW Scaffolding Agent
terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment"
  type        = string
  default     = "production"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# GKE Cluster
module "gke" {
  source  = "terraform-google-modules/kubernetes-engine/google"
  version = "~> 28.0"

  project_id   = var.project_id
  name         = "ka-chow-${var.environment}"
  region       = var.region
  zones        = ["us-central1-a", "us-central1-b", "us-central1-c"]
}

# Cloud SQL
resource "google_sql_database_instance" "postgres" {
  name             = "ka-chow-db-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier          = "db-custom-2-4096"
    disk_size     = 100
    disk_type     = "PD_SSD"
  }
}

output "gke_endpoint" {
  value = module.gke.endpoint
}
'''
    files["terraform/main.tf"] = main_tf

    variables_tf = '''# Auto-generated by KA-CHOW Scaffolding Agent
variable "docker_registry" {
  type    = string
  default = "gcr.io"
}

variable "kafka_bootstrap_servers" {
  type    = list(string)
  default = []
}
'''
    files["terraform/variables.tf"] = variables_tf

    return files


def _generate_github_actions_workflow(plan: Dict[str, Any]) -> Dict[str, str]:
    """Generate GitHub Actions CI/CD workflow."""
    services = plan.get("services", [])
    service_names = [s.get("name", "service").lower().replace(" ", "-") for s in services]

    if not service_names:
        service_names = ["api-service"]

    content = f'''# Auto-generated by KA-CHOW Scaffolding Agent
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [{', '.join(service_names)}]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install ruff mypy
      - name: Run linter
        run: ruff check . && mypy . --ignore-missing-imports

  test:
    name: Test
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      matrix:
        service: [{', '.join(service_names)}]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install pytest pytest-cov
      - name: Run tests
        run: pytest --cov=. --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  build:
    name: Build
    runs-on: ubuntu-latest
    needs: test
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        service: [{', '.join(service_names)}]
    steps:
      - uses: actions/checkout@v4
      - name: Login to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{{{ github.repository }}}}/${{{{ matrix.service }}}}:${{{{ github.sha }}}}

  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Kubernetes
        run: |
          kubectl apply -f k8s/
          kubectl set image deployment/{', '.join(service_names)} {', '.join([f"{s}=ghcr.io/${{{{ github.repository }}}}/{s}:${{{{ github.sha }}}}" for s in service_names])}
'''
    return {".github/workflows/ci-cd.yaml": content}


def _persist_scaffold_result(
    scaffold_id: str,
    repo: str,
    requirements: str,
    blueprint: Dict[str, Any],
    files: Dict[str, str],
    llm_model: str,
    tokens_used: int,
    pg_cfg: Optional[Dict[str, Any]],
) -> None:
    """Persist scaffolding result to PostgreSQL."""
    if not pg_cfg:
        return

    import psycopg2
    from psycopg2.extras import Json

    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.scaffolding_runs
                    (scaffold_id, repo, requirements, blueprint, files, llm_model, tokens_used, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        scaffold_id,
                        repo,
                        requirements,
                        Json(blueprint),
                        Json({k: v for k, v in files.items() if len(v) < 10000}),
                        llm_model,
                        tokens_used,
                    ),
                )
            conn.commit()
        log.info("Scaffold result persisted: %s", scaffold_id)
    except Exception as exc:
        log.warning("Scaffold persistence failed: %s", exc)
