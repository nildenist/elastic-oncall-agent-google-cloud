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

    .flow {
      color: #e2e8f0;
      font-size: 14px;
      line-height: 1.55;
    }

    .flow span {
      display: inline-block;
      margin: 3px 5px 3px 0;
      padding: 5px 9px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.07);
      border: 1px solid rgba(255, 255, 255, 0.11);
      white-space: nowrap;
    }

    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
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
      white-space: nowrap;
    }

    button:hover {
      transform: translateY(-1px);
      filter: brightness(1.15);
      box-shadow: 0 14px 32px rgba(255, 255, 255, 0.08);
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
      gap: 10px;
      align-items: stretch;
    }

    .side-panel {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }

    .ask-row {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    input {
      flex: 1;
      min-height: 36px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.14);
      background: rgba(2, 6, 23, 0.58);
      color: #e5e7eb;
      padding: 8px 14px;
      font-size: 13px;
      outline: none;
      min-width: 0;
    }

    input:focus {
      border-color: rgba(147, 197, 253, 0.7);
      box-shadow: 0 0 0 3px rgba(66, 133, 244, 0.18);
    }

    pre {
      background: rgba(2, 6, 23, 0.88);
      color: #d1d5db;
      padding: 14px;
      border-radius: 14px;
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid rgba(148, 163, 184, 0.16);
      font-size: 12px;
      line-height: 1.4;
      margin: 0;
    }

    .incident-output {
      min-height: 290px;
      max-height: 430px;
    }

    .agent-output {
      min-height: 172px;
      max-height: 250px;
    }

    .footer {
      margin-top: 10px;
      color: #94a3b8;
      font-size: 12px;
      text-align: center;
    }

    @media (max-width: 900px) {
      .page {
        width: min(100% - 22px, 1120px);
        padding-top: 14px;
      }

      .hero {
        padding: 16px 18px;
        border-radius: 20px;
      }

      h1 {
        font-size: clamp(25px, 8vw, 36px);
      }

      .subtitle {
        font-size: 14px;
      }

      .workspace {
        grid-template-columns: 1fr;
      }

      .controls {
        gap: 8px;
      }

      button {
        flex: 1 1 calc(50% - 8px);
        min-width: 140px;
      }

      .ask-row {
        flex-direction: column;
        align-items: stretch;
      }

      .ask-row button {
        width: 100%;
      }

      .incident-output {
        min-height: 220px;
      }

      .agent-output {
        min-height: 160px;
      }
    }

    @media (max-width: 520px) {
      .page {
        width: min(100% - 16px, 1120px);
        padding-top: 10px;
      }

      .card {
        padding: 14px;
      }

      .hero {
        padding: 15px;
      }

      .eyebrow {
        font-size: 11px;
      }

      h1 {
        font-size: 28px;
      }

      button {
        flex: 1 1 100%;
      }
    }

    @media (max-height: 760px) and (min-width: 901px) {
      .page {
        padding-top: 10px;
      }

      .hero {
        padding: 14px 22px;
      }

      h1 {
        font-size: clamp(26px, 3vw, 36px);
      }

      .subtitle {
        font-size: 14px;
      }

      .grid {
        gap: 9px;
        margin-top: 10px;
      }

      .card {
        padding: 13px 18px;
      }

      .card h2 {
        font-size: 17px;
        margin-bottom: 9px;
      }

      .incident-output {
        min-height: 250px;
        max-height: 350px;
      }

      .agent-output {
        min-height: 150px;
        max-height: 220px;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-content">
        <div class="eyebrow">Google Cloud Agentic AI x Elastic</div>
        <h1>
          Elastic On-Call Agent:<br />
          <span class="gradient-text">Agentic Ops with Google Cloud</span>
        </h1>
        <p class="subtitle">
          Alert-triggered triage using Cloud Run, Elastic evidence, and Slack notifications
          to move from signal to root cause to safe next action.
        </p>
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <h2>Agentic flow</h2>
        <div class="flow">
          <span>Elastic alert</span>
          <span>Cloud Run endpoint</span>
          <span>Evidence collection</span>
          <span>Probable root cause</span>
          <span>Safe next action</span>
          <span>Slack notification</span>
          <span>Ask follow-up</span>
        </div>
      </div>

      <div class="card">
        <h2>Demo controls</h2>
        <div class="controls">
          <button class="btn-health" onclick="health()">Health check</button>
          <button class="btn-seed" onclick="seed()">Seed demo data</button>
          <button class="btn-simulate" onclick="simulate()">Simulate incident</button>
          <button class="btn-latest" onclick="latest()">Latest incident</button>
        </div>
      </div>

      <div class="workspace">
        <div class="card">
          <h2>Incident output</h2>
          <pre id="incident-output" class="incident-output">Click Seed demo data, then Simulate incident.</pre>
        </div>

        <div class="side-panel">
          <div class="card">
            <h2>Ask Agent</h2>
            <div class="ask-row">
              <input
                id="question"
                value="Why do you think this is deployment-related?"
                placeholder="Ask a follow-up question"
              />
              <button class="btn-ask" onclick="askAgent()">Ask agent</button>
            </div>
          </div>

          <div class="card">
            <h2>Agent answer</h2>
            <pre id="agent-output" class="agent-output">Ask a question after simulating an incident.</pre>
          </div>
        </div>
      </div>
    </section>

    <div class="footer">
      Built for the Rapid Agent Hackathon Elastic track. Human approval is required before destructive actions.
    </div>
  </main>

  <script>
    async function callApi(path, method = "GET", body = null) {
      const output = document.getElementById("incident-output");
      output.textContent = "Running " + method + " " + path + " ...";

      try {
        const options = { method };

        if (body !== null) {
          options.headers = { "Content-Type": "application/json" };
          options.body = JSON.stringify(body);
        }

        const response = await fetch(path, options);
        const data = await response.json();
        output.textContent = JSON.stringify(data, null, 2);
      } catch (error) {
        output.textContent = "Error: " + error;
      }
    }

    async function askAgent() {
      const output = document.getElementById("agent-output");
      const question = document.getElementById("question").value;

      output.textContent = "Asking agent...";

      try {
        const response = await fetch("/ask-followup", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ question })
        });

        const data = await response.json();
        const agentResponse = data.response || {};
        const evidence = agentResponse.evidence_used || [];

        output.textContent =
          "Agent answer\\n" +
          "============\\n\\n" +
          (agentResponse.answer || "No answer returned.") +
          "\\n\\n" +
          "Evidence used\\n" +
          "-------------\\n" +
          evidence.map((item) => "- " + item).join("\\n");
      } catch (error) {
        output.textContent = "Error: " + error;
      }
    }

    function health() {
      callApi("/health");
    }

    function seed() {
      callApi("/seed-demo-data", "POST");
    }

    function simulate() {
      callApi("/simulate-incident", "POST");
    }

    function latest() {
      callApi("/incidents/latest");
    }
  </script>
</body>
</html>
"""