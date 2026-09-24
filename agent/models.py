from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CaseStatus(str, Enum):
    OPEN = "open"
    EVIDENCE_REQUESTED = "evidence_requested"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"


class ActionStatus(str, Enum):
    RECOMMENDED = "recommended"
    EXECUTED = "executed"
    PENDING_APPROVAL = "pending_approval"
    FAILED = "failed"


class Trigger(BaseModel):
    type: Literal["risk_score", "customer_report", "analyst_request"]
    source: str
    transaction_id: str | None = None
    account_id: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Evidence(BaseModel):
    evidence_id: str
    type: str
    source: str
    summary: str
    strength: float = Field(ge=0, le=1)
    polarity: Literal["supports_fraud", "supports_legitimate", "neutral"]
    observed_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    finding_id: str
    title: str
    summary: str
    severity: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class NextBestAction(BaseModel):
    action: str
    rationale: str
    confidence: float = Field(ge=0, le=1)
    requires_human_approval: bool = False
    recorded_at: datetime = Field(default_factory=utc_now)


class Action(BaseModel):
    action_id: str
    action: str
    status: ActionStatus
    rationale: str
    requires_human_approval: bool = False
    approval_route: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class CaseRecord(BaseModel):
    case_id: str
    status: CaseStatus
    trigger: Trigger
    account_id: str | None = None
    transaction_id: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    matched_patterns: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    confidence: float = Field(default=0, ge=0, le=1)
    enough_evidence_before_request: bool = False
    additional_evidence_requested: dict[str, Any] | None = None
    additional_evidence_received: bool = False
    next_best_action_before_evidence: NextBestAction | None = None
    next_best_action_after_evidence: NextBestAction | None = None
    decisions: list[str] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    explanation: str = ""
    outcome: str | None = None
    sar_required: bool = False
    sar_text: str | None = None
    graph_written: bool = False
    opened_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
