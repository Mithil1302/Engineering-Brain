"""
KA-CHOW CI/CD — GitHub Branch Protection Enforcement.

Implements actual merge blocking via GitHub Branch Protection API:
  1. Set required status checks based on policy gate outcome
  2. Configure branch protection rules per repository
  3. Enforce/unenforce based on policy template settings
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("ka-chow.branch-protection")


class BranchProtectionEnforcer:
    """
    Enforces merge blocking via GitHub Branch Protection API.

    When a policy gate decision is "block", this module:
      1. Creates/updates a required status check ("KA-CHOW Policy Gate")
      2. Ensures the branch protection rule requires this check to pass
    """

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        api_base: str = "https://api.github.com",
        check_name: str = "KA-CHOW Policy Gate",
    ):
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._api_base = api_base.rstrip("/")
        self._check_name = check_name
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if self._token:
            self._session.headers["Authorization"] = f"token {self._token}"

    def enforce_merge_block(
        self,
        *,
        repo: str,
        gate_decision: Dict[str, Any],
        branch: str = "main",
    ) -> Dict[str, Any]:
        """
        Enforce or relax branch protection based on policy gate decision.

        Parameters
        ----------
        repo : str
            Full repo name (owner/repo).
        gate_decision : dict
            Output from build_merge_gate_decision().
        branch : str
            Branch to protect.

        Returns
        -------
        dict
            Result with 'enforced', 'action', 'details'.
        """
        if not self._token:
            return {
                "enforced": False,
                "action": "skipped",
                "reason": "GitHub token not configured",
            }

        decision = gate_decision.get("decision", "allow")
        should_block = decision in ("block", "fail")

        try:
            # Get current branch protection
            current = self._get_protection(repo, branch)
            current_checks = self._extract_required_checks(current)

            if should_block:
                # Ensure KA-CHOW check is in required status checks
                if self._check_name not in current_checks:
                    updated_checks = current_checks + [self._check_name]
                    self._update_required_checks(repo, branch, updated_checks, current)
                    return {
                        "enforced": True,
                        "action": "added_required_check",
                        "check_name": self._check_name,
                        "required_checks": updated_checks,
                        "gate_decision": decision,
                    }
                return {
                    "enforced": True,
                    "action": "already_enforced",
                    "check_name": self._check_name,
                    "gate_decision": decision,
                }
            else:
                # Remove KA-CHOW check from required (allow merge)
                if self._check_name in current_checks:
                    updated_checks = [c for c in current_checks if c != self._check_name]
                    self._update_required_checks(repo, branch, updated_checks, current)
                    return {
                        "enforced": False,
                        "action": "removed_required_check",
                        "check_name": self._check_name,
                        "required_checks": updated_checks,
                        "gate_decision": decision,
                    }
                return {
                    "enforced": False,
                    "action": "already_relaxed",
                    "gate_decision": decision,
                }

        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                # No branch protection exists yet — create it if blocking
                if should_block:
                    return self._create_protection(repo, branch)
                return {
                    "enforced": False,
                    "action": "no_protection_exists",
                    "gate_decision": decision,
                }
            log.error("Branch protection enforcement failed: %s", exc)
            return {
                "enforced": False,
                "action": "error",
                "error": str(exc),
            }
        except Exception as exc:
            log.error("Branch protection enforcement failed: %s", exc)
            return {
                "enforced": False,
                "action": "error",
                "error": str(exc),
            }

    def get_protection_status(
        self, repo: str, branch: str = "main"
    ) -> Dict[str, Any]:
        """Get current branch protection status."""
        if not self._token:
            return {"configured": False, "reason": "No token"}

        try:
            protection = self._get_protection(repo, branch)
            checks = self._extract_required_checks(protection)
            return {
                "configured": True,
                "branch": branch,
                "ka_chow_enforced": self._check_name in checks,
                "required_checks": checks,
                "enforce_admins": protection.get("enforce_admins", {}).get("enabled", False),
                "require_pull_request": bool(protection.get("required_pull_request_reviews")),
            }
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return {"configured": False, "branch": branch, "reason": "No protection rules"}
            return {"configured": False, "error": str(exc)}
        except Exception as exc:
            return {"configured": False, "error": str(exc)}

    # -- GitHub API helpers -------------------------------------------------

    def _get_protection(self, repo: str, branch: str) -> Dict[str, Any]:
        url = f"{self._api_base}/repos/{repo}/branches/{branch}/protection"
        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_required_checks(protection: Dict[str, Any]) -> List[str]:
        checks_obj = protection.get("required_status_checks") or {}
        contexts = checks_obj.get("contexts") or []
        # Also check the newer "checks" field
        checks = checks_obj.get("checks") or []
        check_names = [c.get("context", "") for c in checks if c.get("context")]
        return list(set(contexts + check_names))

    def _update_required_checks(
        self,
        repo: str,
        branch: str,
        checks: List[str],
        current_protection: Dict[str, Any],
    ) -> None:
        url = f"{self._api_base}/repos/{repo}/branches/{branch}/protection"

        # Preserve existing protection settings
        payload: Dict[str, Any] = {
            "required_status_checks": {
                "strict": True,
                "contexts": checks,
            },
            "enforce_admins": bool(
                current_protection.get("enforce_admins", {}).get("enabled")
            ),
            "required_pull_request_reviews": None,
            "restrictions": None,
        }

        # Preserve PR review requirements if they exist
        pr_reviews = current_protection.get("required_pull_request_reviews")
        if pr_reviews:
            payload["required_pull_request_reviews"] = {
                "required_approving_review_count": pr_reviews.get(
                    "required_approving_review_count", 1
                ),
            }

        resp = self._session.put(url, json=payload, timeout=30)
        resp.raise_for_status()

    def _create_protection(self, repo: str, branch: str) -> Dict[str, Any]:
        """Create branch protection with KA-CHOW check required."""
        url = f"{self._api_base}/repos/{repo}/branches/{branch}/protection"
        payload = {
            "required_status_checks": {
                "strict": True,
                "contexts": [self._check_name],
            },
            "enforce_admins": False,
            "required_pull_request_reviews": {
                "required_approving_review_count": 1,
            },
            "restrictions": None,
        }
        resp = self._session.put(url, json=payload, timeout=30)
        resp.raise_for_status()
        return {
            "enforced": True,
            "action": "created_protection",
            "check_name": self._check_name,
            "branch": branch,
        }
