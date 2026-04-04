"""
CodeChunker: Transform raw file content into semantically meaningful, embeddable chunks.

Uses language-specific extraction strategies with fallback to sliding window.
Never truncates content - always subdivides oversized chunks.
"""

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import yaml

from .crawler import FileContent


@dataclass
class Chunk:
    """Semantically meaningful segment of code or documentation."""
    chunk_id: str  # SHA-256(repo + path + content), filled by chunk_files()
    repo: str  # filled by chunk_files()
    file_path: str
    extension: str
    content: str
    source_type: Literal["code", "docs", "spec", "config", "migration", "infra"]
    metadata: dict  # language-specific fields
    start_line: int
    end_line: int
    char_count: int


class CodeChunker:
    """Transform raw file content into semantically meaningful chunks."""

    def __init__(self, max_chunk_chars: int = 2000):
        self.max_chunk_chars = max_chunk_chars
        self._extractors: dict[str, Callable[[FileContent], list[Chunk]]] = {
            ".py": self._extract_python,
            ".ts": self._extract_typescript,
            ".js": self._extract_javascript,
            ".go": self._extract_go,
            ".md": self._extract_markdown,
            ".yaml": self._extract_yaml,
            ".yml": self._extract_yaml,
            ".json": self._extract_json,
            ".proto": self._extract_proto,
            ".sql": self._extract_sql,
            ".tf": self._extract_terraform,
        }

    def chunk_files(self, repo: str, files: list[FileContent]) -> list[Chunk]:
        """Chunk all files using language-specific strategies. Falls back to sliding window."""
        all_chunks = []
        for file in files:
            extractor = self._extractors.get(file.extension, self._sliding_window)
            try:
                chunks = extractor(file)
            except Exception as e:
                import logging
                logging.warning(f"Extractor failed for {file.path}: {e}, using sliding window")
                chunks = self._sliding_window(file)

            # Subdivide oversized chunks
            final_chunks = []
            for chunk in chunks:
                if chunk.char_count > self.max_chunk_chars:
                    final_chunks.extend(self._subdivide_large_chunk(chunk))
                else:
                    final_chunks.append(chunk)

            # Assign repo-scoped chunk_ids
            for chunk in final_chunks:
                chunk.repo = repo
                chunk.chunk_id = self._compute_chunk_id(repo, chunk.file_path, chunk.content)

            all_chunks.extend(final_chunks)
        return all_chunks

    def _extract_python(self, file: FileContent) -> list[Chunk]:
        """Extract top-level functions and classes using AST. Falls back to sliding window."""
        try:
            tree = ast.parse(file.content)
        except SyntaxError:
            import logging
            logging.debug(f"Python syntax error in {file.path}, falling back to sliding window")
            return self._sliding_window(file)

        chunks = []
        lines = file.content.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            # Only top-level (col_offset == 0)
            if node.col_offset != 0:
                continue

            start = node.lineno - 1
            end = node.end_lineno
            content = "\n".join(lines[start:end])
            docstring = ast.get_docstring(node) or ""

            chunks.append(Chunk(
                chunk_id="",  # filled later
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=content,
                source_type="code",
                metadata={
                    "name": node.name,
                    "type": "function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class",
                    "docstring": docstring[:200],
                    "start_line": node.lineno,
                    "end_line": node.end_lineno,
                },
                start_line=node.lineno,
                end_line=node.end_lineno,
                char_count=len(content),
            ))

        return chunks if chunks else self._sliding_window(file)

    def _extract_typescript(self, file: FileContent) -> list[Chunk]:
        """Extract declarations using regex with 30-line context windows."""
        pattern = re.compile(
            r'(?:export\s+)?(?:async\s+)?(?:function|class|interface|type|const)\s+(\w+)'
        )
        lines = file.content.splitlines()
        chunks = []

        for match in pattern.finditer(file.content):
            line_num = file.content[:match.start()].count('\n')
            start = max(0, line_num - 2)
            end = min(len(lines), line_num + 30)
            content = "\n".join(lines[start:end])

            chunks.append(Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=content,
                source_type="code",
                metadata={
                    "name": match.group(1),
                    "declaration_type": match.group(0).split()[0]
                },
                start_line=start + 1,
                end_line=end,
                char_count=len(content),
            ))

        return chunks if chunks else self._sliding_window(file)

    def _extract_javascript(self, file: FileContent) -> list[Chunk]:
        """Same pattern as TypeScript."""
        return self._extract_typescript(file)

    def _extract_go(self, file: FileContent) -> list[Chunk]:
        """Extract func declarations and struct/interface types."""
        func_pattern = re.compile(r'func\s+(?:\(([^)]+)\)\s+)?(\w+)\s*\(')
        type_pattern = re.compile(r'type\s+(\w+)\s+(?:struct|interface)')
        lines = file.content.splitlines()
        chunks = []

        for match in list(func_pattern.finditer(file.content)) + list(type_pattern.finditer(file.content)):
            line_num = file.content[:match.start()].count('\n')
            start = max(0, line_num)
            end = min(len(lines), line_num + 40)
            content = "\n".join(lines[start:end])

            # Determine if this is a function with receiver
            is_func = func_pattern.match(match.group(0))
            receiver = match.group(1) if is_func and match.lastindex >= 1 else None
            name = match.group(2) if is_func else match.group(1)

            chunks.append(Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=content,
                source_type="code",
                metadata={
                    "name": name,
                    "receiver_type": receiver
                },
                start_line=start + 1,
                end_line=end,
                char_count=len(content),
            ))

        return chunks if chunks else self._sliding_window(file)

    def _extract_markdown(self, file: FileContent) -> list[Chunk]:
        """Split on ## and ### headings. Each section is one chunk."""
        sections = re.split(r'\n(?=#{2,3}\s)', file.content)
        chunks = []
        line_offset = 0

        for section in sections:
            if not section.strip():
                continue

            first_line = section.split('\n')[0]
            title = re.sub(r'^#+\s*', '', first_line).strip()
            line_count = section.count('\n') + 1

            chunks.append(Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=section,
                source_type="docs",
                metadata={"section_title": title},
                start_line=line_offset + 1,
                end_line=line_offset + line_count,
                char_count=len(section),
            ))
            line_offset += line_count

        return chunks if chunks else self._sliding_window(file)

    def _extract_yaml(self, file: FileContent) -> list[Chunk]:
        """Handle OpenAPI specs, Kubernetes manifests, and generic YAML."""
        try:
            parsed = yaml.safe_load(file.content)
        except yaml.YAMLError:
            return self._sliding_window(file)

        if not isinstance(parsed, dict):
            return self._sliding_window(file)

        # OpenAPI spec
        if "openapi" in parsed or "swagger" in parsed:
            chunks = []
            paths = parsed.get("paths", {})
            for path, path_item in paths.items():
                for method, operation in path_item.items():
                    if method not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                        continue
                    content = yaml.dump({path: {method: operation}})
                    chunks.append(Chunk(
                        chunk_id="",
                        repo="",
                        file_path=file.path,
                        extension=file.extension,
                        content=content,
                        source_type="spec",
                        metadata={
                            "http_method": method.upper(),
                            "path": path,
                            "operation_id": operation.get("operationId", ""),
                            "tags": operation.get("tags", []),
                            "deprecated": operation.get("deprecated", False),
                        },
                        start_line=1,
                        end_line=content.count('\n') + 1,
                        char_count=len(content),
                    ))
            return chunks if chunks else self._sliding_window(file)

        # Kubernetes manifest
        if "kind" in parsed and "apiVersion" in parsed:
            return [Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=file.content,
                source_type="config",
                metadata={
                    "kind": parsed.get("kind"),
                    "name": parsed.get("metadata", {}).get("name")
                },
                start_line=1,
                end_line=file.content.count('\n') + 1,
                char_count=len(file.content),
            )]

        # Generic YAML — whole file as one chunk
        return [Chunk(
            chunk_id="",
            repo="",
            file_path=file.path,
            extension=file.extension,
            content=file.content,
            source_type="config",
            metadata={},
            start_line=1,
            end_line=file.content.count('\n') + 1,
            char_count=len(file.content),
        )]

    def _extract_json(self, file: FileContent) -> list[Chunk]:
        """Detect OpenAPI in JSON; otherwise whole file as one chunk."""
        try:
            parsed = json.loads(file.content)
            if isinstance(parsed, dict) and ("openapi" in parsed or "swagger" in parsed):
                # Convert to YAML string and reuse YAML extractor
                as_yaml = yaml.dump(parsed)
                fake_file = FileContent(
                    path=file.path,
                    content=as_yaml,
                    extension=".yaml",
                    size_bytes=len(as_yaml),
                    sha=file.sha,
                    last_modified=file.last_modified,
                )
                return self._extract_yaml(fake_file)
        except json.JSONDecodeError:
            pass

        return [Chunk(
            chunk_id="",
            repo="",
            file_path=file.path,
            extension=file.extension,
            content=file.content,
            source_type="config",
            metadata={},
            start_line=1,
            end_line=file.content.count('\n') + 1,
            char_count=len(file.content),
        )]

    def _extract_proto(self, file: FileContent) -> list[Chunk]:
        """Extract service and message definitions from proto files."""
        service_pattern = re.compile(r'service\s+(\w+)\s*\{([^}]+)\}', re.DOTALL)
        message_pattern = re.compile(r'message\s+(\w+)\s*\{([^}]+)\}', re.DOTALL)
        chunks = []

        for match in list(service_pattern.finditer(file.content)) + list(message_pattern.finditer(file.content)):
            content = match.group(0)
            line_start = file.content[:match.start()].count('\n') + 1
            is_service = match.group(0).startswith("service")

            chunks.append(Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=content,
                source_type="spec",
                metadata={
                    "proto_type": "service" if is_service else "message",
                    "name": match.group(1)
                },
                start_line=line_start,
                end_line=line_start + content.count('\n'),
                char_count=len(content),
            ))

        return chunks if chunks else self._sliding_window(file)

    def _extract_sql(self, file: FileContent) -> list[Chunk]:
        """Extract CREATE TABLE, CREATE INDEX, CREATE FUNCTION statements."""
        pattern = re.compile(
            r'(CREATE\s+(?:TABLE|INDEX|UNIQUE\s+INDEX|FUNCTION|OR\s+REPLACE\s+FUNCTION)'
            r'\s+[^;]+;)',
            re.IGNORECASE | re.DOTALL
        )
        chunks = []

        for match in pattern.finditer(file.content):
            content = match.group(0).strip()
            line_start = file.content[:match.start()].count('\n') + 1

            # Extract object name
            name_match = re.search(
                r'(?:TABLE|INDEX|FUNCTION)\s+(?:IF\s+NOT\s+EXISTS\s+)?(\S+)',
                content,
                re.IGNORECASE
            )
            object_name = name_match.group(1) if name_match else ""

            stmt_type_match = re.match(r'CREATE\s+(\w+)', content, re.IGNORECASE)

            chunks.append(Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=content,
                source_type="migration",
                metadata={
                    "statement_type": stmt_type_match.group(1).upper() if stmt_type_match else "CREATE",
                    "object_name": object_name
                },
                start_line=line_start,
                end_line=line_start + content.count('\n'),
                char_count=len(content),
            ))

        return chunks if chunks else self._sliding_window(file)

    def _extract_terraform(self, file: FileContent) -> list[Chunk]:
        """Extract resource blocks from Terraform files."""
        pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([^}]+)\}', re.DOTALL)
        chunks = []

        for match in pattern.finditer(file.content):
            content = match.group(0)
            line_start = file.content[:match.start()].count('\n') + 1

            chunks.append(Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=content,
                source_type="infra",
                metadata={
                    "resource_type": match.group(1),
                    "resource_name": match.group(2)
                },
                start_line=line_start,
                end_line=line_start + content.count('\n'),
                char_count=len(content),
            ))

        return chunks if chunks else self._sliding_window(file)

    def _sliding_window(
        self,
        file: FileContent,
        window_lines: int = 50,
        overlap_lines: int = 10
    ) -> list[Chunk]:
        """Fallback: fixed sliding window with overlap. Used for unknown types and parse failures."""
        lines = file.content.splitlines()
        chunks = []
        step = window_lines - overlap_lines

        for i in range(0, max(1, len(lines)), step):
            window = lines[i: i + window_lines]
            content = "\n".join(window)

            chunks.append(Chunk(
                chunk_id="",
                repo="",
                file_path=file.path,
                extension=file.extension,
                content=content,
                source_type="code" if file.extension in {".py", ".ts", ".js", ".go", ".java"} else "config",
                metadata={},
                start_line=i + 1,
                end_line=i + len(window),
                char_count=len(content),
            ))

        return chunks

    def _subdivide_large_chunk(self, chunk: Chunk) -> list[Chunk]:
        """Split oversized chunks with 200-char overlap. Never truncates."""
        sub_chunks = []
        content = chunk.content
        overlap = 200
        step = self.max_chunk_chars - overlap

        for i in range(0, len(content), step):
            sub_content = content[i: i + self.max_chunk_chars]
            sub_chunks.append(Chunk(
                chunk_id="",
                repo=chunk.repo,
                file_path=chunk.file_path,
                extension=chunk.extension,
                content=sub_content,
                source_type=chunk.source_type,
                metadata={
                    **chunk.metadata,
                    "sub_chunk_index": len(sub_chunks),
                    "original_start_line": chunk.start_line
                },
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                char_count=len(sub_content),
            ))

        return sub_chunks

    def _compute_chunk_id(self, repo: str, path: str, content: str) -> str:
        """SHA-256 of repo+path+content for deterministic deduplication."""
        return hashlib.sha256(f"{repo}:{path}:{content}".encode()).hexdigest()
