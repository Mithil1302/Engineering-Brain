"""
config.py — Backend API configuration.

All service URLs and auth settings are read from environment variables
so the backend works both locally and inside Docker Compose.
"""
from __future__ import annotations

import os

# Upstream service base URLs
WORKER_SERVICE_URL = os.getenv("WORKER_SERVICE_URL", "http://worker-service:8003")
AGENT_SERVICE_URL  = os.getenv("AGENT_SERVICE_URL",  "http://agent-service:8002")
GRAPH_SERVICE_URL  = os.getenv("GRAPH_SERVICE_URL",  "http://graph-service:8001")

# Admin token forwarded to worker-service
POLICY_ADMIN_TOKEN = os.getenv("POLICY_ADMIN_TOKEN", "").strip()

# Auth signing key (forwarded to worker-service claims)
AUTH_CONTEXT_SIGNING_KEY = os.getenv("AUTH_CONTEXT_SIGNING_KEY", "").strip()

# Request timeout (seconds)
REQUEST_TIMEOUT = int(os.getenv("BACKEND_REQUEST_TIMEOUT", "30"))
