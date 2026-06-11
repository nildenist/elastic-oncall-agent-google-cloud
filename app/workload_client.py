import os
from typing import Any, Dict, Optional

import httpx


CHECKOUT_SERVICE_URL = os.getenv("CHECKOUT_SERVICE_URL", "http://127.0.0.1:9001").rstrip("/")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://127.0.0.1:9002").rstrip("/")


def _request_json(
    method: str,
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 4.0,
) -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.request(method=method, url=url, json=json_body)

        try:
            body: Any = response.json()
        except ValueError:
            body = response.text

        return {
            "ok": 200 <= response.status_code < 400,
            "http_status": response.status_code,
            "url": url,
            "body": body,
            "error": None,
        }
    except httpx.RequestError as exc:
        return {
            "ok": False,
            "http_status": None,
            "url": url,
            "body": None,
            "error": str(exc),
        }


def _body_detail(response: Dict[str, Any]) -> Any:
    body = response.get("body")

    if isinstance(body, dict) and "detail" in body:
        return body["detail"]

    return body


def _extract_text(response: Dict[str, Any], fallback: str) -> str:
    detail = _body_detail(response)

    if isinstance(detail, dict):
        for key in ["message", "status", "mode", "root_cause_signal"]:
            value = detail.get(key)
            if value:
                return str(value)

    if isinstance(detail, str) and detail:
        return detail

    return fallback


def get_service_urls() -> Dict[str, str]:
    return {
        "checkout_service_url": CHECKOUT_SERVICE_URL,
        "payment_service_url": PAYMENT_SERVICE_URL,
        "checkout_health_url": f"{CHECKOUT_SERVICE_URL}/livez",
        "checkout_status_url": f"{CHECKOUT_SERVICE_URL}/status",
        "checkout_flow_url": f"{CHECKOUT_SERVICE_URL}/checkout",
        "payment_health_url": f"{PAYMENT_SERVICE_URL}/livez",
        "payment_status_url": f"{PAYMENT_SERVICE_URL}/status",
    }


def get_checkout_health() -> Dict[str, Any]:
    return _request_json("GET", f"{CHECKOUT_SERVICE_URL}/livez")


def get_checkout_status() -> Dict[str, Any]:
    return _request_json("GET", f"{CHECKOUT_SERVICE_URL}/status")


def get_checkout_flow() -> Dict[str, Any]:
    return _request_json("GET", f"{CHECKOUT_SERVICE_URL}/checkout")


def get_payment_health() -> Dict[str, Any]:
    return _request_json("GET", f"{PAYMENT_SERVICE_URL}/livez")


def get_payment_status() -> Dict[str, Any]:
    return _request_json("GET", f"{PAYMENT_SERVICE_URL}/status")


def simulate_checkout_failure(mode: str = "redis_timeout") -> Dict[str, Any]:
    response = _request_json(
        "POST",
        f"{CHECKOUT_SERVICE_URL}/admin/fail",
        json_body={"mode": mode},
    )

    return {
        "status": "failure_injected" if response.get("ok") else "failure_injection_failed",
        "requested_mode": mode,
        "response": response,
        "snapshot": get_workload_snapshot(),
    }


def repair_checkout() -> Dict[str, Any]:
    response = _request_json("POST", f"{CHECKOUT_SERVICE_URL}/admin/repair")

    return {
        "status": "repaired" if response.get("ok") else "repair_failed",
        "response": response,
        "snapshot": get_workload_snapshot(),
    }


def verify_customer_flow() -> Dict[str, Any]:
    checkout_health = get_checkout_health()
    checkout_flow = get_checkout_flow()
    payment_health = get_payment_health()

    verified = (
        checkout_health.get("ok") is True
        and checkout_flow.get("ok") is True
        and payment_health.get("ok") is True
    )

    return {
        "status": "verified" if verified else "failed",
        "verified": verified,
        "checks": {
            "checkout_health": checkout_health,
            "checkout_flow": checkout_flow,
            "payment_health": payment_health,
        },
    }


def get_workload_snapshot() -> Dict[str, Any]:
    checkout_health = get_checkout_health()
    checkout_status = get_checkout_status()
    checkout_flow = get_checkout_flow()
    payment_health = get_payment_health()
    payment_status = get_payment_status()

    checkout_ok = checkout_health.get("ok") is True
    payment_ok = payment_health.get("ok") is True
    customer_flow_ok = checkout_flow.get("ok") is True

    checkout_state = "healthy" if checkout_ok else "critical"
    payment_state = "healthy" if payment_ok else "degraded"
    customer_flow_state = "healthy" if customer_flow_ok else "critical"

    if checkout_ok and payment_ok and customer_flow_ok:
        overall_status = "healthy"
    else:
        overall_status = "incident"

    checkout_status_body = checkout_status.get("body")
    checkout_mode = "unknown"

    if isinstance(checkout_status_body, dict):
        checkout_mode = str(checkout_status_body.get("mode") or "unknown")

    services = [
        {
            "key": "checkout-api",
            "name": "checkout-api",
            "state": checkout_state,
            "status_label": "HEALTHY" if checkout_ok else "CRITICAL",
            "service_url": CHECKOUT_SERVICE_URL,
            "health_url": f"{CHECKOUT_SERVICE_URL}/livez",
            "status_url": f"{CHECKOUT_SERVICE_URL}/status",
            "flow_url": f"{CHECKOUT_SERVICE_URL}/checkout",
            "http_status": checkout_health.get("http_status"),
            "mode": checkout_mode,
            "detail": (
                "checkout-api is healthy and accepting checkout traffic."
                if checkout_ok
                else _extract_text(checkout_health, "checkout-api is unhealthy.")
            ),
        },
        {
            "key": "payment-api",
            "name": "payment-api",
            "state": payment_state,
            "status_label": "HEALTHY" if payment_ok else "DEGRADED",
            "service_url": PAYMENT_SERVICE_URL,
            "health_url": f"{PAYMENT_SERVICE_URL}/livez",
            "status_url": f"{PAYMENT_SERVICE_URL}/status",
            "http_status": payment_health.get("http_status"),
            "detail": (
                "payment-api is healthy and payment authorization is available."
                if payment_ok
                else _extract_text(payment_health, "payment-api is not reachable.")
            ),
        },
        {
            "key": "customer-flow",
            "name": "customer checkout flow",
            "state": customer_flow_state,
            "status_label": "HEALTHY" if customer_flow_ok else "FAILED",
            "service_url": f"{CHECKOUT_SERVICE_URL}/checkout",
            "health_url": f"{CHECKOUT_SERVICE_URL}/checkout",
            "status_url": f"{CHECKOUT_SERVICE_URL}/status",
            "http_status": checkout_flow.get("http_status"),
            "detail": (
                "End-to-end checkout flow completed successfully."
                if customer_flow_ok
                else _extract_text(checkout_flow, "End-to-end checkout flow failed.")
            ),
        },
    ]

    return {
        "status": overall_status,
        "checkout_service_url": CHECKOUT_SERVICE_URL,
        "payment_service_url": PAYMENT_SERVICE_URL,
        "services": services,
        "checks": {
            "checkout_health": checkout_health,
            "checkout_status": checkout_status,
            "checkout_flow": checkout_flow,
            "payment_health": payment_health,
            "payment_status": payment_status,
        },
    }