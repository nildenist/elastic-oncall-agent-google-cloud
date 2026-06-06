from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from app.demo_data import get_demo_alert_payload
from app.elastic_client import (
    get_elastic_client,
    get_latest_incident_brief,
    save_incident_brief,
    seed_demo_data,
)
from app.notifier import format_incident_brief_for_slack, send_slack_notification
from app.schemas import AlertPayload, FollowUpRequest
from app.triage_agent import answer_followup, build_incident_brief_from_elastic


app = FastAPI(
    title="Elastic On-Call Agent: Agentic Ops with Google Cloud",
    version="0.1.0",
    description=(
        "Alert-triggered incident triage agent using Google Cloud, Gemini, "
        "Agent Builder concepts, Cloud Run, and Elastic operational evidence."
    ),
)


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "name": "Elastic On-Call Agent: Agentic Ops with Google Cloud",
        "status": "running",
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
    }


@app.post("/seed-demo-data")
def seed_data() -> Dict[str, Any]:
    try:
        client = get_elastic_client()
        result = seed_demo_data(client)
        return {
            "status": "seeded",
            "result": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/simulate-incident")
def simulate_incident() -> Dict[str, Any]:
    try:
        payload = AlertPayload(**get_demo_alert_payload())
        return triage_alert(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/triage-alert")
def triage_alert(alert: AlertPayload) -> Dict[str, Any]:
    try:
        client = get_elastic_client()

        incident_brief = build_incident_brief_from_elastic(
            client=client,
            alert=alert,
        )

        incident_json = incident_brief.model_dump(mode="json")

        save_result = save_incident_brief(
            client=client,
            incident_brief=incident_json,
        )

        slack_message = format_incident_brief_for_slack(incident_json)
        slack_result = send_slack_notification(slack_message)

        return {
            "status": "triaged",
            "incident": incident_json,
            "elastic_save_result": save_result,
            "slack_result": slack_result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/incidents/latest")
def latest_incident() -> Dict[str, Any]:
    try:
        client = get_elastic_client()
        latest = get_latest_incident_brief(client)

        if latest is None:
            return {
                "status": "empty",
                "incident": None,
            }

        return {
            "status": "found",
            "incident": latest,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/ask-followup")
def ask_followup(request: FollowUpRequest) -> Dict[str, Any]:
    try:
        client = get_elastic_client()
        latest = get_latest_incident_brief(client)

        response = answer_followup(
            question=request.question,
            latest_brief=latest,
        )

        return {
            "status": "answered",
            "response": response,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
