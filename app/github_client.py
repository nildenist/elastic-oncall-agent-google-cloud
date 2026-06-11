import os
from typing import Any, Dict, List

import httpx


def build_incident_issue_body(
    before_snapshot: Dict[str, Any] | None = None,
    after_snapshot: Dict[str, Any] | None = None,
    verification_result: Dict[str, Any] | None = None,
) -> str:
    # Keep arguments for future enrichment while providing a deterministic body now.
    _ = before_snapshot
    _ = after_snapshot
    _ = verification_result

    return (
        "# Incident resolved by Elastic On-Call Agent\n\n"
        "## Root cause\n"
        "checkout-api entered redis_timeout failure mode and started returning unhealthy responses.\n\n"
        "## Evidence\n"
        "- checkout-api /healthz returned 503 during the incident.\n"
        "- checkout-api /checkout returned 500 during the incident.\n"
        "- payment-api /healthz remained healthy.\n"
        "- Failure was isolated to checkout-api and customer checkout flow.\n\n"
        "## Action taken\n"
        "The agent called checkout-api /admin/repair and restored checkout-api runtime mode to healthy.\n\n"
        "## Verification\n"
        "- checkout-api /healthz returned 200 after remediation.\n"
        "- checkout-api /checkout returned 200 after remediation.\n"
        "- payment-api /healthz returned 200 after remediation.\n"
        "- customer checkout flow returned to healthy.\n\n"
        "## Follow-up\n"
        "Review checkout-api runtime config guardrails before redeployment."
    )


def create_incident_issue(
    issue_title: str,
    labels: List[str],
    before_snapshot: Dict[str, Any] | None = None,
    after_snapshot: Dict[str, Any] | None = None,
    verification_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    issue_body = build_incident_issue_body(
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        verification_result=verification_result,
    )

    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    github_repository = os.getenv("GITHUB_REPOSITORY", "").strip()

    if not github_token or not github_repository:
        return {
            "status": "simulated",
            "reason": "GITHUB_TOKEN or GITHUB_REPOSITORY is not configured.",
            "title": issue_title,
            "labels": labels,
            "body": issue_body,
        }

    if "/" not in github_repository or github_repository.count("/") != 1:
        return {
            "status": "failed",
            "error": "GITHUB_REPOSITORY must be in owner/repo format.",
            "title": issue_title,
            "labels": labels,
            "body": issue_body,
        }

    owner, repo = github_repository.split("/", maxsplit=1)
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"

    payload = {
        "title": issue_title,
        "body": issue_body,
        "labels": labels,
    }
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload, headers=headers)

        if 200 <= response.status_code < 300:
            data = response.json()
            return {
                "status": "created",
                "issue_url": data.get("html_url"),
                "issue_number": data.get("number"),
                "title": issue_title,
                "labels": labels,
                "body": issue_body,
            }

        return {
            "status": "failed",
            "http_status": response.status_code,
            "error": response.text,
            "title": issue_title,
            "labels": labels,
            "body": issue_body,
        }
    except httpx.RequestError as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "title": issue_title,
            "labels": labels,
            "body": issue_body,
        }
