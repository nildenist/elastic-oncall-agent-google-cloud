import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://127.0.0.1:9002").rstrip("/")

app = FastAPI(
    title="Checkout API",
    version="0.1.0",
    description="Demo checkout workload for Elastic On-Call Agent.",
)


runtime_state: Dict[str, Any] = {
    "mode": "healthy",
    "failure_reason": None,
    "last_changed_at": None,
}


class FailRequest(BaseModel):
    mode: Optional[str] = "redis_timeout"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_runtime_mode(mode: str, reason: Optional[str] = None) -> None:
    runtime_state["mode"] = mode
    runtime_state["failure_reason"] = reason
    runtime_state["last_changed_at"] = utc_now()


def get_runtime_mode() -> str:
    return str(runtime_state.get("mode") or "healthy")


def call_payment_api() -> Dict[str, Any]:
    payment_url = f"{PAYMENT_SERVICE_URL}/payment"

    try:
      with httpx.Client(timeout=3.0) as client:
          response = client.post(payment_url)
          response.raise_for_status()
          return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "service": "checkout-api",
                "status": "payment_dependency_failed",
                "payment_url": payment_url,
                "error": str(exc),
                "timestamp": utc_now(),
            },
        ) from exc


def get_payment_health() -> Dict[str, Any]:
    health_url = f"{PAYMENT_SERVICE_URL}/livez"

    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(health_url)
            return {
                "url": health_url,
                "reachable": response.status_code < 500,
                "http_status": response.status_code,
                "body": response.json(),
            }
    except Exception as exc:
        return {
            "url": health_url,
            "reachable": False,
            "http_status": None,
            "error": str(exc),
        }


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "checkout-api",
        "status": "running",
        "mode": get_runtime_mode(),
        "payment_service_url": PAYMENT_SERVICE_URL,
        "timestamp": utc_now(),
    }


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    mode = get_runtime_mode()

    if mode != "healthy":
        raise HTTPException(
            status_code=503,
            detail={
                "service": "checkout-api",
                "status": "unhealthy",
                "mode": mode,
                "failure_reason": runtime_state.get("failure_reason"),
                "http_status": 503,
                "timestamp": utc_now(),
            },
        )

    return {
        "service": "checkout-api",
        "status": "healthy",
        "mode": mode,
        "http_status": 200,
        "timestamp": utc_now(),
    }


@app.get("/livez")
def livez() -> Dict[str, Any]:
    mode = get_runtime_mode()

    if mode != "healthy":
        raise HTTPException(
            status_code=503,
            detail={
                "service": "checkout-api",
                "status": "unhealthy",
                "mode": mode,
                "failure_reason": runtime_state.get("failure_reason"),
                "http_status": 503,
                "timestamp": utc_now(),
            },
        )

    return {
        "service": "checkout-api",
        "status": "healthy",
        "mode": mode,
        "http_status": 200,
        "timestamp": utc_now(),
    }


@app.get("/status")
def status() -> Dict[str, Any]:
    mode = get_runtime_mode()
    payment_health = get_payment_health()

    service_status = "healthy" if mode == "healthy" else "critical"

    return {
        "service": "checkout-api",
        "status": service_status,
        "mode": mode,
        "failure_reason": runtime_state.get("failure_reason"),
        "last_changed_at": runtime_state.get("last_changed_at"),
        "dependencies": [
            {
                "service": "payment-api",
                "status": "healthy" if payment_health.get("reachable") else "unreachable",
                "health": payment_health,
            }
        ],
        "timestamp": utc_now(),
    }


@app.get("/checkout")
def checkout_get() -> Dict[str, Any]:
    return run_checkout_flow()


@app.post("/checkout")
def checkout_post() -> Dict[str, Any]:
    return run_checkout_flow()


def run_checkout_flow() -> Dict[str, Any]:
    mode = get_runtime_mode()

    if mode == "redis_timeout":
        raise HTTPException(
            status_code=500,
            detail={
                "service": "checkout-api",
                "status": "checkout_failed",
                "mode": mode,
                "root_cause_signal": "RedisTimeoutError",
                "message": "Checkout failed because checkout-api is in redis_timeout failure mode.",
                "timestamp": utc_now(),
            },
        )

    if mode != "healthy":
        raise HTTPException(
            status_code=500,
            detail={
                "service": "checkout-api",
                "status": "checkout_failed",
                "mode": mode,
                "message": "Checkout failed because checkout-api is not healthy.",
                "timestamp": utc_now(),
            },
        )

    payment_result = call_payment_api()

    return {
        "service": "checkout-api",
        "status": "checkout_completed",
        "mode": mode,
        "order_id": "demo-order-0001",
        "payment": payment_result,
        "timestamp": utc_now(),
    }


@app.post("/admin/fail")
def admin_fail(request: FailRequest) -> Dict[str, Any]:
    requested_mode = request.mode or "redis_timeout"

    if requested_mode not in {"redis_timeout", "runtime_config_regression"}:
        raise HTTPException(
            status_code=400,
            detail={
                "service": "checkout-api",
                "status": "invalid_failure_mode",
                "allowed_modes": ["redis_timeout", "runtime_config_regression"],
                "timestamp": utc_now(),
            },
        )

    set_runtime_mode(
        mode=requested_mode,
        reason="Demo incident injected by Elastic On-Call Agent.",
    )

    return {
        "service": "checkout-api",
        "status": "failure_injected",
        "mode": get_runtime_mode(),
        "failure_reason": runtime_state.get("failure_reason"),
        "timestamp": utc_now(),
    }


@app.post("/admin/repair")
def admin_repair() -> Dict[str, Any]:
    previous_mode = get_runtime_mode()

    set_runtime_mode(
        mode="healthy",
        reason="Agent remediation repaired checkout-api runtime mode.",
    )

    return {
        "service": "checkout-api",
        "status": "repaired",
        "previous_mode": previous_mode,
        "mode": get_runtime_mode(),
        "timestamp": utc_now(),
    }