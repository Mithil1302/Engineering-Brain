"""
proxy.py — Thin HTTP proxy helpers.

forward_request() forwards an incoming FastAPI request to an upstream
service, preserving method, path suffix, headers, query params, and body.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, Request, status

from .config import REQUEST_TIMEOUT

log = logging.getLogger("ka-chow.backend")


async def forward_request(
    request: Request,
    *,
    base_url: str,
    path: str,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    """
    Forward a FastAPI request to an upstream service and return the JSON body.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    base_url : str
        Upstream service base URL (e.g. http://worker-service:8003).
    path : str
        Path on the upstream service (e.g. /policy/evaluate).
    extra_headers : dict, optional
        Additional headers to inject (e.g. auth headers).
    """
    url = f"{base_url.rstrip('/')}{path}"

    # Forward query params
    params = dict(request.query_params)

    # Forward relevant headers, inject extras
    headers: Dict[str, str] = {}
    for key in (
        "x-auth-context",
        "x-auth-signature",
        "x-auth-subject",
        "x-auth-role",
        "x-auth-tenant-id",
        "x-auth-repo-scope",
        "x-admin-token",
        "x-correlation-id",
        "x-request-id",
        "x-tenant-id",
        "authorization",
        "content-type",
    ):
        val = request.headers.get(key)
        if val:
            headers[key] = val

    if extra_headers:
        headers.update(extra_headers)

    # Read body
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                params=params,
                headers=headers,
                content=body,
            )
    except httpx.ConnectError as exc:
        log.error("Upstream connection failed %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Upstream service unavailable: {base_url}",
        )
    except httpx.TimeoutException as exc:
        log.error("Upstream timeout %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream service timed out",
        )

    # Propagate upstream error status codes
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}
