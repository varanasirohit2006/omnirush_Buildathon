"""Domain records used by the parser, agent, and report layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


STATUSES = ("proposed", "accepted", "in progress", "blocked", "done", "missed")


@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    timestamp: datetime
    text: str


@dataclass
class Commitment:
    id: str
    owner: str | None
    task: str
    deadline: datetime | None
    deadline_text: str | None
    status: str
    confidence: float
    commitment_strength: str
    source_message_id: str
    source_text: str
    last_update_message_id: str | None = None
    clarification: str | None = None
    nudge_count: int = 0
    escalated: bool = False
    last_nudged_at: datetime | None = None
    updated_at: datetime | None = None
    evidence: list[str] = field(default_factory=list)
    review_decision: str | None = None
    review_reason: str | None = None

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.8:
            return "high"
        if self.confidence >= 0.6:
            return "medium"
        return "low"

    @property
    def needs_clarification(self) -> bool:
        return bool(self.clarification)


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    commitment_id: str | None
    timestamp: datetime
    description: str
    evidence: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutgoingMessage:
    id: str
    commitment_id: str
    recipient: str
    purpose: str
    text: str
    created_at: datetime
    simulated: bool = True


@dataclass
class AgentState:
    commitments: list[Commitment] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    outbox: list[OutgoingMessage] = field(default_factory=list)
    ignored_candidates: list[Commitment] = field(default_factory=list)
    ai_review_status: str = "not configured"
    ai_review_error: str | None = None
    clock: datetime | None = None
