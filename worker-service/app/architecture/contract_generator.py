from __future__ import annotations

import json
from typing import Any, Dict, List


def generate_grpc_contracts(plan: Dict[str, Any]) -> Dict[str, str]:
    files: Dict[str, str] = {}
    services = plan.get("services") or []
    for svc in services:
        name = str((svc or {}).get("name") or "service").replace(" ", "")
        endpoints = (svc or {}).get("endpoints") or []
        rpc_lines: List[str] = []
        msg_lines: List[str] = []
        for i, ep in enumerate(endpoints, start=1):
            op = str((ep or {}).get("operation_id") or f"Operation{i}")
            req = f"{op}Request"
            res = f"{op}Response"
            rpc_lines.append(f"  rpc {op}({req}) returns ({res});")
            msg_lines.extend([
                f"message {req} {{ string trace_id = 1; }}",
                f"message {res} {{ string status = 1; }}",
            ])

        proto = "\n".join([
            'syntax = "proto3";',
            "",
            f"package {name.lower()};",
            "",
            f"service {name}Service {{",
            *rpc_lines,
            "}",
            "",
            *msg_lines,
            "",
        ])
        files[f"contracts/{name.lower()}.proto"] = proto
    return files


def generate_openapi_contracts(plan: Dict[str, Any]) -> Dict[str, str]:
    files: Dict[str, str] = {}
    services = plan.get("services") or []
    for svc in services:
        name = str((svc or {}).get("name") or "service").lower().replace(" ", "-")
        paths: Dict[str, Any] = {}
        for ep in (svc or {}).get("endpoints") or []:
            method = str((ep or {}).get("method") or "GET").lower()
            path = str((ep or {}).get("path") or "/")
            paths.setdefault(path, {})[method] = {
                "summary": str((ep or {}).get("description") or ""),
                "operationId": str((ep or {}).get("operation_id") or f"{method}_{path.strip('/').replace('/', '_')}"),
                "responses": {
                    "200": {"description": "Success"},
                    "400": {"description": "Bad Request"},
                    "500": {"description": "Internal Server Error"},
                },
            }

        doc = {
            "openapi": "3.0.3",
            "info": {"title": f"{name} API", "version": "1.0.0"},
            "paths": paths,
        }
        files[f"contracts/{name}.openapi.json"] = json.dumps(doc, indent=2)
    return files
