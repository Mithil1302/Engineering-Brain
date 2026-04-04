"""
Service detection and dependency extraction for repository ingestion.

This module identifies microservice boundaries within a repository using heuristics
(Dockerfile presence, package manifests, k8s directories) and extracts inter-service
dependencies from docker-compose, Kubernetes manifests, and import statements.
"""

import re
import yaml
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .crawler import FileContent


@dataclass
class ServiceManifest:
    """Represents a detected microservice with its metadata and capabilities."""
    service_name: str
    root_path: str
    language: str
    has_dockerfile: bool = False
    has_openapi: bool = False
    has_proto: bool = False
    has_migrations: bool = False
    has_tests: bool = False
    has_ci: bool = False
    owner_hint: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)


class ServiceDetector:
    """Identifies microservice boundaries within a repository using heuristics."""
    
    SERVICE_MARKERS = {"Dockerfile", "pyproject.toml", "package.json", "go.mod"}

    def detect_services(self, files: list[FileContent]) -> list[ServiceManifest]:
        """
        Identify service boundaries using heuristics across all detected markers.
        
        Groups files by top-level directory and checks for service markers
        (Dockerfile, package manifests, k8s/ directories).
        """
        # Build directory tree from file paths - group by top-level directory
        dirs: dict[str, list[FileContent]] = {}
        for file in files:
            top_level = file.path.split("/")[0] if "/" in file.path else "."
            dirs.setdefault(top_level, []).append(file)

        services = []
        for dir_path, dir_files in dirs.items():
            file_names = {Path(f.path).name for f in dir_files}
            has_marker = bool(self.SERVICE_MARKERS & file_names)
            has_k8s = any("k8s/" in f.path or "kubernetes/" in f.path for f in dir_files)
            
            if not (has_marker or has_k8s):
                continue
            
            services.append(ServiceManifest(
                service_name=dir_path,
                root_path=dir_path,
                language=self._determine_language(dir_files),
                has_dockerfile="Dockerfile" in file_names,
                has_openapi=any(
                    "openapi" in (f.content[:500].lower()) for f in dir_files
                    if f.extension in {".yaml", ".yml", ".json"}
                ),
                has_proto=any(f.extension == ".proto" for f in dir_files),
                has_migrations=any(f.extension == ".sql" for f in dir_files) or
                               any("migrations/" in f.path for f in dir_files),
                has_tests=any(
                    Path(f.path).name.startswith("test_") or
                    f.path.endswith(".test.ts") or f.path.endswith("_test.go")
                    for f in dir_files
                ),
                has_ci=any(".github/workflows/" in f.path for f in dir_files),
                owner_hint=self._extract_owner_from_codeowners(dir_path, files),
                dependencies=[],  # populated by DependencyExtractor
                endpoints=self._extract_endpoints(dir_files),
                file_paths=[f.path for f in dir_files],
            ))

        # Also parse docker-compose for additional service names
        compose_services = self._parse_docker_compose_services(files)
        existing_names = {s.service_name for s in services}
        for name in compose_services:
            if name not in existing_names:
                services.append(ServiceManifest(
                    service_name=name,
                    root_path=name,
                    language="unknown",
                    has_dockerfile=False,
                    has_openapi=False,
                    has_proto=False,
                    has_migrations=False,
                    has_tests=False,
                    has_ci=False,
                    owner_hint=None,
                    dependencies=[],
                    endpoints=[],
                    file_paths=[],
                ))
        
        return services

    def _determine_language(self, files: list[FileContent]) -> str:
        """Return most common code file extension."""
        counter = Counter(
            f.extension for f in files
            if f.extension in {".py", ".ts", ".js", ".go", ".java"}
        )
        return counter.most_common(1)[0][0] if counter else "unknown"

    def _extract_owner_from_codeowners(self, dir_path: str,
                                        all_files: list[FileContent]) -> Optional[str]:
        """Parse CODEOWNERS file for directory ownership hint."""
        codeowners_file = next(
            (f for f in all_files if f.path in {"CODEOWNERS", ".github/CODEOWNERS"}),
            None
        )
        if not codeowners_file:
            return None
        
        for line in codeowners_file.content.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2 and dir_path in parts[0]:
                return parts[1].lstrip("@")
        
        return None

    def _extract_endpoints(self, files: list[FileContent]) -> list[str]:
        """Extract HTTP paths from OpenAPI spec files in this service."""
        endpoints = []
        for f in files:
            if f.extension not in {".yaml", ".yml", ".json"}:
                continue
            if "openapi" not in f.content[:500].lower():
                continue
            try:
                parsed = yaml.safe_load(f.content)
                endpoints.extend(parsed.get("paths", {}).keys())
            except Exception:
                pass
        return endpoints

    def _parse_docker_compose_services(self, files: list[FileContent]) -> list[str]:
        """Extract service names from docker-compose.yaml files."""
        names = []
        for f in files:
            if Path(f.path).name not in {"docker-compose.yaml", "docker-compose.yml"}:
                continue
            try:
                parsed = yaml.safe_load(f.content)
                names.extend(parsed.get("services", {}).keys())
            except Exception:
                pass
        return names


class DependencyExtractor:
    """Extracts inter-service dependencies from multiple sources."""

    def extract_dependencies(self, services: list[ServiceManifest],
                             files: list[FileContent]) -> list[tuple[str, str, str]]:
        """
        Extract (source, target, type) dependency tuples from all sources.
        
        Unions results from docker-compose depends_on, Kubernetes Service
        cross-references, and import statements.
        """
        service_names = {s.service_name for s in services}
        deps = []
        deps.extend(self._parse_docker_compose(files, service_names))
        deps.extend(self._parse_k8s_services(files, service_names))
        deps.extend(self._parse_import_statements(files, services, service_names))
        return list(set(deps))  # deduplicate

    def _parse_docker_compose(self, files: list[FileContent],
                               service_names: set[str]) -> list[tuple[str, str, str]]:
        """Parse depends_on blocks from docker-compose files."""
        deps = []
        for f in files:
            if Path(f.path).name not in {"docker-compose.yaml", "docker-compose.yml"}:
                continue
            try:
                parsed = yaml.safe_load(f.content)
                for svc_name, svc_config in parsed.get("services", {}).items():
                    if not isinstance(svc_config, dict):
                        continue
                    depends_on = svc_config.get("depends_on", [])
                    # Handle both list and dict formats
                    if isinstance(depends_on, dict):
                        depends_on = list(depends_on.keys())
                    for dep in depends_on:
                        if dep in service_names:
                            deps.append((svc_name, dep, "runtime"))
            except Exception:
                pass
        return deps

    def _parse_k8s_services(self, files: list[FileContent],
                             service_names: set[str]) -> list[tuple[str, str, str]]:
        """Cross-reference Kubernetes Service names against detected services."""
        k8s_service_names = set()
        for f in files:
            if f.extension not in {".yaml", ".yml"}:
                continue
            try:
                parsed = yaml.safe_load(f.content)
                if isinstance(parsed, dict) and parsed.get("kind") == "Service":
                    name = parsed.get("metadata", {}).get("name")
                    if name:
                        k8s_service_names.add(name)
            except Exception:
                pass
        
        # Cross-reference: k8s Service name that matches a detected service
        deps = []
        for svc in service_names:
            for k8s_name in k8s_service_names:
                if k8s_name != svc and k8s_name in service_names:
                    deps.append((svc, k8s_name, "network"))
        return deps

    def _parse_import_statements(self, files: list[FileContent],
                                  services: list[ServiceManifest],
                                  service_names: set[str]) -> list[tuple[str, str, str]]:
        """Extract cross-service imports from Python and TypeScript files."""
        py_pattern = re.compile(r'^(?:from|import)\s+([\w.]+)', re.MULTILINE)
        ts_pattern = re.compile(r"from\s+['\"](@[\w-]+/[\w-]+|\.\.?/[\w/-]+)['\"]")
        deps = []
        
        for file in files:
            # Find which service this file belongs to
            source_service = next(
                (s.service_name for s in services if file.path.startswith(s.root_path)), None
            )
            if not source_service:
                continue
            
            if file.extension == ".py":
                for match in py_pattern.finditer(file.content):
                    # Take first segment of dotted module name
                    module = match.group(1).split(".")[0]
                    if module in service_names and module != source_service:
                        deps.append((source_service, module, "import"))
            
            elif file.extension in {".ts", ".js"}:
                for match in ts_pattern.finditer(file.content):
                    # Take last segment and strip @
                    imported = match.group(1).split("/")[-1].lstrip("@")
                    if imported in service_names and imported != source_service:
                        deps.append((source_service, imported, "import"))
        
        return deps
