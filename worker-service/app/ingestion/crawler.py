"""GitHub repository crawler with App authentication and rate limit handling."""
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt

log = logging.getLogger(__name__)


@dataclass
class FileContent:
    """Represents a single file fetched from GitHub."""
    path: str
    content: str
    extension: str
    size_bytes: int
    sha: str
    last_modified: datetime | None  # Required for freshness scoring downstream


@dataclass
class RepoCrawlResult:
    """Result of crawling a GitHub repository."""
    repo: str
    default_branch: str
    total_files: int
    files: list[FileContent]
    crawled_at: datetime


class GitHubRepoCrawler:
    """Crawls GitHub repositories using GitHub App authentication."""
    
    EXTENSION_WHITELIST = {
        ".py", ".ts", ".js", ".go", ".java",
        ".yaml", ".yml", ".json", ".md", ".proto", ".tf", ".sql"
    }
    
    PATH_BLACKLIST = {
        "node_modules/", ".git/", "dist/", "build/",
        "__pycache__/", "vendor/", "coverage/", ".next/", ".nuxt/"
    }

    def __init__(
        self,
        app_id: str,
        private_key: str,
        installation_id: str,
        max_concurrent: int = 10,
        max_file_size_kb: int = 500,
    ):
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self.max_file_size_bytes = max_file_size_kb * 1024
        self.api_base_url = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com").rstrip("/")
        self.max_http_retries = int(os.getenv("GITHUB_HTTP_MAX_RETRIES", "4"))
        self._token_cache: dict[str, tuple[str, datetime]] = {}
        self._rate_limit_remaining: int = 5000
        self._rate_limit_reset: datetime | None = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=max_concurrent * 2,
                max_keepalive_connections=max_concurrent,
            ),
        )

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        max_retries: int | None = None,
    ) -> httpx.Response:
        retries = self.max_http_retries if max_retries is None else max_retries
        last_exc: Exception | None = None

        for attempt in range(retries + 1):
            try:
                resp = await self._client.request(method, url, headers=headers)

                # Retry transient server/rate-limit responses.
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    wait = min(2 ** attempt, 20)
                    log.warning(
                        "GitHub %s %s returned %s; retrying in %ss (attempt %s/%s)",
                        method,
                        url,
                        resp.status_code,
                        wait,
                        attempt + 1,
                        retries + 1,
                    )
                    await asyncio.sleep(wait)
                    continue

                return resp

            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt >= retries:
                    raise
                wait = min(2 ** attempt, 20)
                log.warning(
                    "GitHub %s %s connection error (%s); retrying in %ss (attempt %s/%s)",
                    method,
                    url,
                    exc,
                    wait,
                    attempt + 1,
                    retries + 1,
                )
                await asyncio.sleep(wait)

        if last_exc:
            raise last_exc
        raise RuntimeError("Unexpected HTTP retry flow")

    def _create_jwt(self) -> str:
        """Create GitHub App JWT. Valid for 10 minutes, used to get installation token."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # 60-second backdate required by GitHub
            "exp": now + 540,  # 9 minutes from now
            "iss": self.app_id
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def _get_installation_token(self) -> str:
        """Get cached installation token or fetch a new one. Refreshes 1 minute before expiry."""
        cached_token, expiry = self._token_cache.get("default", (None, None))
        if cached_token and expiry and datetime.now(timezone.utc) < expiry - timedelta(minutes=1):
            return cached_token
        
        app_jwt = self._create_jwt()
        resp = await self._request_with_retries(
            "POST",
            f"{self.api_base_url}/app/installations/{self.installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["token"]
        expiry = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        self._token_cache["default"] = (token, expiry)
        return token

    async def _get_default_branch(self, repo: str, token: str) -> str:
        """Get repository default branch via GET /repos/{owner}/{repo}."""
        resp = await self._request_with_retries(
            "GET",
            f"{self.api_base_url}/repos/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        await self._handle_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()
        return data["default_branch"]

    async def _get_branch_sha(self, repo: str, branch: str, token: str) -> str:
        """Get branch SHA via GET /repos/{owner}/{repo}/git/ref/heads/{branch}."""
        resp = await self._request_with_retries(
            "GET",
            f"{self.api_base_url}/repos/{repo}/git/ref/heads/{branch}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        await self._handle_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()
        return data["object"]["sha"]

    async def _fetch_tree(self, repo: str, sha: str, token: str) -> list[dict]:
        """Fetch full repository file tree recursively. Filter to blobs only."""
        resp = await self._request_with_retries(
            "GET",
            f"{self.api_base_url}/repos/{repo}/git/trees/{sha}?recursive=1",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        await self._handle_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()
        return [item for item in data.get("tree", []) if item["type"] == "blob"]

    async def _fetch_file_content(
        self,
        repo: str,
        path: str,
        token: str
    ) -> FileContent | None:
        """Fetch and decode single file. Returns None on 404 or size exceeded."""
        async with self._semaphore:
            for attempt in range(5):
                try:
                    resp = await self._request_with_retries(
                        "GET",
                        f"{self.api_base_url}/repos/{repo}/contents/{path}",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/vnd.github+json",
                        },
                        max_retries=3,
                    )
                    await self._handle_rate_limit(resp)

                    if resp.status_code == 404:
                        log.warning(f"File not found: {repo}/{path}")
                        return None

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        log.warning(f"Rate limited, sleeping {wait}s")
                        await asyncio.sleep(min(wait, 60))
                        continue

                    resp.raise_for_status()
                    data = resp.json()
                    size_bytes = data.get("size", 0)

                    if size_bytes > self.max_file_size_bytes:
                        log.debug(f"Skipping {path}: {size_bytes} bytes exceeds limit")
                        return None

                    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

                    return FileContent(
                        path=path,
                        content=content,
                        extension=Path(path).suffix.lower(),
                        size_bytes=size_bytes,
                        sha=data["sha"],
                        last_modified=None,  # Populated separately if needed
                    )
                except httpx.HTTPError as e:
                    log.warning(f"HTTP error fetching {path} (attempt {attempt+1}): {e}")
                    await asyncio.sleep(min(2 ** attempt, 60))
            
            return None

    def _should_include_file(self, path: str, size_bytes: int) -> bool:
        """Filter by extension whitelist, path blacklist, and size limit."""
        ext = Path(path).suffix.lower()
        if ext not in self.EXTENSION_WHITELIST:
            return False
        if any(pattern in path for pattern in self.PATH_BLACKLIST):
            return False
        if size_bytes > self.max_file_size_bytes:
            return False
        return True

    async def _handle_rate_limit(self, response: httpx.Response) -> None:
        """Read rate limit headers and sleep until reset if below 100 remaining."""
        remaining = int(response.headers.get("X-RateLimit-Remaining", 5000))
        reset_ts = int(response.headers.get("X-RateLimit-Reset", 0))
        self._rate_limit_remaining = remaining
        
        if remaining < 100 and reset_ts:
            sleep_seconds = max(0, reset_ts - int(time.time())) + 5
            log.warning(f"GitHub rate limit low ({remaining}), sleeping {sleep_seconds}s")
            await asyncio.sleep(sleep_seconds)

    async def crawl_repo(
        self,
        repo: str,
        changed_files: list[str] | None = None
    ) -> RepoCrawlResult:
        """Full or incremental crawl. If changed_files provided, only fetch those."""
        token = await self._get_installation_token()
        default_branch = await self._get_default_branch(repo, token)
        tree_sha = await self._get_branch_sha(repo, default_branch, token)

        if changed_files is not None:
            # Incremental: only fetch listed files
            file_items = [{"path": f, "type": "blob", "size": 0} for f in changed_files]
        else:
            # Full: walk entire tree
            file_items = await self._fetch_tree(repo, tree_sha, token)

        filtered = [f for f in file_items if self._should_include_file(f["path"], f.get("size", 0))]
        
        files = await asyncio.gather(*[
            self._fetch_file_content(repo, f["path"], token)
            for f in filtered
        ])
        files = [f for f in files if f is not None]  # Drop fetch failures

        return RepoCrawlResult(
            repo=repo,
            default_branch=default_branch,
            total_files=len(files),
            files=files,
            crawled_at=datetime.now(timezone.utc),
        )
