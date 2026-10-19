"""Evidence-based progress report generation."""

from __future__ import annotations

from collections import defaultdict

from .models import AgentState, Commitment


def _evidence(commitment: Commitment) -> str:
    return ", ".join(commitment.evidence) or commitment.source_message_id


def build_report(state: AgentState) -> dict[str, object]:
    commitments = state.commitments
    by_owner: dict[str, dict[str, int]] = defaultdict(lambda: {"accepted": 0, "done": 0, "blocked": 0, "missed": 0})
    for commitment in commitments:
        owner = commitment.owner or "Unassigned"
        if commitment.status in by_owner[owner]:
            by_owner[owner][commitment.status] += 1
        if commitment.status in ("accepted", "in progress", "proposed"):
            by_owner[owner]["accepted"] += 1

    return {
        "generated_at": state.clock,
        "summary": {
            "total": len(commitments),
            "done": sum(item.status == "done" for item in commitments),
            "blocked": sum(item.status == "blocked" for item in commitments),
            "missed": sum(item.status == "missed" for item in commitments),
            "clarifications": sum(item.needs_clarification for item in commitments),
            "ai_reviewed": sum(item.review_decision is not None for item in commitments),
            "ai_ignored": len(state.ignored_candidates),
        },
        "commitments": [
            {
                "owner": item.owner or "Unassigned",
                "task": item.task,
                "status": item.status,
                "deadline": item.deadline.strftime("%Y-%m-%d %H:%M") if item.deadline else "Unclear",
                "evidence": _evidence(item),
                "ai_review": item.review_decision,
                "ai_review_confidence": item.review_confidence,
                "ai_review_reason": item.review_reason,
            }
            for item in commitments
        ],
        "by_owner": dict(by_owner),
        "risks": [
            {
                "task": item.task,
                "owner": item.owner or "Unassigned",
                "reason": "blocked" if item.status == "blocked" else "deadline missed",
                "evidence": _evidence(item),
            }
            for item in commitments
            if item.status in ("blocked", "missed")
        ],
        "clarifications": [
            {
                "task": item.task,
                "question": item.clarification,
                "evidence": item.source_message_id,
            }
            for item in commitments
            if item.clarification
        ],
    }
