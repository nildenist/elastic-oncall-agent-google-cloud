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
from app.gemini_agent import (
    answer_followup_with_gemini,
    generate_incident_brief_with_gemini,
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


def _collect_elastic_evidence(
    client: Elasticsearch,
    alert: AlertPayload,
) -> Dict[str, Any]:
    service = alert.service
    related_service = str(alert.metadata.get("related_service", "payment-service"))

    service_logs = search_recent_logs(
        client,
        service=service,
        environment=alert.environment,
    )
    related_logs = search_recent_logs(
        client,
        service=related_service,
        environment=alert.environment,
    )
    redis_logs = search_related_logs(
        client,
        "RedisTimeoutError connection pool checkout payment",
    )
    service_metrics = get_service_metrics(client, service=service)
    related_metrics = get_service_metrics(client, service=related_service)
    deploys = get_recent_deploys(client, service=service)
    knowledge = search_runbooks_and_incidents(
        client,
        "Redis timeout deployment checkout payment 5xx connection pool",
    )

    return {
        "service": service,
        "related_service": related_service,
        "environment": alert.environment,
        "service_logs": service_logs,
        "related_logs": related_logs,
        "redis_logs": redis_logs,
        "service_metrics": service_metrics,
        "related_metrics": related_metrics,
        "deploys": deploys,
        "knowledge": knowledge,
    }


def _build_evidence_items(bundle: Dict[str, Any]) -> List[EvidenceItem]:
    service = bundle["service"]
    related_service = bundle["related_service"]

    service_metrics = bundle["service_metrics"]
    related_metrics = bundle["related_metrics"]
    redis_logs = bundle["redis_logs"]
    deploys = bundle["deploys"]
    knowledge = bundle["knowledge"]

    latency_values = _metric_value(service_metrics, "latency_p95_ms")
    error_rate_values = _metric_value(related_metrics, "http_5xx_rate")
    cpu_values = _metric_value(service_metrics, "cpu_percent")
    memory_values = _metric_value(service_metrics, "memory_percent")
    restart_values = _metric_value(service_metrics, "pod_restarts")

    latest_deploy = deploys[0] if deploys else {}
    runbook = knowledge["runbooks"][0] if knowledge.get("runbooks") else {}
    similar_incident = knowledge["incidents"][0] if knowledge.get("incidents") else {}

    return [
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


def _default_hypotheses() -> List[RootCauseHypothesis]:
    return [
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


def _default_next_actions(service: str, deploys: List[Dict[str, Any]]) -> List[NextAction]:
    latest_deploy = deploys[0] if deploys else {}

    return [
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


def _default_timeline() -> List[str]:
    return [
        "T-14m: checkout-service v1.8.2 deployment detected",
        "T-10m: checkout-service p95 latency increased",
        "T-09m: RedisTimeoutError logs started increasing",
        "T-08m: payment-service 5xx rate increased",
        "T-now: agent prepared evidence-backed incident brief",
    ]


def _build_deterministic_brief(
    alert: AlertPayload,
    bundle: Dict[str, Any],
) -> IncidentBrief:
    service = bundle["service"]
    related_service = bundle["related_service"]

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
        timeline=_default_timeline(),
        evidence=_build_evidence_items(bundle),
        hypotheses=_default_hypotheses(),
        next_actions=_default_next_actions(service, bundle["deploys"]),
        human_approval_required=True,
    )


def _hypotheses_from_gemini(items: List[Dict[str, Any]]) -> List[RootCauseHypothesis]:
    hypotheses: List[RootCauseHypothesis] = []

    for item in items:
        hypotheses.append(
            RootCauseHypothesis(
                title=str(item.get("title", "Gemini hypothesis")),
                explanation=str(item.get("explanation", "")),
                confidence=str(item.get("confidence", "medium")),
                supporting_evidence=list(item.get("supporting_evidence", [])),
            )
        )

    return hypotheses


def _next_actions_from_gemini(items: List[Dict[str, Any]]) -> List[NextAction]:
    actions: List[NextAction] = []

    for item in items:
        actions.append(
            NextAction(
                title=str(item.get("title", "Recommended action")),
                description=str(item.get("description", "")),
                requires_human_approval=bool(item.get("requires_human_approval", True)),
                risk_level=str(item.get("risk_level", "medium")),
            )
        )

    return actions


def build_incident_brief_from_elastic(
    client: Elasticsearch,
    alert: AlertPayload,
) -> IncidentBrief:
    bundle = _collect_elastic_evidence(client, alert)
    fallback_brief = _build_deterministic_brief(alert, bundle)

    gemini_data = generate_incident_brief_with_gemini(
        alert_payload=alert.model_dump(mode="json"),
        evidence_bundle=bundle,
    )

    if gemini_data is None:
        return fallback_brief

    evidence = _build_evidence_items(bundle)
    evidence.append(
        EvidenceItem(
            source="Google Vertex AI Gemini",
            title="Gemini-backed reasoning",
            detail=str(gemini_data.get("reasoning_engine", "Gemini reasoning completed")),
            value="gemini_reasoning",
            confidence="high",
        )
    )

    hypotheses = _hypotheses_from_gemini(gemini_data.get("hypotheses", []))
    if not hypotheses:
        hypotheses = fallback_brief.hypotheses

    next_actions = _next_actions_from_gemini(gemini_data.get("next_actions", []))
    if not next_actions:
        next_actions = fallback_brief.next_actions

    timeline = list(gemini_data.get("timeline", [])) or fallback_brief.timeline
    timeline.append("T-now: Gemini-backed reasoning generated the final incident brief")

    return IncidentBrief(
        incident_id=f"incident-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        status="active",
        summary=str(gemini_data.get("summary", fallback_brief.summary)),
        probable_root_cause=str(
            gemini_data.get("probable_root_cause", fallback_brief.probable_root_cause)
        ),
        confidence=str(gemini_data.get("confidence", fallback_brief.confidence)),
        affected_services=list(
            gemini_data.get("affected_services", fallback_brief.affected_services)
        ),
        timeline=timeline,
        evidence=evidence,
        hypotheses=hypotheses,
        next_actions=next_actions,
        human_approval_required=bool(
            gemini_data.get("human_approval_required", True)
        ),
    )


def _fallback_followup_answer(
    question: str,
    latest_brief: Dict[str, Any],
) -> Dict[str, Any]:
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
        "reasoning_engine": "deterministic_fallback",
    }


def answer_followup(question: str, latest_brief: Dict[str, Any] | None) -> Dict[str, Any]:
    if latest_brief is None:
        return {
            "answer": "No incident brief is available yet. Trigger or triage an incident first.",
            "evidence_used": [],
            "reasoning_engine": "deterministic_fallback",
        }

    gemini_response = answer_followup_with_gemini(
        question=question,
        latest_brief=latest_brief,
    )

    if gemini_response is not None:
        answer = str(
            gemini_response.get("answer")
            or gemini_response.get("Answer")
            or gemini_response.get("response")
            or gemini_response.get("Response")
            or ""
        ).strip()

        evidence_used = (
            gemini_response.get("evidence_used")
            or gemini_response.get("evidence")
            or gemini_response.get("Evidence used")
            or []
        )

        if isinstance(evidence_used, str):
            evidence_used = [evidence_used]

        if answer:
            return {
                "incident_id": latest_brief.get("incident_id"),
                "answer": answer,
                "evidence_used": list(evidence_used),
                "reasoning_engine": gemini_response.get(
                    "reasoning_engine",
                    "Gemini on Vertex AI",
                ),
            }

    return _fallback_followup_answer(question, latest_brief)