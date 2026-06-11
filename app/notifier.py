from typing import Any, Dict

import requests

from app.config import get_settings


def send_slack_notification(message: str) -> Dict[str, Any]:
    settings = get_settings()

    if not settings.slack_webhook_url:
        return {
            "sent": False,
            "reason": "SLACK_WEBHOOK_URL is not configured. Skipping Slack notification.",
        }

    response = requests.post(
        settings.slack_webhook_url,
        json={"text": message},
        timeout=10,
    )

    return {
        "sent": response.status_code >= 200 and response.status_code < 300,
        "status_code": response.status_code,
        "response_text": response.text,
    }


def format_incident_brief_for_slack(incident_brief: Dict[str, Any]) -> str:
    evidence_lines = []
    for item in incident_brief.get("evidence", [])[:5]:
        evidence_lines.append(
            f"- {item.get('title')}: {item.get('detail')}"
        )

    action_lines = []
    for item in incident_brief.get("next_actions", [])[:4]:
        approval = "approval required" if item.get("requires_human_approval") else "no approval required"
        action_lines.append(
            f"- {item.get('title')}: {item.get('description')} ({approval})"
        )

    return (
        f"*Active incident detected*\n\n"
        f"*Summary:*\n{incident_brief.get('summary')}\n\n"
        f"*Probable root cause:*\n{incident_brief.get('probable_root_cause')}\n\n"
        f"*Confidence:* {incident_brief.get('confidence')}\n\n"
        f"*Evidence:*\n" + "\n".join(evidence_lines) + "\n\n"
        f"*Next actions:*\n" + "\n".join(action_lines) + "\n\n"
        f"*Human approval required:* {incident_brief.get('human_approval_required')}"
    )

    def format_resolved_message_for_slack(
        service: str,
        rolled_from: str,
        rolled_to: str,
    ) -> str:
        return (
            f"*Incident resolved* \u2713\n\n"
            f"*Service:* {service}\n"
            f"*Action:* Rolled back Cloud Run traffic from `{rolled_from}` to `{rolled_to}`\n"
            f"*Verification:* Health check passed. Error rate returned to baseline.\n"
            f"*Follow-up:* Review `{rolled_from}` before redeployment."
        )
