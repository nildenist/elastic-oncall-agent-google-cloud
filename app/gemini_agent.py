import json
import re
from typing import Any, Dict, Optional

from google import genai

from app.config import get_settings


def _get_client() -> genai.Client:
    settings = get_settings()

    if not settings.google_cloud_project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not configured.")

    return genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )


def _extract_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response did not contain a JSON object.")

    return json.loads(cleaned[start : end + 1])


def generate_incident_brief_with_gemini(
    alert_payload: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    client = _get_client()

    prompt = f"""
You are Elastic On-Call Agent, an incident triage agent built with Google Cloud Gemini.

You must reason only from the Elastic evidence bundle below.
Do not invent logs, metrics, deployments, services, or incidents.
If evidence is missing, say so.

Your job:
- identify probable root cause
- explain why the evidence supports it
- produce a timeline
- produce hypotheses
- produce safe next actions
- require human approval before destructive actions

Return ONLY valid JSON. No markdown.

JSON shape:
{{
  "summary": "string",
  "probable_root_cause": "string",
  "confidence": "low|medium|high",
  "affected_services": ["string"],
  "timeline": ["string"],
  "hypotheses": [
    {{
      "title": "string",
      "explanation": "string",
      "confidence": "low|medium|high",
      "supporting_evidence": ["string"]
    }}
  ],
  "next_actions": [
    {{
      "title": "string",
      "description": "string",
      "requires_human_approval": true,
      "risk_level": "low|medium|high"
    }}
  ],
  "human_approval_required": true
}}

Alert payload:
{json.dumps(alert_payload, indent=2, default=str)}

Elastic evidence bundle:
{json.dumps(evidence_bundle, indent=2, default=str)}
"""

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        parsed = _extract_json(response.text or "")
        parsed["reasoning_engine"] = f"Gemini on Vertex AI: {settings.gemini_model}"
        return parsed
    except Exception as exc:
        print(f"Gemini incident reasoning failed, falling back to deterministic logic: {exc}")
        return None


def answer_followup_with_gemini(
    question: str,
    latest_brief: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    client = _get_client()

    prompt = f"""
You are Elastic On-Call Agent, a Gemini-backed incident follow-up assistant.

Answer the user's follow-up question using only the incident brief below.
Do not invent facts.
Keep the answer concise and operational.
Mention evidence explicitly.
Do not recommend destructive execution without human approval.

Return ONLY valid JSON. No markdown.

JSON shape:
{{
  "answer": "string",
  "evidence_used": ["string"]
}}

Question:
{question}

Incident brief:
{json.dumps(latest_brief, indent=2, default=str)}
"""

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        parsed = _extract_json(response.text or "")
        parsed["reasoning_engine"] = f"Gemini on Vertex AI: {settings.gemini_model}"
        return parsed
    except Exception as exc:
        print(f"Gemini follow-up reasoning failed, falling back to deterministic logic: {exc}")
        return None
