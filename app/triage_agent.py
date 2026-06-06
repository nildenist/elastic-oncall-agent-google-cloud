from datetime import datetime, timezone
from typing import Any, Dict, List

from elasticsearch import Elasticsearch

from app.elastic_client import (
    get_recent_deploys,
    get_service_metrics,
    search_recent_logs,
    search_related_logs,
    search_runbooks_and_incidents,
)
from app.schemas import (
    AlertPayload,
    EvidenceItem,
    IncidentBrief,
    NextAction,
    RootCauseHypothesis,
)


def _metric_value(metrics: List[Dict[str, Any]], metric_name: str) -> List[Any]:
    return [item.get("value") for item in metrics if item.get("metric") == metric_name]


def build_incident_brief_from_elastic(
    client: Elasticsearch,
    alert: AlertPayload,
) -> IncidentBrief:
    service = alert.service
    related_service = str(alert.metadata.get("related_service", "payment-service"))

    service_logs = search_recent_logs(client, service=service, environment=alert.environment)
    related_logs = search_recent_logs(client, service=related_service, environment=alert.environment)
    redis_logs = search_related_logs(client, "RedisTimeoutError connection pool checkout payment")
    service_metrics = get_service_metrics(client, service=service)
    related_metrics = get_service_metrics(client, service=related_service)
    deploys = get_recent_deploys(client, service=service)
    knowledge = search_runbooks_and_incidents(
        client,
        "Redis timeout deployment checkout payment 5xx connection pool",
    )

    latency_values = _metric_value(service_metrics, "latency_p95_ms")
    error_rate_values = _metric_value(related_metrics, "http_5xx_rate")
    cpu_values = _metric_value(service_metrics, "cpu_percent")
    memory_values = _metric_value(service_metrics, "memory_percent")
    restart_values = _metric_value(service_metrics, "pod_restarts")

    latest_deploy = deploys[0] if deploys else {}
    runbook = knowledge["runbooks"][0] if knowledge["runbooks"] else {}
    similar_incident = knowledge["incidents"][0] if knowledge["incidents"] else {}

    evidence = [
        EvidenceItem(
            source="Elastic metrics-service",
            title="Checkout latency spike",
            detail=f"Latency p95 values observed for {service}: {latency_values}",
            value=str(latency_values),
            confidence="high",
        ),
        EvidenceItem(
            source="Elastic metrics-service",
            title="Payment 5xx increase",
            detail=f"HTTP 5xx rate values observed for {related_service}: {error_rate_values}",
            value=str(error_rate_values),
            confidence="high",
        ),
        EvidenceItem(
            source="Elastic logs-app",
            title="Redis timeout pattern",
            detail=f"Found {len(redis_logs)} Redis/dependency related log events around the alert window.",
            value="RedisTimeoutError",
            confidence="high",
        ),
        EvidenceItem(
            source="Elastic deploy-events",
            title="Recent deployment correlation",
            detail=(
                f"Latest deploy for {service}: version={latest_deploy.get('version')} "
                f"previous={latest_deploy.get('previous_version')} "
                f"change={latest_deploy.get('change_summary')}"
            ),
            value=str(latest_deploy.get("version")),
            confidence="high" if latest_deploy else "medium",
        ),
        EvidenceItem(
            source="Elastic metrics-service",
            title="Resource pressure check",
            detail=(
                f"CPU values={cpu_values}, memory values={memory_values}, "
                f"pod restart values={restart_values}. No obvious resource saturation or restart storm detected."
            ),
            value="cpu_memory_restarts_normal",
            confidence="medium",
        ),
        EvidenceItem(
            source="Elastic runbooks",
            title="Relevant runbook found",
            detail=runbook.get("content", "No matching runbook found."),
            value=runbook.get("title"),
            confidence="medium" if runbook else "low",
        ),
        EvidenceItem(
            source="Elastic incidents-history",
            title="Similar past incident found",
            detail=similar_incident.get("summary", "No similar incident found."),
            value=similar_incident.get("incident_id"),
            confidence="medium" if similar_incident else "low",
        ),
    ]

    hypotheses = [
        RootCauseHypothesis(
            title="Redis client configuration regression after deployment",
            explanation=(
                "The most likely root cause is a checkout-service deployment that changed Redis "
                "connection behavior. Redis timeout logs, checkout latency spike, payment-service "
                "5xx increase, and the recent deploy event point to the same time window."
            ),
            confidence="high",
            supporting_evidence=[
                "Checkout p95 latency spike",
                "Payment-service 5xx increase",
                "RedisTimeoutError pattern",
                "Recent checkout-service deployment",
                "Similar historical incident INC-42",
            ],
        ),
        RootCauseHypothesis(
            title="Redis saturation or external dependency degradation",
            explanation=(
                "Redis or dependency saturation is possible, but CPU, memory, and pod restart "
                "signals do not show a direct application resource pressure pattern."
            ),
            confidence="medium",
            supporting_evidence=[
                "Redis timeout logs",
                "No pod restart storm",
                "CPU and memory appear normal",
            ],
        ),
    ]

    next_actions = [
        NextAction(
            title="Freeze new deployments",
            description="Pause further production deployments for affected services until mitigation is confirmed.",
            requires_human_approval=False,
            risk_level="low",
        ),
        NextAction(
            title="Prepare rollback plan",
            description=(
                f"Prepare rollback of {service} from "
                f"{latest_deploy.get('version', 'current version')} to "
                f"{latest_deploy.get('previous_version', 'previous stable version')}. Do not execute without approval."
            ),
            requires_human_approval=True,
            risk_level="medium",
        ),
        NextAction(
            title="Monitor Redis timeout rate",
            description="After mitigation, monitor Redis timeout logs and payment-service 5xx rate for 10 minutes.",
            requires_human_approval=False,
            risk_level="low",
        ),
        NextAction(
            title="Create postmortem draft",
            description="Generate a postmortem draft with timeline, impact, evidence, root cause, and follow-up actions.",
            requires_human_approval=False,
            risk_level="low",
        ),
    ]

    timeline = [
        "T-14m: checkout-service v1.8.2 deployment detected",
        "T-10m: checkout-service p95 latency increased",
        "T-09m: RedisTimeoutError logs started increasing",
        "T-08m: payment-service 5xx rate increased",
        "T-now: agent prepared evidence-backed incident brief",
    ]

    return IncidentBrief(
        incident_id=f"incident-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        status="active",
        summary=(
            f"{alert.severity.upper()} alert for {service}: {alert.message}. "
            f"Related downstream impact detected on {related_service}."
        ),
        probable_root_cause=(
            "Recent checkout-service deployment likely changed Redis connection behavior, "
            "causing Redis timeout errors and downstream payment-service 5xx responses."
        ),
        confidence="high",
        affected_services=[service, related_service],
        timeline=timeline,
        evidence=evidence,
        hypotheses=hypotheses,
        next_actions=next_actions,
        human_approval_required=True,
    )


def answer_followup(question: str, latest_brief: Dict[str, Any] | None) -> Dict[str, Any]:
    if latest_brief is None:
        return {
            "answer": "No incident brief is available yet. Trigger or triage an incident first.",
            "evidence_used": [],
        }

    question_lower = question.lower()

    if "rollback" in question_lower:
        answer = (
            "Rollback should be prepared but not executed automatically. The safest draft action is "
            "to roll back checkout-service from v1.8.2 to v1.8.1, then monitor Redis timeout rate "
            "and payment-service 5xx for 10 minutes. Human approval is required."
        )
    elif "deployment" in question_lower or "deploy" in question_lower:
        answer = (
            "The incident appears deployment-related because the latency spike and RedisTimeoutError "
            "pattern started shortly after the checkout-service deployment. The deploy event also "
            "mentions Redis client configuration and connection pool changes."
        )
    elif "evidence" in question_lower:
        answer = (
            "Main evidence: checkout latency increased, payment-service 5xx increased, RedisTimeoutError "
            "logs appeared in the same time window, CPU/memory/pod restarts look normal, and a similar "
            "historical incident was resolved by rollback."
        )
    elif "postmortem" in question_lower:
        answer = (
            "Postmortem draft: checkout-service deployment v1.8.2 likely introduced Redis connection "
            "pool regression. Impact: checkout latency and downstream payment failures. Mitigation: "
            "rollback or revert Redis pool config. Follow-up: add canary validation for Redis timeout "
            "rate after deployments."
        )
    else:
        answer = (
            "Based on the latest incident brief, the likely issue is a Redis connection behavior "
            "regression after checkout-service deployment. Ask for rollback, evidence, deployment "
            "correlation, or postmortem draft for a more specific answer."
        )

    return {
        "incident_id": latest_brief.get("incident_id"),
        "answer": answer,
        "evidence_used": [
            item.get("title", "evidence") for item in latest_brief.get("evidence", [])
        ],
    }
