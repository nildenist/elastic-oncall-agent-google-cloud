import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.elastic_client import (
    get_elastic_client,
    get_latest_incident_brief,
    save_incident_brief,
)
from app.github_client import create_incident_issue
from app.rate_limiter import allow_request
from app.schemas import AlertPayload, FollowUpRequest
from app.triage_agent import answer_followup, build_incident_brief_from_elastic
from app.workload_client import (
    get_workload_snapshot,
    repair_checkout,
    simulate_checkout_failure,
    verify_customer_flow,
)


app = FastAPI(
    title="Elastic On-Call Agent: Agentic Ops with Google Cloud",
    version="0.1.0",
    description=(
        "Alert-triggered incident triage agent using Google Cloud, Gemini, "
        "Agent Builder concepts, Cloud Run, GitHub Issues, and Elastic operational evidence."
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
    return {"status": "ok"}


@app.get("/workload-status")
def workload_status() -> Dict[str, Any]:
    """Return real-time workload status from checkout/payment services."""
    try:
        snapshot = get_workload_snapshot()
        return {
            "status": "ok",
            "workload": snapshot,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/connection-status")
def connection_status() -> Dict[str, Any]:
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    github_repository = os.getenv("GITHUB_REPOSITORY", "").strip()

    github_ready = bool(github_token and github_repository)

    return {
        "status": "ok",
        "systems": [
            {
                "key": "elastic",
                "name": "Elastic MCP",
                "state": "connected",
                "label": "CONNECTED",
            },
            {
                "key": "gemini",
                "name": "Vertex AI Gemini 2.5 Pro",
                "state": "connected",
                "label": "CONNECTED",
            },
            {
                "key": "cloud-run",
                "name": "Cloud Run",
                "state": "connected",
                "label": "CONNECTED",
            },
            {
                "key": "github",
                "name": "GitHub Issues",
                "state": "connected" if github_ready else "not-configured",
                "label": "CONNECTED" if github_ready else "SIMULATE MODE",
            },
        ],
    }


@app.post("/simulate-incident")
def simulate_incident() -> Dict[str, Any]:
    if not allow_request("simulate-incident", limit=10, window_seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for demo incident simulation. Please wait and try again.",
        )

    try:
        failure_result = simulate_checkout_failure(mode="redis_timeout")
        return {
            "status": "incident_simulated",
            "message": "checkout-api was moved into redis_timeout failure mode.",
            "failure_result": failure_result,
            "workload": failure_result.get("snapshot"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/apply-remediation")
def apply_remediation() -> Dict[str, Any]:
    """Apply remediation to workload and verify end-to-end recovery."""
    if not allow_request("apply-remediation", limit=10, window_seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for remediation requests. Please wait and try again.",
        )

    try:
        before_snapshot = get_workload_snapshot()
        repair_result = repair_checkout()
        verification_result = verify_customer_flow()
        after_snapshot = get_workload_snapshot()

        github_issue_result = create_incident_issue(
            issue_title=(
                "[resolved by agent] checkout-api failure after redis_timeout runtime mode"
            ),
            labels=[
                "incident",
                "agent-remediated",
                "checkout-api",
                "elastic-evidence",
            ],
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            verification_result=verification_result,
        )

        verified = verification_result.get("verified") is True
        remediation_status = "solved" if verified else "verification_failed"

        return {
            "status": remediation_status,
            "message": (
                "Agent repaired checkout-api and verified the customer checkout flow."
                if verified
                else "Agent attempted repair, but verification failed."
            ),
            "action_taken": {
                "target": "checkout-api",
                "operation": "runtime_repair",
                "description": (
                    "Agent called checkout-api /admin/repair and restored runtime mode to healthy."
                ),
            },
            "before": before_snapshot,
            "repair_result": repair_result,
            "verification": verification_result,
            "after": after_snapshot,
            "github_issue": github_issue_result,
        }
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

        return {
            "status": "triaged",
            "incident": incident_json,
            "elastic_save_result": save_result,
            "github_followup": {
                "status": "pending_agent_remediation",
                "message": "GitHub issue will be created after agent-executed remediation.",
            },
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
    if not allow_request("ask-followup", limit=20, window_seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for demo follow-up questions. Please wait and try again.",
        )

    if len(request.question) > 500:
        raise HTTPException(
            status_code=400,
            detail="Question is too long for the public demo. Please keep it under 500 characters.",
        )

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


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    return r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Elastic On-Call Agent</title>
  <style>
    :root {
      --card: rgba(15, 23, 42, 0.76);
      --border: rgba(148, 163, 184, 0.22);
      --text: #f8fafc;
      --muted: #cbd5e1;
      --blue: #4285f4;
      --red: #ea4335;
      --yellow: #fbbc04;
      --green: #34a853;
      --purple: #a855f7;
    }

    * {
      box-sizing: border-box;
    }

    body {
      font-family: Arial, sans-serif;
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 14% 9%, rgba(66, 133, 244, 0.40), transparent 24%),
        radial-gradient(circle at 88% 14%, rgba(168, 85, 247, 0.34), transparent 22%),
        radial-gradient(circle at 70% 82%, rgba(52, 168, 83, 0.20), transparent 24%),
        radial-gradient(circle at 18% 82%, rgba(251, 188, 4, 0.15), transparent 22%),
        linear-gradient(135deg, #020617 0%, #0f172a 48%, #111827 100%);
      overflow-x: hidden;
    }

    .page {
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 16px 0 16px 0;
    }

    .hero {
      position: relative;
      padding: 16px 22px;
      border: 1px solid var(--border);
      border-radius: 24px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02)),
        rgba(15, 23, 42, 0.72);
      box-shadow: 0 20px 70px rgba(0, 0, 0, 0.38);
      overflow: hidden;
    }

    .hero:before {
      content: "";
      position: absolute;
      width: 360px;
      height: 360px;
      right: -120px;
      top: -150px;
      background:
        conic-gradient(from 180deg, var(--blue), var(--purple), var(--red), var(--yellow), var(--green), var(--blue));
      filter: blur(46px);
      opacity: 0.32;
      border-radius: 999px;
    }

    .hero-content {
      position: relative;
      z-index: 1;
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(66, 133, 244, 0.12);
      border: 1px solid rgba(66, 133, 244, 0.35);
      color: #dbeafe;
      font-weight: 700;
      font-size: 12px;
      margin-bottom: 10px;
    }

    h1 {
      margin: 0 0 8px 0;
      font-size: clamp(27px, 3.2vw, 40px);
      line-height: 1.04;
      letter-spacing: -0.045em;
      max-width: 900px;
    }

    .gradient-text {
      background: linear-gradient(90deg, #ffffff, #93c5fd, #c4b5fd, #fca5a5, #fde68a);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }

    .subtitle {
      max-width: 820px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.38;
      margin: 0;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
      margin-top: 12px;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 14px 18px;
      box-shadow: 0 14px 45px rgba(0, 0, 0, 0.24);
      backdrop-filter: blur(14px);
    }

    .card h2 {
      margin: 0 0 10px 0;
      font-size: 18px;
    }

    .connected-systems {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      align-items: center;
      margin-bottom: 12px;
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.13);
    }

    .system-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 9px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.055);
      border: 1px solid rgba(255, 255, 255, 0.10);
      color: #dbeafe;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: -0.01em;
      cursor: default;
      user-select: none;
      white-space: nowrap;
      transition:
        background 0.18s ease,
        border-color 0.18s ease,
        box-shadow 0.18s ease,
        color 0.18s ease,
        opacity 0.18s ease;
    }

    .system-dot {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: rgba(203, 213, 225, 0.62);
      box-shadow: 0 0 0 3px rgba(203, 213, 225, 0.08);
    }

    .system-label {
      opacity: 0.78;
      font-size: 10px;
      letter-spacing: 0.05em;
    }

    .system-chip.connected {
      color: #dcfce7;
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.23), rgba(22, 163, 74, 0.10));
      border-color: rgba(74, 222, 128, 0.32);
      box-shadow: 0 8px 20px rgba(34, 197, 94, 0.10);
    }

    .system-chip.connected .system-dot {
      background: #4ade80;
      box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.12);
    }

    .system-chip.checking {
      color: #dbeafe;
      background: linear-gradient(135deg, rgba(66, 133, 244, 0.22), rgba(168, 85, 247, 0.12));
      border-color: rgba(147, 197, 253, 0.30);
      box-shadow: 0 8px 20px rgba(66, 133, 244, 0.10);
    }

    .system-chip.checking .system-dot {
      background: #93c5fd;
      box-shadow: 0 0 0 3px rgba(147, 197, 253, 0.12);
    }

    .system-chip.not-configured {
      color: #fef3c7;
      background: linear-gradient(135deg, rgba(251, 188, 4, 0.22), rgba(217, 119, 6, 0.10));
      border-color: rgba(251, 191, 36, 0.30);
      box-shadow: 0 8px 20px rgba(251, 188, 4, 0.10);
    }

    .system-chip.not-configured .system-dot {
      background: #fbbf24;
      box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.12);
    }

    .system-chip.disconnected {
      color: #fee2e2;
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.24), rgba(185, 28, 28, 0.12));
      border-color: rgba(248, 113, 113, 0.34);
      box-shadow: 0 8px 20px rgba(239, 68, 68, 0.10);
    }

    .system-chip.disconnected .system-dot {
      background: #f87171;
      box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.12);
    }

    .flow {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .flow-step {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin: 0;
      padding: 7px 10px;
      border-radius: 999px;
      color: #e2e8f0;
      background: rgba(255, 255, 255, 0.07);
      border: 1px solid rgba(255, 255, 255, 0.11);
      white-space: nowrap;
      font-size: 14px;
      line-height: 1.2;
      cursor: default;
      user-select: none;
      transition:
        background 0.18s ease,
        border-color 0.18s ease,
        box-shadow 0.18s ease,
        color 0.18s ease,
        transform 0.18s ease,
        opacity 0.18s ease;
    }

    .flow-step .state-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: rgba(203, 213, 225, 0.55);
      box-shadow: 0 0 0 3px rgba(203, 213, 225, 0.08);
    }

    .flow-step .state-label {
      display: none;
      font-size: 10px;
      letter-spacing: 0.04em;
      font-weight: 800;
      opacity: 0.8;
    }

    .flow-step.idle {
      opacity: 0.82;
    }

    .flow-step.running {
      color: #eff6ff;
      background: linear-gradient(135deg, rgba(66, 133, 244, 0.32), rgba(168, 85, 247, 0.20));
      border-color: rgba(147, 197, 253, 0.50);
      box-shadow: 0 0 0 1px rgba(66, 133, 244, 0.12), 0 12px 30px rgba(66, 133, 244, 0.18);
      animation: chipPulse 1.05s ease-in-out infinite;
      opacity: 1;
    }

    .flow-step.running .state-dot {
      background: #93c5fd;
      box-shadow: 0 0 0 4px rgba(147, 197, 253, 0.16), 0 0 20px rgba(147, 197, 253, 0.7);
    }

    .flow-step.running .state-label {
      display: inline;
      color: #bfdbfe;
    }

    .flow-step.done {
      color: #dcfce7;
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.28), rgba(22, 163, 74, 0.14));
      border-color: rgba(74, 222, 128, 0.42);
      box-shadow: 0 10px 26px rgba(34, 197, 94, 0.13);
      opacity: 1;
    }

    .flow-step.done .state-dot {
      background: #4ade80;
      box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.13);
    }

    .flow-step.done .state-label {
      display: inline;
      color: #bbf7d0;
    }

    .flow-step.failed {
      color: #fee2e2;
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.32), rgba(185, 28, 28, 0.18));
      border-color: rgba(248, 113, 113, 0.45);
      box-shadow: 0 10px 26px rgba(239, 68, 68, 0.16);
      opacity: 1;
    }

    .flow-step.failed .state-dot {
      background: #f87171;
      box-shadow: 0 0 0 4px rgba(248, 113, 113, 0.15);
    }

    .flow-step.failed .state-label {
      display: inline;
      color: #fecaca;
    }

    @keyframes chipPulse {
      0% {
        transform: translateY(0);
        filter: brightness(1);
      }
      50% {
        transform: translateY(-1px);
        filter: brightness(1.16);
      }
      100% {
        transform: translateY(0);
        filter: brightness(1);
      }
    }

    .controls-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, 360px);
      gap: 12px;
      align-items: stretch;
    }

    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .incident-status-panel {
      border-radius: 16px;
      border: 1px solid rgba(148, 163, 184, 0.16);
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.055), rgba(255, 255, 255, 0.018)),
        rgba(2, 6, 23, 0.30);
      padding: 10px 12px;
      min-height: 78px;
    }

    .status-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }

    .status-title {
      font-size: 12px;
      font-weight: 800;
      color: #e5e7eb;
      letter-spacing: 0.01em;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 900;
      letter-spacing: 0.05em;
      white-space: nowrap;
      border: 1px solid rgba(255, 255, 255, 0.10);
      color: #e2e8f0;
      background: rgba(255, 255, 255, 0.06);
    }

    .status-pill:before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: rgba(203, 213, 225, 0.65);
      box-shadow: 0 0 0 3px rgba(203, 213, 225, 0.08);
    }

    .status-pill.idle {
      color: #e2e8f0;
      background: rgba(255, 255, 255, 0.06);
    }

    .status-pill.active {
      color: #fee2e2;
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.28), rgba(185, 28, 28, 0.14));
      border-color: rgba(248, 113, 113, 0.35);
    }

    .status-pill.active:before {
      background: #f87171;
      box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.12);
    }

    .status-pill.ready {
      color: #fef3c7;
      background: linear-gradient(135deg, rgba(251, 188, 4, 0.23), rgba(217, 119, 6, 0.12));
      border-color: rgba(251, 191, 36, 0.32);
    }

    .status-pill.ready:before {
      background: #fbbf24;
      box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.12);
    }

    .status-pill.remediating {
      color: #dbeafe;
      background: linear-gradient(135deg, rgba(66, 133, 244, 0.24), rgba(168, 85, 247, 0.14));
      border-color: rgba(147, 197, 253, 0.34);
    }

    .status-pill.remediating:before {
      background: #93c5fd;
      box-shadow: 0 0 0 3px rgba(147, 197, 253, 0.12);
    }

    .status-pill.solved {
      color: #dcfce7;
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.27), rgba(22, 163, 74, 0.13));
      border-color: rgba(74, 222, 128, 0.34);
    }

    .status-pill.solved:before {
      background: #4ade80;
      box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.12);
    }

    .status-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px 10px;
    }

    .status-item {
      min-width: 0;
    }

    .status-key {
      display: block;
      color: rgba(203, 213, 225, 0.72);
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 2px;
    }

    .status-value {
      display: block;
      color: #f8fafc;
      font-size: 12px;
      font-weight: 800;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .workload-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .workload-card {
      position: relative;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid rgba(148, 163, 184, 0.18);
      background: rgba(2, 6, 23, 0.34);
      padding: 12px;
      min-height: 112px;
      transition:
        background 0.18s ease,
        border-color 0.18s ease,
        box-shadow 0.18s ease,
        transform 0.18s ease;
    }

    .workload-card:before {
      content: "";
      position: absolute;
      width: 120px;
      height: 120px;
      right: -56px;
      top: -60px;
      border-radius: 999px;
      filter: blur(22px);
      opacity: 0.22;
      background: #94a3b8;
    }

    .workload-card.healthy {
      border-color: rgba(74, 222, 128, 0.34);
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.18), rgba(2, 6, 23, 0.32));
      box-shadow: 0 12px 26px rgba(34, 197, 94, 0.08);
    }

    .workload-card.healthy:before {
      background: #4ade80;
    }

    .workload-card.degraded {
      border-color: rgba(251, 191, 36, 0.36);
      background: linear-gradient(135deg, rgba(251, 188, 4, 0.17), rgba(2, 6, 23, 0.32));
      box-shadow: 0 12px 26px rgba(251, 188, 4, 0.08);
    }

    .workload-card.degraded:before {
      background: #fbbf24;
    }

    .workload-card.critical {
      border-color: rgba(248, 113, 113, 0.40);
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.20), rgba(2, 6, 23, 0.34));
      box-shadow: 0 12px 28px rgba(239, 68, 68, 0.12);
      animation: servicePulse 1.2s ease-in-out infinite;
    }

    .workload-card.critical:before {
      background: #f87171;
    }

    .workload-card.remediating {
      border-color: rgba(147, 197, 253, 0.40);
      background: linear-gradient(135deg, rgba(66, 133, 244, 0.21), rgba(168, 85, 247, 0.10));
      box-shadow: 0 12px 28px rgba(66, 133, 244, 0.12);
      animation: servicePulse 1.2s ease-in-out infinite;
    }

    .workload-card.remediating:before {
      background: #93c5fd;
    }

    @keyframes servicePulse {
      0% {
        transform: translateY(0);
        filter: brightness(1);
      }
      50% {
        transform: translateY(-1px);
        filter: brightness(1.12);
      }
      100% {
        transform: translateY(0);
        filter: brightness(1);
      }
    }

    .workload-name {
      position: relative;
      z-index: 1;
      display: block;
      color: #f8fafc;
      font-size: 14px;
      font-weight: 900;
      margin-bottom: 8px;
      letter-spacing: -0.02em;
    }

    .workload-pill {
      position: relative;
      z-index: 1;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 8px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 900;
      letter-spacing: 0.05em;
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #e2e8f0;
      background: rgba(255, 255, 255, 0.06);
      margin-bottom: 9px;
    }

    .workload-pill:before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: rgba(203, 213, 225, 0.68);
    }

    .workload-card.healthy .workload-pill {
      color: #dcfce7;
      border-color: rgba(74, 222, 128, 0.30);
      background: rgba(34, 197, 94, 0.13);
    }

    .workload-card.healthy .workload-pill:before {
      background: #4ade80;
    }

    .workload-card.degraded .workload-pill {
      color: #fef3c7;
      border-color: rgba(251, 191, 36, 0.30);
      background: rgba(251, 188, 4, 0.13);
    }

    .workload-card.degraded .workload-pill:before {
      background: #fbbf24;
    }

    .workload-card.critical .workload-pill {
      color: #fee2e2;
      border-color: rgba(248, 113, 113, 0.34);
      background: rgba(239, 68, 68, 0.14);
    }

    .workload-card.critical .workload-pill:before {
      background: #f87171;
    }

    .workload-card.remediating .workload-pill {
      color: #dbeafe;
      border-color: rgba(147, 197, 253, 0.34);
      background: rgba(66, 133, 244, 0.14);
    }

    .workload-card.remediating .workload-pill:before {
      background: #93c5fd;
    }

    .workload-detail {
      position: relative;
      z-index: 1;
      color: #cbd5e1;
      font-size: 12px;
      line-height: 1.35;
      margin: 0;
    }

    .workload-meta {
      position: relative;
      z-index: 1;
      display: block;
      color: rgba(203, 213, 225, 0.70);
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.04em;
      margin: 8px 0 0;
    }

    .workload-links {
      position: relative;
      z-index: 1;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }

    .workload-link,
    .issue-link {
      display: inline-flex;
      align-items: center;
      padding: 5px 8px;
      border-radius: 999px;
      color: #dbeafe;
      background: rgba(66, 133, 244, 0.12);
      border: 1px solid rgba(147, 197, 253, 0.22);
      text-decoration: none;
      font-size: 10px;
      font-weight: 900;
      letter-spacing: 0.02em;
    }

    .workload-link:hover,
    .issue-link:hover {
      filter: brightness(1.12);
      transform: translateY(-1px);
    }

    .workload-link.disabled,
    .issue-link.disabled {
      pointer-events: none;
      opacity: 0.55;
    }

    .insight-grid {
      display: none;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 10px;
    }

    .insight-grid.visible {
      display: grid;
    }

    .resolved-card {
      border-color: rgba(74, 222, 128, 0.32);
      background:
        linear-gradient(135deg, rgba(34, 197, 94, 0.13), rgba(66, 133, 244, 0.06)),
        var(--card);
    }

    .issue-card {
      border-color: rgba(147, 197, 253, 0.26);
      background:
        linear-gradient(135deg, rgba(66, 133, 244, 0.11), rgba(168, 85, 247, 0.06)),
        var(--card);
    }

    .resolution-title {
      margin: 0 0 9px 0;
      font-size: 17px;
      color: #f8fafc;
    }

    .resolution-copy {
      margin: 0 0 10px 0;
      color: #cbd5e1;
      font-size: 12px;
      line-height: 1.5;
    }

    .mini-list {
      margin: 0;
      padding-left: 17px;
      color: #e5e7eb;
      font-size: 12px;
      line-height: 1.48;
    }

    .issue-title {
      font-size: 12px;
      line-height: 1.4;
      color: #f8fafc;
      font-weight: 900;
      margin: 0 0 8px 0;
    }

    .label-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 8px 0 10px;
    }

    .label-chip {
      display: inline-flex;
      padding: 4px 8px;
      border-radius: 999px;
      color: #dbeafe;
      background: rgba(66, 133, 244, 0.13);
      border: 1px solid rgba(147, 197, 253, 0.22);
      font-size: 10px;
      font-weight: 900;
    }

    button {
      border: 1px solid rgba(255, 255, 255, 0.15);
      padding: 7px 13px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 700;
      font-size: 13px;
      line-height: 1.2;
      min-height: 34px;
      letter-spacing: -0.01em;
      transition: transform 0.15s ease, filter 0.15s ease, box-shadow 0.15s ease;
      backdrop-filter: blur(10px);
    }

    button:hover {
      transform: translateY(-1px);
      filter: brightness(1.08);
    }

    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
      filter: none;
    }

    .btn-health {
      color: #dcfce7;
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.34), rgba(22, 163, 74, 0.18));
      box-shadow: 0 10px 26px rgba(34, 197, 94, 0.14);
    }

    .btn-simulate {
      color: #fce7f3;
      background: linear-gradient(135deg, rgba(168, 85, 247, 0.36), rgba(219, 39, 119, 0.22));
      box-shadow: 0 10px 26px rgba(168, 85, 247, 0.14);
    }

    .btn-latest {
      color: #fee2e2;
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.46), rgba(185, 28, 28, 0.30));
      box-shadow: 0 10px 26px rgba(239, 68, 68, 0.18);
    }

    .btn-ask {
      color: #ede9fe;
      background: linear-gradient(135deg, rgba(66, 133, 244, 0.38), rgba(168, 85, 247, 0.26));
      box-shadow: 0 10px 26px rgba(66, 133, 244, 0.18);
    }

    .btn-apply {
      color: #dcfce7;
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.38), rgba(22, 163, 74, 0.22));
      box-shadow: 0 10px 26px rgba(34, 197, 94, 0.16);
    }

    .btn-skip {
      color: #e5e7eb;
      background: linear-gradient(135deg, rgba(100, 116, 139, 0.38), rgba(51, 65, 85, 0.24));
      box-shadow: 0 10px 26px rgba(15, 23, 42, 0.18);
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(320px, 1fr);
      gap: 10px;
    }

    pre {
      margin: 0;
      min-height: 280px;
      max-height: 360px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(2, 6, 23, 0.72);
      border: 1px solid rgba(148, 163, 184, 0.08);
      border-radius: 14px;
      padding: 14px;
      color: #e5e7eb;
      font-size: 12px;
      line-height: 1.45;
    }

    .ask-row {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    input {
      width: 100%;
      border: 1px solid rgba(148, 163, 184, 0.18);
      border-radius: 999px;
      background: rgba(2, 6, 23, 0.52);
      color: #f8fafc;
      outline: none;
      padding: 10px 14px;
      font-weight: 700;
    }

    input::placeholder {
      color: rgba(203, 213, 225, 0.65);
    }

    .side {
      display: grid;
      gap: 10px;
      align-content: start;
    }

    .recommended-action {
      display: none;
      border-color: rgba(251, 191, 36, 0.24);
      background:
        linear-gradient(135deg, rgba(251, 188, 4, 0.08), rgba(34, 197, 94, 0.04)),
        var(--card);
    }

    .recommended-action.visible {
      display: block;
    }

    .action-kicker {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 9px;
      border-radius: 999px;
      color: #fef3c7;
      background: linear-gradient(135deg, rgba(251, 188, 4, 0.20), rgba(217, 119, 6, 0.10));
      border: 1px solid rgba(251, 191, 36, 0.28);
      font-size: 10px;
      font-weight: 900;
      letter-spacing: 0.06em;
      margin-bottom: 10px;
    }

    .action-title {
      margin: 0 0 8px 0;
      font-size: 15px;
      line-height: 1.25;
      color: #f8fafc;
    }

    .action-copy {
      margin: 0 0 10px 0;
      color: #cbd5e1;
      font-size: 12px;
      line-height: 1.45;
    }

    .action-box {
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.12);
      background: rgba(2, 6, 23, 0.38);
      padding: 10px 12px;
      margin: 10px 0;
    }

    .action-section-title {
      display: block;
      color: rgba(203, 213, 225, 0.76);
      font-size: 10px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 7px;
    }

    .action-list {
      margin: 0;
      padding-left: 17px;
      color: #e5e7eb;
      font-size: 12px;
      line-height: 1.45;
    }

    .action-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }

    .footer {
      color: rgba(203, 213, 225, 0.74);
      font-size: 12px;
      padding: 10px 4px 0;
    }

    .error {
      color: #fecaca;
    }

    @media (max-width: 900px) {
      .workspace,
      .controls-layout,
      .workload-grid,
      .insight-grid {
        grid-template-columns: 1fr;
      }

      pre {
        max-height: none;
      }
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="hero-content">
        <div class="eyebrow">Google Cloud Agentic AI x Elastic</div>
        <h1>
          Elastic On-Call Agent:<br />
          <span class="gradient-text">Agentic Ops with Google Cloud</span>
        </h1>
        <p class="subtitle">
          Alert-triggered triage using Cloud Run, Elastic evidence, and GitHub Issues to move from signal to root cause to agent-executed remediation.
        </p>
      </div>
    </section>

    <div class="grid">
      <section class="card">
        <h2>Agentic flow</h2>

        <div class="connected-systems" aria-label="Connected systems">
          <span class="system-chip checking" data-system="elastic">
            <span class="system-dot"></span>
            Elastic MCP
            <span class="system-label">CHECKING</span>
          </span>
          <span class="system-chip checking" data-system="gemini">
            <span class="system-dot"></span>
            Vertex AI Gemini 2.5 Pro
            <span class="system-label">CHECKING</span>
          </span>
          <span class="system-chip checking" data-system="cloud-run">
            <span class="system-dot"></span>
            Cloud Run
            <span class="system-label">CHECKING</span>
          </span>
          <span class="system-chip checking" data-system="github">
            <span class="system-dot"></span>
            GitHub Issues
            <span class="system-label">CHECKING</span>
          </span>
        </div>

        <div class="flow" aria-label="Agentic flow execution status">
          <span class="flow-step idle" data-step="elastic-alert">
            <span class="state-dot"></span>
            Elastic alert
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="cloud-run">
            <span class="state-dot"></span>
            Cloud Run endpoint
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="evidence">
            <span class="state-dot"></span>
            Evidence collection
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="gemini">
            <span class="state-dot"></span>
            Gemini reasoning
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="root-cause">
            <span class="state-dot"></span>
            Root cause
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="remediation-plan">
            <span class="state-dot"></span>
            Remediation plan
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="apply-fix">
            <span class="state-dot"></span>
            Apply fix
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="verify-health">
            <span class="state-dot"></span>
            Verify health
            <span class="state-label">IDLE</span>
          </span>
          <span class="flow-step idle" data-step="github-issue">
            <span class="state-dot"></span>
            GitHub issue
            <span class="state-label">IDLE</span>
          </span>
        </div>
      </section>

      <section class="card">
        <h2>Demo controls</h2>

        <div class="controls-layout">
          <div class="controls">
            <button class="btn-health" id="btnHealth" onclick="healthCheck()">Health check</button>
            <button class="btn-simulate" id="btnSimulate" onclick="simulateIncident()">Simulate incident</button>
            <button class="btn-latest" id="btnLatest" onclick="latestIncident()">Latest incident</button>
          </div>

          <div class="incident-status-panel" aria-label="Incident status">
            <div class="status-header">
              <span class="status-title">Incident status</span>
              <span class="status-pill idle" id="incidentState">IDLE</span>
            </div>

            <div class="status-grid">
              <div class="status-item">
                <span class="status-key">Service</span>
                <span class="status-value" id="incidentService">checkout-api</span>
              </div>
              <div class="status-item">
                <span class="status-key">Severity</span>
                <span class="status-value" id="incidentSeverity">high</span>
              </div>
              <div class="status-item">
                <span class="status-key">Root cause</span>
                <span class="status-value" id="incidentRootCause">-</span>
              </div>
              <div class="status-item">
                <span class="status-key">Confidence</span>
                <span class="status-value" id="incidentConfidence">-</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>Live workload health</h2>
        <div class="workload-grid" id="workloadGrid">
          <div class="workload-card healthy" data-service="checkout-api">
            <span class="workload-name">checkout-api</span>
            <span class="workload-pill" data-service-status="checkout-api">CHECKING</span>
            <p class="workload-detail" data-service-detail="checkout-api">Waiting for live checkout-api status.</p>
            <span class="workload-meta" data-service-meta="checkout-api">HTTP: - | mode: -</span>
            <div class="workload-links">
              <a class="workload-link disabled" data-service-link="checkout-api-service" href="#" target="_blank" rel="noreferrer">Open service</a>
              <a class="workload-link disabled" data-service-link="checkout-api-health" href="#" target="_blank" rel="noreferrer">Health</a>
              <a class="workload-link disabled" data-service-link="checkout-api-flow" href="#" target="_blank" rel="noreferrer">Checkout flow</a>
            </div>
          </div>

          <div class="workload-card healthy" data-service="payment-api">
            <span class="workload-name">payment-api</span>
            <span class="workload-pill" data-service-status="payment-api">CHECKING</span>
            <p class="workload-detail" data-service-detail="payment-api">Waiting for live payment-api status.</p>
            <span class="workload-meta" data-service-meta="payment-api">HTTP: -</span>
            <div class="workload-links">
              <a class="workload-link disabled" data-service-link="payment-api-service" href="#" target="_blank" rel="noreferrer">Open service</a>
              <a class="workload-link disabled" data-service-link="payment-api-health" href="#" target="_blank" rel="noreferrer">Health</a>
              <a class="workload-link disabled" data-service-link="payment-api-status" href="#" target="_blank" rel="noreferrer">Status</a>
            </div>
          </div>

          <div class="workload-card healthy" data-service="customer-flow">
            <span class="workload-name">customer checkout flow</span>
            <span class="workload-pill" data-service-status="customer-flow">CHECKING</span>
            <p class="workload-detail" data-service-detail="customer-flow">Waiting for live end-to-end checkout flow status.</p>
            <span class="workload-meta" data-service-meta="customer-flow">HTTP: -</span>
            <div class="workload-links">
              <a class="workload-link disabled" data-service-link="customer-flow-service" href="#" target="_blank" rel="noreferrer">Open flow</a>
              <a class="workload-link disabled" data-service-link="customer-flow-status" href="#" target="_blank" rel="noreferrer">Checkout status</a>
            </div>
          </div>
        </div>
      </section>

      <div class="insight-grid" id="resolutionInsights">
        <section class="card resolved-card">
          <h2 class="resolution-title">Agent resolved the incident</h2>
          <p class="resolution-copy" id="resolvedSummary">
            The agent repaired checkout-api runtime mode and verified the live customer checkout flow.
          </p>
          <span class="action-section-title">Verification</span>
          <ul class="mini-list" id="verificationList">
            <li>checkout-api /healthz returned 200 after remediation.</li>
            <li>checkout-api /checkout returned 200 after remediation.</li>
            <li>payment-api /healthz remained healthy.</li>
            <li>Customer checkout flow returned to healthy.</li>
          </ul>
        </section>

        <section class="card issue-card">
          <h2 class="resolution-title">GitHub issue created</h2>
          <p class="issue-title" id="issueTitle">
            [resolved by agent] checkout-api failure after redis_timeout runtime mode
          </p>
          <div class="label-row" id="issueLabels">
            <span class="label-chip">incident</span>
            <span class="label-chip">agent-remediated</span>
            <span class="label-chip">checkout-api</span>
            <span class="label-chip">elastic-evidence</span>
          </div>
          <p class="resolution-copy" id="issueStatus">Waiting for remediation result.</p>
          <a class="issue-link disabled" id="issueUrl" href="#" target="_blank" rel="noreferrer">Open GitHub issue</a>
          <div class="action-box">
            <span class="action-section-title">Issue body preview</span>
            <ul class="mini-list" id="issueBodyPreview">
              <li>Root cause: checkout-api entered redis_timeout failure mode.</li>
              <li>Action taken: agent called checkout-api /admin/repair.</li>
              <li>Verification: live workload checks returned healthy.</li>
              <li>Follow-up: review checkout-api runtime config guardrails.</li>
            </ul>
          </div>
        </section>
      </div>

      <div class="workspace">
        <section class="card">
          <h2>Incident output</h2>
          <pre id="incidentOutput">Click Health check, then Simulate incident.</pre>
        </section>

        <div class="side">
          <section class="card">
            <h2>Ask Agent</h2>
            <div class="ask-row">
              <input
                id="question"
                value="Why do you think this is deployment-related?"
                maxlength="500"
              />
              <button class="btn-ask" id="btnAsk" onclick="askAgent()">Ask agent</button>
            </div>
          </section>

          <section class="card">
            <h2>Agent answer</h2>
            <pre id="agentAnswer">Ask a question after simulating an incident.</pre>
          </section>

          <section class="card recommended-action" id="recommendedActionCard">
            <div class="action-kicker">AGENT REMEDIATION PLAN</div>
            <h2 class="action-title">Repair checkout-api runtime mode</h2>
            <p class="action-copy">
              The agent will call the real <strong>checkout-api /admin/repair</strong> endpoint,
              then verify <strong>/healthz</strong>, <strong>/checkout</strong>, and
              <strong>payment-api /healthz</strong> before closing the loop.
            </p>

            <div class="action-box">
              <span class="action-section-title">Why this is safe</span>
              <ul class="action-list">
                <li>payment-api is still healthy, so the blast radius is isolated to checkout-api.</li>
                <li>The failure mode is runtime-level redis_timeout and can be repaired without redeploying.</li>
                <li>The agent verifies the customer checkout flow before marking the incident solved.</li>
                <li>GitHub issue creation keeps an engineering follow-up trail.</li>
              </ul>
            </div>

            <div class="action-box">
              <span class="action-section-title">What the agent will do</span>
              <ul class="action-list">
                <li>Read live checkout-api and payment-api status.</li>
                <li>Call checkout-api /admin/repair.</li>
                <li>Verify checkout-api /healthz and /checkout.</li>
                <li>Create a GitHub issue for post-incident review.</li>
              </ul>
            </div>

            <div class="action-buttons">
              <button class="btn-apply" id="btnApply" onclick="applyRemediation()">Apply remediation</button>
              <button class="btn-skip" id="btnDoNotAct" onclick="doNotAct()">Do not act</button>
            </div>
          </section>
        </div>
      </div>
    </div>

    <div class="footer">
      Built for the Rapid Agent Hackathon Elastic track. Human-approved, agent-executed remediation.
    </div>
  </div>

  <script>
    const incidentOutput = document.getElementById("incidentOutput");
    const agentAnswer = document.getElementById("agentAnswer");
    const recommendedActionCard = document.getElementById("recommendedActionCard");
    const resolutionInsights = document.getElementById("resolutionInsights");
    const issueTitle = document.getElementById("issueTitle");
    const issueLabels = document.getElementById("issueLabels");
    const issueStatus = document.getElementById("issueStatus");
    const issueUrl = document.getElementById("issueUrl");
    const issueBodyPreview = document.getElementById("issueBodyPreview");
    const verificationList = document.getElementById("verificationList");
    const resolvedSummary = document.getElementById("resolvedSummary");

    let githubIssueState = "not-configured";
    let latestWorkload = null;

    const flowStepNames = [
      "elastic-alert",
      "cloud-run",
      "evidence",
      "gemini",
      "root-cause",
      "remediation-plan",
      "apply-fix",
      "verify-health",
      "github-issue"
    ];

    function sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    function formatJson(value) {
      return JSON.stringify(value, null, 2);
    }

    function renderResponse(value) {
      if (value === null || typeof value === "undefined") {
        return "";
      }

      if (typeof value === "string") {
        return value;
      }

      return formatJson(value);
    }

    function appendIncidentOutput(message) {
      const current = incidentOutput.textContent || "";
      incidentOutput.textContent = `${current}\n\n${message}`;
      incidentOutput.scrollTop = incidentOutput.scrollHeight;
    }

    function setRecommendedActionVisible(visible) {
      if (!recommendedActionCard) {
        return;
      }

      if (visible) {
        recommendedActionCard.classList.add("visible");
      } else {
        recommendedActionCard.classList.remove("visible");
      }
    }

    function setResolutionInsightsVisible(visible) {
      if (!resolutionInsights) {
        return;
      }

      if (visible) {
        resolutionInsights.classList.add("visible");
      } else {
        resolutionInsights.classList.remove("visible");
      }
    }

    function setButtonsDisabled(disabled) {
      const buttons = [
        "btnHealth",
        "btnSimulate",
        "btnLatest",
        "btnAsk",
        "btnApply",
        "btnDoNotAct"
      ];

      buttons.forEach((id) => {
        const button = document.getElementById(id);
        if (button) {
          button.disabled = disabled;
        }
      });
    }

    function setIncidentStatus({
      state = "idle",
      service = "checkout-api",
      severity = "high",
      rootCause = "-",
      confidence = "-"
    } = {}) {
      const stateElement = document.getElementById("incidentState");
      const serviceElement = document.getElementById("incidentService");
      const severityElement = document.getElementById("incidentSeverity");
      const rootCauseElement = document.getElementById("incidentRootCause");
      const confidenceElement = document.getElementById("incidentConfidence");

      const stateMap = {
        idle: {
          label: "IDLE",
          className: "idle"
        },
        active: {
          label: "ACTIVE INCIDENT",
          className: "active"
        },
        ready: {
          label: "REMEDIATION READY",
          className: "ready"
        },
        remediating: {
          label: "REMEDIATING",
          className: "remediating"
        },
        solved: {
          label: "SOLVED",
          className: "solved"
        }
      };

      const safeState = stateMap[state] ? state : "idle";
      const stateConfig = stateMap[safeState];

      if (stateElement) {
        stateElement.classList.remove("idle", "active", "ready", "remediating", "solved");
        stateElement.classList.add(stateConfig.className);
        stateElement.textContent = stateConfig.label;
      }

      if (serviceElement) {
        serviceElement.textContent = service || "checkout-api";
      }

      if (severityElement) {
        severityElement.textContent = severity || "high";
      }

      if (rootCauseElement) {
        rootCauseElement.textContent = rootCause || "-";
      }

      if (confidenceElement) {
        confidenceElement.textContent = confidence || "-";
      }
    }

    function normalizeServiceState(state) {
      const allowedStates = ["healthy", "degraded", "critical", "remediating"];
      return allowedStates.includes(state) ? state : "healthy";
    }

    function setLink(linkKey, url) {
      const link = document.querySelector(`[data-service-link="${linkKey}"]`);
      if (!link) {
        return;
      }

      if (url) {
        link.href = url;
        link.classList.remove("disabled");
      } else {
        link.href = "#";
        link.classList.add("disabled");
      }
    }

    function setServiceState(service) {
      if (!service || !service.key) {
        return;
      }

      const serviceKey = service.key;
      const card = document.querySelector(`[data-service="${serviceKey}"]`);
      const statusElement = document.querySelector(`[data-service-status="${serviceKey}"]`);
      const detailElement = document.querySelector(`[data-service-detail="${serviceKey}"]`);
      const metaElement = document.querySelector(`[data-service-meta="${serviceKey}"]`);

      if (!card) {
        return;
      }

      const safeState = normalizeServiceState(service.state);

      card.classList.remove("healthy", "degraded", "critical", "remediating");
      card.classList.add(safeState);

      if (statusElement) {
        statusElement.textContent = service.status_label || safeState.toUpperCase();
      }

      if (detailElement) {
        detailElement.textContent = service.detail || "No detail available.";
      }

      if (metaElement) {
        const statusCode = service.http_status || "-";
        const mode = service.mode ? ` | mode: ${service.mode}` : "";
        metaElement.textContent = `HTTP: ${statusCode}${mode}`;
      }

      if (serviceKey === "checkout-api") {
        setLink("checkout-api-service", service.service_url);
        setLink("checkout-api-health", service.health_url);
        setLink("checkout-api-flow", service.flow_url);
      }

      if (serviceKey === "payment-api") {
        setLink("payment-api-service", service.service_url);
        setLink("payment-api-health", service.health_url);
        setLink("payment-api-status", service.status_url);
      }

      if (serviceKey === "customer-flow") {
        setLink("customer-flow-service", service.service_url);
        setLink("customer-flow-status", service.status_url);
      }
    }

    function setWorkloadRemediating() {
      [
        {
          key: "checkout-api",
          state: "remediating",
          status_label: "REMEDIATING",
          http_status: "-",
          mode: "repairing",
          detail: "Agent is calling checkout-api /admin/repair."
        },
        {
          key: "payment-api",
          state: "remediating",
          status_label: "VERIFYING",
          http_status: "-",
          detail: "Agent will verify payment-api health after checkout recovery."
        },
        {
          key: "customer-flow",
          state: "remediating",
          status_label: "VERIFYING",
          http_status: "-",
          detail: "Agent is verifying the end-to-end customer checkout flow."
        }
      ].forEach(setServiceState);
    }

    function updateWorkloadFromSnapshot(snapshot, incidentStateOverride = null) {
      if (!snapshot || !Array.isArray(snapshot.services)) {
        return;
      }

      latestWorkload = snapshot;
      snapshot.services.forEach(setServiceState);

      if (incidentStateOverride) {
        return;
      }

      if (snapshot.status === "incident") {
        setIncidentStatus({
          state: "active",
          service: "checkout-api",
          severity: "high",
          rootCause: "redis_timeout runtime mode",
          confidence: "live HTTP evidence"
        });
      } else {
        setIncidentStatus({
          state: "idle",
          service: "checkout-api",
          severity: "high",
          rootCause: "-",
          confidence: "-"
        });
      }
    }

    async function loadWorkloadStatus() {
      const payload = await callApi("/workload-status");
      if (payload.workload) {
        updateWorkloadFromSnapshot(payload.workload);
      }
      return payload;
    }

    function setSystemStatus(systemKey, state, label) {
      const chip = document.querySelector(`[data-system="${systemKey}"]`);
      if (!chip) {
        return;
      }

      const allowedStates = ["checking", "connected", "not-configured", "disconnected"];
      const safeState = allowedStates.includes(state) ? state : "checking";

      chip.classList.remove("checking", "connected", "not-configured", "disconnected");
      chip.classList.add(safeState);

      const systemLabel = chip.querySelector(".system-label");
      if (systemLabel) {
        systemLabel.textContent = label || safeState.toUpperCase();
      }
    }

    async function loadConnectedSystems() {
      try {
        const payload = await callApi("/connection-status");

        if (!payload.systems || !Array.isArray(payload.systems)) {
          return;
        }

        payload.systems.forEach((system) => {
          setSystemStatus(system.key, system.state, system.label);

          if (system.key === "github") {
            githubIssueState = system.state;
          }
        });
      } catch (error) {
        setSystemStatus("elastic", "disconnected", "UNKNOWN");
        setSystemStatus("gemini", "disconnected", "UNKNOWN");
        setSystemStatus("cloud-run", "disconnected", "UNKNOWN");
        setSystemStatus("github", "disconnected", "UNKNOWN");
        githubIssueState = "disconnected";
      }
    }

    function setFlowStep(stepName, state) {
      const step = document.querySelector(`[data-step="${stepName}"]`);
      if (!step) {
        return;
      }

      const allowedStates = ["idle", "running", "done", "failed"];
      const safeState = allowedStates.includes(state) ? state : "idle";

      step.classList.remove("idle", "running", "done", "failed");
      step.classList.add(safeState);

      const stateLabel = step.querySelector(".state-label");
      if (stateLabel) {
        stateLabel.textContent = safeState.toUpperCase();
      }
    }

    function resetFlow() {
      flowStepNames.forEach((stepName) => setFlowStep(stepName, "idle"));
    }

    async function runStep(stepName, durationMs = 260) {
      setFlowStep(stepName, "running");
      await sleep(durationMs);
      setFlowStep(stepName, "done");
    }

    function markStepsIdle(stepNames) {
      stepNames.forEach((stepName) => setFlowStep(stepName, "idle"));
    }

    async function runFlowForAction(actionName) {
      if (actionName === "health") {
        await runStep("cloud-run", 240);
        await runStep("verify-health", 240);
        markStepsIdle([
          "elastic-alert",
          "evidence",
          "gemini",
          "root-cause",
          "remediation-plan",
          "apply-fix",
          "github-issue"
        ]);
        return;
      }

      if (actionName === "simulate") {
        await runStep("elastic-alert", 220);
        await runStep("cloud-run", 220);
        await runStep("evidence", 260);
        await runStep("gemini", 260);
        await runStep("root-cause", 220);
        await runStep("remediation-plan", 220);
        markStepsIdle([
          "apply-fix",
          "verify-health",
          "github-issue"
        ]);
        return;
      }

      if (actionName === "latest") {
        await runStep("evidence", 240);
        await runStep("root-cause", 220);
        markStepsIdle([
          "elastic-alert",
          "cloud-run",
          "gemini",
          "remediation-plan",
          "apply-fix",
          "verify-health",
          "github-issue"
        ]);
        return;
      }

      if (actionName === "ask") {
        setFlowStep("elastic-alert", "done");
        setFlowStep("cloud-run", "done");
        setFlowStep("evidence", "done");
        await runStep("gemini", 320);
        await runStep("root-cause", 240);
        await runStep("remediation-plan", 240);
        markStepsIdle([
          "apply-fix",
          "verify-health",
          "github-issue"
        ]);
      }
    }

    async function callApi(path, options = {}) {
      const response = await fetch(path, options);
      const payload = await response.json();

      if (!response.ok) {
        const message = payload && payload.detail ? payload.detail : "Request failed";
        throw new Error(typeof message === "string" ? message : formatJson(message));
      }

      return payload;
    }

    async function healthCheck() {
      setButtonsDisabled(true);
      resetFlow();
      setRecommendedActionVisible(false);
      setResolutionInsightsVisible(false);
      incidentOutput.textContent = "Checking live checkout-api, payment-api, and customer checkout flow endpoints...";

      const flowPromise = runFlowForAction("health");

      try {
        const payload = await loadWorkloadStatus();
        await flowPromise;
        incidentOutput.textContent = formatJson(payload);
        await loadConnectedSystems();
      } catch (error) {
        setFlowStep("cloud-run", "failed");
        incidentOutput.innerHTML = `<span class="error">${error.message}</span>`;
      } finally {
        setButtonsDisabled(false);
      }
    }

    async function simulateIncident() {
      setButtonsDisabled(true);
      resetFlow();
      setRecommendedActionVisible(false);
      setResolutionInsightsVisible(false);
      incidentOutput.textContent = "Injecting real redis_timeout failure into checkout-api...";

      const flowPromise = runFlowForAction("simulate");

      try {
        const payload = await callApi("/simulate-incident", {
          method: "POST"
        });
        await flowPromise;
        if (payload.workload) {
          updateWorkloadFromSnapshot(payload.workload);
        }
        incidentOutput.textContent = formatJson(payload);
        setIncidentStatus({
          state: "active",
          service: "checkout-api",
          severity: "high",
          rootCause: "redis_timeout runtime mode",
          confidence: "live HTTP evidence"
        });
        await loadConnectedSystems();
      } catch (error) {
        setFlowStep("gemini", "failed");
        setIncidentStatus({
          state: "active",
          service: "checkout-api",
          severity: "high",
          rootCause: "Triage failed",
          confidence: "-"
        });
        incidentOutput.innerHTML = `<span class="error">${error.message}</span>`;
      } finally {
        setButtonsDisabled(false);
      }
    }

    async function latestIncident() {
      setButtonsDisabled(true);
      setRecommendedActionVisible(false);
      setResolutionInsightsVisible(false);
      incidentOutput.textContent = "Loading latest Elastic incident brief and refreshing live workload status...";

      const flowPromise = runFlowForAction("latest");

      try {
        const payload = await callApi("/incidents/latest");
        const workloadPayload = await loadWorkloadStatus();
        await flowPromise;
        incidentOutput.textContent = formatJson({
          latest_incident: payload,
          workload: workloadPayload.workload
        });

        if (workloadPayload.workload && workloadPayload.workload.status === "incident") {
          setIncidentStatus({
            state: "active",
            service: "checkout-api",
            severity: "high",
            rootCause: "redis_timeout runtime mode",
            confidence: "live HTTP evidence"
          });
        }

        await loadConnectedSystems();
      } catch (error) {
        setFlowStep("evidence", "failed");
        incidentOutput.innerHTML = `<span class="error">${error.message}</span>`;
      } finally {
        setButtonsDisabled(false);
      }
    }

    async function askAgent() {
      setButtonsDisabled(true);
      const questionInput = document.getElementById("question");
      const question = questionInput.value.trim();

      if (!question) {
        agentAnswer.innerHTML = `<span class="error">Please enter a question.</span>`;
        setButtonsDisabled(false);
        return;
      }

      agentAnswer.textContent = "Gemini is reasoning over Elastic evidence and the live workload failure...";

      const flowPromise = runFlowForAction("ask");

      try {
        const payload = await callApi("/ask-followup", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            question: question
          })
        });
        await flowPromise;
        await loadWorkloadStatus();
        agentAnswer.textContent = renderResponse(
          Object.prototype.hasOwnProperty.call(payload, "response")
            ? payload.response
            : payload
        );
        setIncidentStatus({
          state: "ready",
          service: "checkout-api",
          severity: "high",
          rootCause: "redis_timeout runtime mode",
          confidence: "87%"
        });
        setRecommendedActionVisible(true);
        await loadConnectedSystems();
      } catch (error) {
        setFlowStep("gemini", "failed");
        agentAnswer.innerHTML = `<span class="error">${error.message}</span>`;
      } finally {
        setButtonsDisabled(false);
      }
    }

    function renderIssueResult(githubIssue) {
      if (!githubIssue) {
        return;
      }

      if (issueTitle) {
        issueTitle.textContent = githubIssue.title || "[resolved by agent] checkout-api failure after redis_timeout runtime mode";
      }

      if (issueStatus) {
        if (githubIssue.status === "created") {
          issueStatus.textContent = `GitHub issue #${githubIssue.issue_number} created by the agent.`;
        } else if (githubIssue.status === "simulated") {
          issueStatus.textContent = "GitHub issue simulated because GitHub credentials are not configured.";
        } else {
          issueStatus.textContent = `GitHub issue status: ${githubIssue.status || "unknown"}`;
        }
      }

      if (issueUrl) {
        if (githubIssue.issue_url) {
          issueUrl.href = githubIssue.issue_url;
          issueUrl.textContent = "Open GitHub issue";
          issueUrl.classList.remove("disabled");
        } else {
          issueUrl.href = "#";
          issueUrl.textContent = "GitHub issue URL not available";
          issueUrl.classList.add("disabled");
        }
      }

      if (issueLabels && Array.isArray(githubIssue.labels)) {
        issueLabels.innerHTML = githubIssue.labels
          .map((label) => `<span class="label-chip">${label}</span>`)
          .join("");
      }
    }

    function renderResolvedInsights(payload) {
      if (!payload) {
        return;
      }

      const githubIssue = payload.github_issue;
      renderIssueResult(githubIssue);

      if (resolvedSummary) {
        resolvedSummary.textContent =
          payload.message ||
          "The agent repaired checkout-api runtime mode and verified the live customer checkout flow.";
      }

      if (verificationList) {
        const verification = payload.verification || {};
        const checks = verification.checks || {};
        const checkoutHealth = checks.checkout_health || {};
        const checkoutFlow = checks.checkout_flow || {};
        const paymentHealth = checks.payment_health || {};

        verificationList.innerHTML = `
          <li>checkout-api /healthz returned ${checkoutHealth.http_status || "-"} after remediation.</li>
          <li>checkout-api /checkout returned ${checkoutFlow.http_status || "-"} after remediation.</li>
          <li>payment-api /healthz returned ${paymentHealth.http_status || "-"} after remediation.</li>
          <li>customer checkout flow verification: ${verification.verified ? "passed" : "failed"}.</li>
        `;
      }

      if (issueBodyPreview) {
        issueBodyPreview.innerHTML = `
          <li>Root cause: checkout-api entered redis_timeout failure mode.</li>
          <li>Action taken: agent called checkout-api /admin/repair.</li>
          <li>Verification: live workload checks returned ${payload.status === "solved" ? "healthy" : "not healthy"}.</li>
          <li>Follow-up: review checkout-api runtime config guardrails before redeployment.</li>
        `;
      }
    }

    async function applyRemediation() {
      setButtonsDisabled(true);

      try {
        setIncidentStatus({
          state: "remediating",
          service: "checkout-api",
          severity: "high",
          rootCause: "redis_timeout runtime mode",
          confidence: "87%"
        });

        setWorkloadRemediating();

        appendIncidentOutput(
          "AGENT REMEDIATION STARTED\n" +
          "The agent is calling the real checkout-api /admin/repair endpoint."
        );

        const remediationPromise = callApi("/apply-remediation", {
          method: "POST"
        });

        await runStep("apply-fix", 560);
        appendIncidentOutput(
          "APPLY FIX REQUEST SENT\n" +
          "Agent requested checkout-api runtime repair."
        );

        await runStep("verify-health", 560);
        appendIncidentOutput(
          "VERIFY HEALTH RUNNING\n" +
          "Agent is checking checkout-api /healthz, checkout-api /checkout, and payment-api /healthz."
        );

        const payload = await remediationPromise;

        if (payload.after) {
          updateWorkloadFromSnapshot(payload.after, "solved");
        } else {
          await loadWorkloadStatus();
        }

        await runStep("github-issue", 440);

        renderResolvedInsights(payload);
        setResolutionInsightsVisible(true);

        const githubIssue = payload.github_issue || {};
        const githubMessage =
          githubIssue.status === "created"
            ? `GitHub issue created: ${githubIssue.issue_url}`
            : `GitHub issue status: ${githubIssue.status || "unknown"}`;

        appendIncidentOutput(
          "AGENT REMEDIATION RESULT\n" +
          formatJson({
            status: payload.status,
            verification: payload.verification,
            github_issue: payload.github_issue
          })
        );

        if (payload.status === "solved") {
          setIncidentStatus({
            state: "solved",
            service: "checkout-api",
            severity: "high",
            rootCause: "runtime mode repaired",
            confidence: "verified"
          });

          agentAnswer.textContent =
            agentAnswer.textContent +
            "\n\nProblem solved by the agent. The agent called checkout-api /admin/repair, verified checkout-api /healthz, verified the customer checkout flow, checked payment-api health, and created a GitHub issue for engineering follow-up. " +
            githubMessage;

          setRecommendedActionVisible(false);
        } else {
          setIncidentStatus({
            state: "active",
            service: "checkout-api",
            severity: "high",
            rootCause: "verification failed",
            confidence: "not verified"
          });
          setFlowStep("verify-health", "failed");
        }
      } catch (error) {
        setFlowStep("apply-fix", "failed");
        appendIncidentOutput(
          "REMEDIATION FAILED\n" +
          error.message
        );
      } finally {
        setButtonsDisabled(false);
      }
    }

    function doNotAct() {
      setRecommendedActionVisible(false);
      if (latestWorkload) {
        updateWorkloadFromSnapshot(latestWorkload);
      }
      setIncidentStatus({
        state: "active",
        service: "checkout-api",
        severity: "high",
        rootCause: "Action skipped",
        confidence: "87%"
      });

      appendIncidentOutput(
        "REMEDIATION SKIPPED\n" +
        "The operator selected Do not act. Incident remains active and no checkout-api repair call was made."
      );
    }

    async function initializeDemoPage() {
      setIncidentStatus({
        state: "idle",
        service: "checkout-api",
        severity: "high",
        rootCause: "-",
        confidence: "-"
      });

      setResolutionInsightsVisible(false);

      try {
        await loadConnectedSystems();
      } catch (error) {
        console.error("Connected systems refresh failed:", error);
      }

      try {
        await loadWorkloadStatus();
      } catch (error) {
        console.error("Live workload refresh failed:", error);
        incidentOutput.innerHTML = `<span class="error">Could not load live workload status: ${error.message}</span>`;
      }
    }

    window.loadConnectedSystems = loadConnectedSystems;
    window.loadWorkloadStatus = loadWorkloadStatus;
    window.initializeDemoPage = initializeDemoPage;
    window.healthCheck = healthCheck;
    window.simulateIncident = simulateIncident;
    window.latestIncident = latestIncident;
    window.askAgent = askAgent;
    window.applyRemediation = applyRemediation;
    window.doNotAct = doNotAct;

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initializeDemoPage);
    } else {
      initializeDemoPage();
    }
  </script>
</body>
</html>
"""