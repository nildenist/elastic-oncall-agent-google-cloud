import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.demo_data import get_demo_alert_payload
from app.elastic_client import (
    get_elastic_client,
    get_latest_incident_brief,
    save_incident_brief,
    seed_demo_data,
)
from app.notifier import format_incident_brief_for_slack, send_slack_notification
from app.rate_limiter import allow_request
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
    return {"status": "ok"}


@app.get("/connection-status")
def connection_status() -> Dict[str, Any]:
    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()

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
                "key": "slack",
                "name": "Slack Webhook",
                "state": "connected" if slack_webhook_url else "not-configured",
                "label": "CONNECTED" if slack_webhook_url else "NOT CONFIGURED",
            },
        ],
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
    if not allow_request("simulate-incident", limit=10, window_seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for demo incident simulation. Please wait and try again.",
        )

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
    return """
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

    .btn-seed {
      color: #dbeafe;
      background: linear-gradient(135deg, rgba(14, 165, 233, 0.36), rgba(37, 99, 235, 0.20));
      box-shadow: 0 10px 26px rgba(14, 165, 233, 0.14);
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
      .controls-layout {
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
          Alert-triggered triage using Cloud Run, Elastic evidence, and Slack notifications to move from signal to root cause to safe next action.
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
          <span class="system-chip checking" data-system="slack">
            <span class="system-dot"></span>
            Slack Webhook
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
          <span class="flow-step idle" data-step="slack">
            <span class="state-dot"></span>
            Slack notification
            <span class="state-label">IDLE</span>
          </span>
        </div>
      </section>

      <section class="card">
        <h2>Demo controls</h2>

        <div class="controls-layout">
          <div class="controls">
            <button class="btn-health" id="btnHealth" onclick="healthCheck()">Health check</button>
            <button class="btn-seed" id="btnSeed" onclick="seedDemoData()">Seed demo data</button>
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

      <div class="workspace">
        <section class="card">
          <h2>Incident output</h2>
          <pre id="incidentOutput">Click Seed demo data, then Simulate incident.</pre>
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
        </div>
      </div>
    </div>

    <div class="footer">
      Built for the Rapid Agent Hackathon Elastic track. Human approval is required before destructive actions.
    </div>
  </div>

  <script>
    const incidentOutput = document.getElementById("incidentOutput");
    const agentAnswer = document.getElementById("agentAnswer");

    const flowStepNames = [
      "elastic-alert",
      "cloud-run",
      "evidence",
      "gemini",
      "root-cause",
      "remediation-plan",
      "apply-fix",
      "verify-health",
      "slack"
    ];

    function sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    function formatJson(value) {
      return JSON.stringify(value, null, 2);
    }

    function setButtonsDisabled(disabled) {
      const buttons = [
        "btnHealth",
        "btnSeed",
        "btnSimulate",
        "btnLatest",
        "btnAsk"
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
        });
      } catch (error) {
        setSystemStatus("elastic", "disconnected", "UNKNOWN");
        setSystemStatus("gemini", "disconnected", "UNKNOWN");
        setSystemStatus("cloud-run", "disconnected", "UNKNOWN");
        setSystemStatus("slack", "disconnected", "UNKNOWN");
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
        markStepsIdle([
          "elastic-alert",
          "evidence",
          "gemini",
          "root-cause",
          "remediation-plan",
          "apply-fix",
          "verify-health",
          "slack"
        ]);
        return;
      }

      if (actionName === "seed") {
        await runStep("evidence", 240);
        await runStep("elastic-alert", 220);
        markStepsIdle([
          "cloud-run",
          "gemini",
          "root-cause",
          "remediation-plan",
          "apply-fix",
          "verify-health",
          "slack"
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
          "slack"
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
          "slack"
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
          "slack"
        ]);
      }
    }

    async function callApi(path, options = {}) {
      const response = await fetch(path, options);
      const payload = await response.json();

      if (!response.ok) {
        const message = payload && payload.detail ? payload.detail : "Request failed";
        throw new Error(message);
      }

      return payload;
    }

    async function healthCheck() {
      setButtonsDisabled(true);
      resetFlow();
      incidentOutput.textContent = "Running Cloud Run endpoint health check...";

      const flowPromise = runFlowForAction("health");

      try {
        const payload = await callApi("/health");
        await flowPromise;
        incidentOutput.textContent = formatJson(payload);
        setIncidentStatus({
          state: "idle",
          service: "checkout-api",
          severity: "high",
          rootCause: "-",
          confidence: "-"
        });
        await loadConnectedSystems();
      } catch (error) {
        setFlowStep("cloud-run", "failed");
        incidentOutput.innerHTML = `<span class="error">${error.message}</span>`;
      } finally {
        setButtonsDisabled(false);
      }
    }

    async function seedDemoData() {
      setButtonsDisabled(true);
      resetFlow();
      incidentOutput.textContent = "Seeding Elastic demo data...";

      const flowPromise = runFlowForAction("seed");

      try {
        const payload = await callApi("/seed-demo-data", {
          method: "POST"
        });
        await flowPromise;
        incidentOutput.textContent = formatJson(payload);
        setIncidentStatus({
          state: "idle",
          service: "checkout-api",
          severity: "high",
          rootCause: "-",
          confidence: "-"
        });
        await loadConnectedSystems();
      } catch (error) {
        setFlowStep("evidence", "failed");
        incidentOutput.innerHTML = `<span class="error">${error.message}</span>`;
      } finally {
        setButtonsDisabled(false);
      }
    }

    async function simulateIncident() {
      setButtonsDisabled(true);
      resetFlow();
      incidentOutput.textContent = "Simulating alert-triggered incident triage...";

      const flowPromise = runFlowForAction("simulate");

      try {
        const payload = await callApi("/simulate-incident", {
          method: "POST"
        });
        await flowPromise;
        incidentOutput.textContent = formatJson(payload);
        setIncidentStatus({
          state: "active",
          service: "checkout-api",
          severity: "high",
          rootCause: "Investigating deployment",
          confidence: "pending"
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
      incidentOutput.textContent = "Loading latest incident brief...";

      const flowPromise = runFlowForAction("latest");

      try {
        const payload = await callApi("/incidents/latest");
        await flowPromise;
        incidentOutput.textContent = formatJson(payload);

        if (payload.status === "found" && payload.incident) {
          setIncidentStatus({
            state: "active",
            service: "checkout-api",
            severity: "high",
            rootCause: "Latest incident loaded",
            confidence: "pending"
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

      agentAnswer.textContent = "Gemini is reasoning over the latest Elastic incident evidence...";

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
        agentAnswer.textContent = payload.response || formatJson(payload);
        setIncidentStatus({
          state: "ready",
          service: "checkout-api",
          severity: "high",
          rootCause: "Bad Cloud Run revision",
          confidence: "87%"
        });
        await loadConnectedSystems();
      } catch (error) {
        setFlowStep("gemini", "failed");
        agentAnswer.innerHTML = `<span class="error">${error.message}</span>`;
      } finally {
        setButtonsDisabled(false);
      }
    }

    window.addEventListener("load", () => {
      setIncidentStatus({
        state: "idle",
        service: "checkout-api",
        severity: "high",
        rootCause: "-",
        confidence: "-"
      });
      loadConnectedSystems();
    });
  </script>
</body>
</html>
"""