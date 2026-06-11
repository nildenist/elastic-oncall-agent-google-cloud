from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI


app = FastAPI(
    title="Payment API",
    version="0.1.0",
    description="Demo payment workload for Elastic On-Call Agent.",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "payment-api",
        "status": "running",
        "message": "Payment API is available.",
        "timestamp": utc_now(),
    }


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    return {
        "service": "payment-api",
        "status": "healthy",
        "http_status": 200,
        "timestamp": utc_now(),
    }


@app.get("/livez")
def livez() -> Dict[str, Any]:
    return {
        "service": "payment-api",
        "status": "healthy",
        "http_status": 200,
        "timestamp": utc_now(),
    }


@app.get("/status")
def status() -> Dict[str, Any]:
    return {
        "service": "payment-api",
        "status": "healthy",
        "mode": "normal",
        "dependencies": [],
        "timestamp": utc_now(),
    }


@app.post("/payment")
def payment() -> Dict[str, Any]:
    return {
        "service": "payment-api",
        "status": "authorized",
        "amount": 42.0,
        "currency": "USD",
        "transaction_id": "demo-payment-0001",
        "timestamp": utc_now(),
    }