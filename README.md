# Elastic On-Call Agent: Agentic Ops with Google Cloud

Elastic On-Call Agent is an alert-triggered incident response agent built for the Rapid Agent Hackathon Elastic track.

It uses Google Cloud, Gemini / Agent Builder concepts, Cloud Run, Slack, and Elastic operational evidence to investigate production incidents automatically.

## Problem

On-call engineers should not watch dashboards all day.

When an incident happens, the hardest questions are:

- What changed?
- What broke?
- Which services are affected?
- What evidence proves the probable root cause?
- What is the safest next action?

This project turns Elastic into an agentic operational evidence layer. When an alert is triggered, the agent investigates logs, metrics, deploy events, runbooks, and historical incidents, then sends an evidence-backed incident brief to the notification channel.

## Core flow

```text
Elastic alert
  -> FastAPI / Cloud Run triage endpoint
  -> Gemini / Google Cloud Agent Builder concept
  -> Elastic evidence collection
  -> probable root cause
  -> evidence table
  -> safe next actions
  -> Slack notification
```

## Current demo scenario

The demo simulates a production incident:

1. checkout-service v1.8.2 is deployed.
2. checkout-service p95 latency increases.
3. payment-service 5xx rate increases.
4. Redis timeout logs appear.
5. CPU, memory, and pod restart signals look normal.
6. A related runbook and similar historical incident are found.
7. The agent produces a root cause hypothesis and next action plan.
8. The result is sent to Slack as an active incident notification.

## Tech stack

- Python
- FastAPI
- Streamlit
- Elastic Cloud Serverless
- Elasticsearch Python client
- Slack Incoming Webhook
- Google Cloud Run target deployment
- Gemini / Google Cloud Agent Builder concept

## Local setup

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a `.env` file from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Set the following values in `.env`:

```env
ELASTIC_URL=https://your-elastic-endpoint.es.europe-west1.gcp.elastic.cloud
ELASTIC_API_KEY=your-elastic-api-key
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/your/webhook/url
```

Run the backend:

```powershell
uvicorn app.main:app --reload --port 8080
```

Run the UI:

```powershell
streamlit run ui\streamlit_app.py --server.port 8501
```

## API endpoints

```text
GET  /health
POST /seed-demo-data
POST /simulate-incident
POST /triage-alert
POST /ask-followup
GET  /incidents/latest
```

## Safety

The agent does not execute destructive actions automatically.

Rollback, delete, or production-changing actions require human approval.

## Individual submission note

This project is an individual hackathon submission. It is not submitted on behalf of my employer and does not represent my employer's products, services, customers, confidential information, or official position.

## License

MIT