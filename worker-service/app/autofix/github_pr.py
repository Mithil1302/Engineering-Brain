"""
KA-CHOW Autofix — GitHub PR Creation.

Creates GitHub PRs with auto-generated patches:
  1. Creates a branch from HEAD
  2. Commits patch files
  3. Opens a PR with KA-CHOW description
  4. Links PR back to the triggering finding
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("ka-chow.autofix.github-pr")


class GitHubPRCreator:
    """
    Creates GitHub PRs for autofix patches.

    Uses either:
      - GitHub App installation tokens (via agent-service)
      - Personal Access Token (PAT) for development
    """

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        api_base: str = "https://api.github.com",
    ):
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._api_base = api_base.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if self._token:
            self._session.headers["Authorization"] = f"token {self._token}"

    def create_fix_pr(
        self,
        *,
        repo: str,
        patches: List[Dict[str, Any]],
        finding_id: str,
        fix_type: str = "code_fix",
        pr_number: Optional[int] = None,
        base_branch: str = "main",
        graph_node_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a GitHub PR with autofix patches.

        Parameters
        ----------
        repo : str
            Full repo name (owner/repo).
        patches : list
            List of dicts with 'file_path', 'content' or 'unified_diff', 'explanation'.
        finding_id : str
            ID of the policy finding this fix addresses.
        fix_type : str
            Type of fix (code_fix, doc_fix, contract_fix).
        pr_number : int, optional
            Original PR number that triggered the fix.
        base_branch : str
            Branch to create the fix PR against.

        Returns
        -------
        dict
            PR creation result with 'pr_url', 'pr_number', 'branch'.
        """
        if not self._token:
            return {
                "success": False,
                "error": "GitHub token not configured. Set GITHUB_TOKEN environment variable.",
            }

        if not patches:
            return {"success": False, "error": "No patches to apply."}

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        branch_name = f"ka-chow/autofix/{fix_type}/{finding_id}/{timestamp}"

        try:
            # Step 1: Get base branch SHA
            base_sha = self._get_branch_sha(repo, base_branch)

            # Step 2: Create branch
            self._create_branch(repo, branch_name, base_sha)

            # Step 3: Commit patches
            for patch in patches:
                file_path = patch.get("file_path", "")
                content = patch.get("content", "")
                if not file_path or not content:
                    continue

                self._create_or_update_file(
                    repo=repo,
                    branch=branch_name,
                    file_path=file_path,
                    content=content,
                    message=f"fix({fix_type}): {patch.get('explanation', 'Auto-generated fix')}",
                )

            # Step 4: Create PR
            pr_title = f"🤖 KA-CHOW Autofix: {fix_type} for {finding_id}"
            pr_body = self._build_pr_body(
                fix_type=fix_type,
                finding_id=finding_id,
                patches=patches,
                original_pr=pr_number,
                graph_node_ids=graph_node_ids or [],
            )

            pr = self._create_pull_request(
                repo=repo,
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=base_branch,
            )

            return {
                "success": True,
                "pr_url": pr.get("html_url"),
                "pr_number": pr.get("number"),
                "branch": branch_name,
                "files_changed": len(patches),
            }

        except Exception as exc:
            log.error("PR creation failed: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "branch": branch_name,
            }

    # -- GitHub API helpers -------------------------------------------------

    def _get_branch_sha(self, repo: str, branch: str) -> str:
        url = f"{self._api_base}/repos/{repo}/git/ref/heads/{branch}"
        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()["object"]["sha"]

    def _create_branch(self, repo: str, branch: str, sha: str) -> None:
        url = f"{self._api_base}/repos/{repo}/git/refs"
        resp = self._session.post(
            url,
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            timeout=20,
        )
        resp.raise_for_status()

    def _create_or_update_file(
        self,
        *,
        repo: str,
        branch: str,
        file_path: str,
        content: str,
        message: str,
    ) -> None:
        url = f"{self._api_base}/repos/{repo}/contents/{file_path}"

        # Check if file exists (to get SHA for update)
        existing_sha = None
        try:
            resp = self._session.get(url, params={"ref": branch}, timeout=20)
            if resp.status_code == 200:
                existing_sha = resp.json().get("sha")
        except Exception:
            pass

        payload: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        resp = self._session.put(url, json=payload, timeout=30)
        resp.raise_for_status()

    def _create_pull_request(
        self,
        *,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> Dict[str, Any]:
        url = f"{self._api_base}/repos/{repo}/pulls"
        resp = self._session.post(
            url,
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _build_pr_body(
        fix_type: str,
        finding_id: str,
        patches: List[Dict[str, Any]],
        original_pr: Optional[int],
        graph_node_ids: Optional[List[str]] = None,
    ) -> str:
        lines = [
            "## 🤖 KA-CHOW Autonomous Fix",
            "",
            f"**Fix Type:** `{fix_type}`",
            f"**Finding:** `{finding_id}`",
        ]
        if original_pr:
            lines.append(f"**Original PR:** #{original_pr}")

        # Graph node traceability — links fix back to knowledge graph entities
        if graph_node_ids:
            lines.extend([
                "",
                "### 🔗 Knowledge Graph Traceability",
                "",
                "This fix is traced to the following nodes in the KA-CHOW knowledge graph:",
                "",
            ])
            for node_id in graph_node_ids:
                lines.append(f"- `{node_id}`")

        lines.extend([
            "",
            "### Changes",
            "",
        ])

        for i, patch in enumerate(patches, 1):
            fp = patch.get("file_path", "unknown")
            explanation = patch.get("explanation", "Auto-generated fix")
            lines.append(f"{i}. **`{fp}`**: {explanation}")

        lines.extend([
            "",
            "---",
            "",
            "> ⚠️ This PR was auto-generated by KA-CHOW's self-healing engine. ",
            "> Please review all changes carefully before merging.",
            "",
            "### Confidence & Risk",
            "- **Confidence:** See individual patch details",
            f"- **Generated at:** {datetime.now(timezone.utc).isoformat()}",
        ])

        return "\n".join(lines)
