from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_minutes_ago(minutes: int) -> str:
    return (utc_now() - timedelta(minutes=minutes)).isoformat()


def get_demo_documents() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "logs-app": [
            {
                "@timestamp": iso_minutes_ago(28),
                "service": "checkout-service",
                "environment": "prod",
                "level": "info",
                "message": "checkout request completed",
                "trace_id": "trace-1001",
                "latency_ms": 230,
            },
            {
                "@timestamp": iso_minutes_ago(11),
                "service": "checkout-service",
                "environment": "prod",
                "level": "error",
                "message": "RedisTimeoutError: connection pool exhausted while reading cart session",
                "trace_id": "trace-2001",
                "latency_ms": 1450,
            },
            {
                "@timestamp": iso_minutes_ago(9),
                "service": "checkout-service",
                "environment": "prod",
                "level": "error",
                "message": "RedisTimeoutError: command GET cart_session timed out after 1200ms",
                "trace_id": "trace-2002",
                "latency_ms": 1510,
            },
            {
                "@timestamp": iso_minutes_ago(8),
                "service": "payment-service",
                "environment": "prod",
                "level": "error",
                "message": "HTTP 502 from checkout dependency while creating payment authorization",
                "trace_id": "trace-3001",
                "latency_ms": 980,
            },
            {
                "@timestamp": iso_minutes_ago(6),
                "service": "payment-service",
                "environment": "prod",
                "level": "error",
                "message": "Payment authorization failed because checkout dependency returned 5xx",
                "trace_id": "trace-3002",
                "latency_ms": 1030,
            },
        ],
        "metrics-service": [
            {
                "@timestamp": iso_minutes_ago(30),
                "service": "checkout-service",
                "metric": "latency_p95_ms",
                "value": 240,
            },
            {
                "@timestamp": iso_minutes_ago(10),
                "service": "checkout-service",
                "metric": "latency_p95_ms",
                "value": 1450,
            },
            {
                "@timestamp": iso_minutes_ago(30),
                "service": "payment-service",
                "metric": "http_5xx_rate",
                "value": 0.2,
            },
            {
                "@timestamp": iso_minutes_ago(8),
                "service": "payment-service",
                "metric": "http_5xx_rate",
                "value": 6.8,
            },
            {
                "@timestamp": iso_minutes_ago(8),
                "service": "checkout-service",
                "metric": "cpu_percent",
                "value": 48,
            },
            {
                "@timestamp": iso_minutes_ago(8),
                "service": "checkout-service",
                "metric": "memory_percent",
                "value": 57,
            },
            {
                "@timestamp": iso_minutes_ago(8),
                "service": "checkout-service",
                "metric": "pod_restarts",
                "value": 0,
            },
        ],
        "alerts": [
            {
                "@timestamp": iso_minutes_ago(7),
                "alert_id": "demo-alert-001",
                "service": "checkout-service",
                "environment": "prod",
                "severity": "critical",
                "signal": "latency_spike",
                "message": "checkout-service p95 latency increased above 1200ms for 5 minutes",
            }
        ],
        "deploy-events": [
            {
                "@timestamp": iso_minutes_ago(14),
                "service": "checkout-service",
                "environment": "prod",
                "version": "v1.8.2",
                "previous_version": "v1.8.1",
                "commit_sha": "abc1234",
                "deployed_by": "ci-cd-pipeline",
                "change_summary": "Updated Redis client configuration and connection pool size",
            }
        ],
        "runbooks": [
            {
                "title": "Redis timeout after deployment",
                "service": "checkout-service",
                "content": (
                    "If Redis timeout errors increase shortly after deployment, check Redis client "
                    "connection pool settings, timeout values, and recent configuration changes. "
                    "Safe mitigation: revert Redis pool config or roll back to the last stable release."
                ),
                "recommended_action": "Rollback service or revert REDIS_POOL_SIZE change, then monitor timeout rate for 10 minutes.",
            }
        ],
        "incidents-history": [
            {
                "incident_id": "INC-42",
                "title": "Checkout Redis connection pool regression",
                "service": "checkout-service",
                "summary": (
                    "A previous checkout-service deployment changed Redis connection behavior. "
                    "Redis timeouts increased, checkout latency spiked, and payment-service returned 5xx."
                ),
                "resolution": "Rolled back checkout-service and restored Redis connection pool configuration.",
            }
        ],
    }


def get_demo_alert_payload() -> Dict[str, Any]:
    return {
        "alert_id": "demo-alert-001",
        "service": "checkout-service",
        "environment": "prod",
        "severity": "critical",
        "signal": "latency_spike",
        "message": "checkout-service p95 latency increased above 1200ms for 5 minutes",
        "time_window_minutes": 30,
        "metadata": {
            "current_latency_p95_ms": 1450,
            "baseline_latency_p95_ms": 240,
            "related_service": "payment-service",
            "related_signal": "http_5xx_rate",
        },
    }
