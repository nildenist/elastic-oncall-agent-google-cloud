# Elastic On-Call Agent: Agentic Ops with Google Cloud

Elastic On-Call Agent is an alert-triggered incident response agent built for the Rapid Agent Hackathon Elastic track.

It uses **Elastic as the operational evidence layer**, **Gemini 2.5 Pro on Vertex AI as the reasoning layer**, **Cloud Run as the execution layer**, and **Slack as the notification layer**.

## Live demo

Public demo URL:

```text
https://elastic-oncall-agent-api-192891427125.europe-west1.run.app/demo
```

GitHub repository:

```text
https://github.com/nildenist/elastic-oncall-agent-google-cloud
```

## Problem

On-call engineers should not watch dashboards all day.

During an incident, the difficult part is not only seeing an alert. The real challenge is connecting scattered operational evidence:

- Which service is affected?
- What changed recently?
- Did a deployment trigger the issue?
- Which logs and metrics support the root cause?
- Is there a relevant runbook?
- Has a similar incident happened before?
- What is the safest next action?

This project automates the first incident triage loop.

## Solution

Elastic On-Call Agent receives or simulates an Elastic alert, collects evidence from Elastic indices, sends the evidence bundle to Gemini 2.5 Pro on Vertex AI, and produces an evidence-backed incident brief.

The agent then sends the incident brief to Slack and allows the user to ask follow-up questions through the hosted demo UI.

## Architecture

```text
Elastic alert / demo trigger
  -> Cloud Run FastAPI endpoint
  -> Elastic evidence collection
  -> Gemini 2.5 Pro on Vertex AI reasoning
  -> Incident brief
  -> Slack notification
  -> Ask Agent follow-up Q&A
```

## Core components

| Component | Role |
|---|---|
| Elastic Cloud Serverless | Stores logs, metrics, alerts, deploy events, runbooks, and past incidents |
| Cloud Run | Hosts the FastAPI API and public demo UI |
| Gemini 2.5 Pro on Vertex AI | Generates root cause reasoning, hypotheses, next actions, and follow-up answers |
| Slack Incoming Webhook | Sends active incident notifications |
| Secret Manager | Stores Elastic and Slack secrets securely |
| FastAPI | Provides API endpoints |
| HTML demo UI | Provides browser-based demo controls |
| Python | Backend implementation |

## Demo scenario

The demo simulates a production incident:

1. `checkout-service` version `v1.8.2` is deployed.
2. The deployment changes Redis client configuration and connection pool size.
3. Shortly after deployment, `RedisTimeoutError` logs appear.
4. `checkout-service` p95 latency increases from `240ms` to `1450ms`.
5. `payment-service` downstream 5xx rate increases from `0.2%` to `6.8%`.
6. CPU, memory, and pod restart signals look normal.
7. A related runbook and a similar historical incident are found.
8. Gemini 2.5 Pro generates the root cause hypothesis and safe next actions.
9. Slack receives the active incident notification.
10. The user can ask follow-up questions through Ask Agent.

## Example output

The agent produces:

- Incident summary
- Probable root cause
- Confidence level
- Affected services
- Timeline
- Evidence table
- Hypotheses
- Next actions
- Human approval requirement

Example probable root cause:

```text
The deployment of checkout-service v1.8.2 introduced a Redis client connection pool configuration issue, causing Redis connection exhaustion, checkout latency increase, and downstream payment-service 5xx errors.
```

Example safe next action:

```text
Prepare rollback of checkout-service to v1.8.1. Do not execute without human approval.
```

## Safety model

The agent does not execute destructive actions automatically.

Rollback, deletion, production change, or mitigation execution requires human approval.

The public demo also includes basic safeguards:

- Cloud Run max instances is limited to 1.
- Simulate incident endpoint has a simple in-memory rate limit.
- Ask Agent endpoint has a simple in-memory rate limit.
- Ask Agent question length is limited.
- Secrets are stored in Secret Manager.
- No service account key file is committed.

## API endpoints

```text
GET  /
GET  /health
GET  /demo
POST /seed-demo-data
POST /simulate-incident
POST /triage-alert
POST /ask-followup
GET  /incidents/latest
```

## Elastic indices

The demo uses the following Elastic indices:

```text
logs-app
metrics-service
alerts
deploy-events
runbooks
incidents-history
agent-results
```

## Local setup

Create and activate a Python virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create a local `.env` file:

```powershell
Copy-Item .env.example .env
```

Set the following values in `.env`:

```env
APP_ENV=local

ELASTIC_URL=https://your-elastic-endpoint.es.europe-west1.gcp.elastic.cloud
ELASTIC_API_KEY=your-elastic-api-key

GOOGLE_CLOUD_PROJECT=elastic-oncall-agent-nilden
GOOGLE_CLOUD_LOCATION=europe-west1
GEMINI_MODEL=gemini-2.5-pro

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/your/webhook/url
```

Run the backend locally:

```powershell
uvicorn app.main:app --reload --port 8080
```

Open the local demo:

```text
http://127.0.0.1:8080/demo
```

## Local demo flow

1. Click `Seed demo data`.
2. Click `Simulate incident`.
3. Check the incident output.
4. Check Slack notification.
5. Ask a follow-up question in `Ask Agent`.

Example follow-up question:

```text
Why do you think this is deployment-related?
```

## Cloud Run deployment

The service can be deployed to Cloud Run from source:

```powershell
gcloud run deploy elastic-oncall-agent-api `
  --source . `
  --region europe-west1 `
  --allow-unauthenticated `
  --max-instances 1 `
  --set-env-vars "APP_ENV=cloud,GOOGLE_CLOUD_PROJECT=elastic-oncall-agent-nilden,GOOGLE_CLOUD_LOCATION=europe-west1,GEMINI_MODEL=gemini-2.5-pro,DEMO_TOKEN=local-demo-token" `
  --set-secrets "ELASTIC_URL=ELASTIC_URL:latest,ELASTIC_API_KEY=ELASTIC_API_KEY:latest,SLACK_WEBHOOK_URL=SLACK_WEBHOOK_URL:latest"
```

Required Google Cloud APIs:

```text
Cloud Run
Cloud Build
Artifact Registry
Secret Manager
Vertex AI
```

Required runtime permissions:

```text
roles/secretmanager.secretAccessor
roles/aiplatform.user
```

## Why this is agentic

This is not just an alert formatter.

The agent performs a multi-step incident investigation:

1. Receives an alert context.
2. Collects operational evidence from Elastic.
3. Builds an evidence bundle.
4. Sends the evidence bundle to Gemini 2.5 Pro.
5. Produces root cause hypotheses.
6. Produces safe next actions.
7. Sends a Slack notification.
8. Supports follow-up reasoning through Ask Agent.
9. Keeps destructive actions behind human approval.

## Individual submission note

This project is an individual hackathon submission.

It is not submitted on behalf of my employer and does not represent my employer's products, services, customers, confidential information, or official position.

No customer data, internal data, or confidential production data is used. The demo uses synthetic data only.

## License

MIT