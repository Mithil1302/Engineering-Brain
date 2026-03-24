"""
KA-CHOW Architecture Scaffolder — generates actual file contents from plans.

Given an architecture plan, produces:
  - Dockerfiles
  - docker-compose fragments
  - OpenAPI spec stubs
  - Kubernetes manifests
  - Database migration SQL
  - README.md for each service
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..llm import get_llm_client

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
    all_types = include_types or ["dockerfile", "docker-compose", "openapi", "k8s", "migration", "readme"]

    services = plan.get("services", [])
    if not services:
        return files

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

        # OpenAPI spec via LLM
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

    # Migration SQL
    if "migration" in all_types:
        data_models = plan.get("data_models", [])
        if data_models:
            try:
                files["migrations/001_scaffold.sql"] = _generate_migration_sql(llm, data_models)
            except Exception as exc:
                log.warning("Migration SQL generation failed: %s", exc)
                files["migrations/001_scaffold.sql"] = _fallback_migration(data_models)

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
