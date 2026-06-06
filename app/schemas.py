from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AlertPayload(BaseModel):
    alert_id: str = Field(default="demo-alert-001")
    service: str = Field(default="checkout-service")
    environment: str = Field(default="prod")
    severity: str = Field(default="critical")
    signal: str = Field(default="latency_spike")
    message: str = Field(default="checkout-service p95 latency increased")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    time_window_minutes: int = Field(default=30)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    source: str
    title: str
    detail: str
    value: Optional[str] = None
    confidence: str = "medium"


class RootCauseHypothesis(BaseModel):
    title: str
    explanation: str
    confidence: str
    supporting_evidence: List[str] = Field(default_factory=list)


class NextAction(BaseModel):
    title: str
    description: str
    requires_human_approval: bool = True
    risk_level: str = "medium"


class IncidentBrief(BaseModel):
    incident_id: str
    status: str = "active"
    summary: str
    probable_root_cause: str
    confidence: str
    affected_services: List[str] = Field(default_factory=list)
    timeline: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    hypotheses: List[RootCauseHypothesis] = Field(default_factory=list)
    next_actions: List[NextAction] = Field(default_factory=list)
    human_approval_required: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FollowUpRequest(BaseModel):
    question: str
    incident_id: Optional[str] = None


class FollowUpResponse(BaseModel):
    incident_id: Optional[str] = None
    answer: str
    evidence_used: List[str] = Field(default_factory=list)
