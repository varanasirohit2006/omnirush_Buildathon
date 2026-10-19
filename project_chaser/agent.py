"""The bounded follow-up loop and reply handling."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .chat import parse_chat
from .extractor import _resolve_deadline, extract_commitments
from .models import AgentState, Commitment, Event, Message, OutgoingMessage


REMINDER_WINDOW = timedelta(days=2)
QUIET_START = 21
QUIET_END = 8


def _event_id(state: AgentState) -> str:
    return f"e{len(state.events) + 1:03d}"


def _outgoing_id(state: AgentState) -> str:
    return f"o{len(state.outbox) + 1:03d}"


def new_state(chat_text: str, clock: datetime | None = None) -> AgentState:
    messages = parse_chat(chat_text)
    commitments = extract_commitments(messages)
    initial_clock = clock or max((message.timestamp for message in messages), default=datetime(2026, 10, 19, 9, 0))
    state = AgentState(messages=messages, commitments=commitments, clock=initial_clock)
    for commitment in commitments:
        state.events.append(
            Event(
                id=_event_id(state),
                kind="commitment_extracted",
                commitment_id=commitment.id,
                timestamp=commitment.updated_at or initial_clock,
                description=f"Extracted {commitment.commitment_strength} commitment: {commitment.task}",
                evidence=commitment.source_message_id,
            )
        )
        if commitment.clarification:
            state.events.append(
                Event(
                    id=_event_id(state),
                    kind="clarification_needed",
                    commitment_id=commitment.id,
                    timestamp=commitment.updated_at or initial_clock,
                    description=commitment.clarification,
                    evidence=commitment.source_message_id,
                )
            )
    return state


def _is_quiet_hour(clock: datetime) -> bool:
    return clock.hour >= QUIET_START or clock.hour < QUIET_END


def _send_outbox(state: AgentState, commitment: Commitment, purpose: str, text: str) -> None:
    now = state.clock or datetime.now()
    state.outbox.append(
        OutgoingMessage(
            id=_outgoing_id(state),
            commitment_id=commitment.id,
            recipient=commitment.owner or "unassigned",
            purpose=purpose,
            text=text,
            created_at=now,
        )
    )
    if purpose == "reminder":
        commitment.nudge_count += 1
        commitment.last_nudged_at = now
    else:
        commitment.escalated = True


def run_agent(state: AgentState) -> list[Event]:
    """Evaluate risk and create at most the allowed outgoing actions.

    This function is intentionally idempotent at a given clock value: repeated UI
    reruns do not duplicate reminders or escalations.
    """

    now = state.clock or datetime.now()
    created: list[Event] = []
    for commitment in state.commitments:
        if not commitment.owner or commitment.clarification or not commitment.deadline:
            continue
        if commitment.status == "done":
            continue
        if commitment.status == "blocked":
            if not any(event.kind == "blocked_risk" and event.commitment_id == commitment.id for event in state.events):
                event = Event(
                    id=_event_id(state),
                    kind="blocked_risk",
                    commitment_id=commitment.id,
                    timestamp=now,
                    description="Blocked work is at risk. Suggested next step: agree on a small unblocker and a new owner or date.",
                    evidence=commitment.last_update_message_id or commitment.source_message_id,
                )
                state.events.append(event)
                created.append(event)
            continue

        if now >= commitment.deadline:
            if commitment.status != "missed":
                commitment.status = "missed"
                event = Event(
                    id=_event_id(state),
                    kind="commitment_missed",
                    commitment_id=commitment.id,
                    timestamp=now,
                    description=f"Deadline passed without completion: {commitment.task}",
                    evidence=commitment.last_update_message_id or commitment.source_message_id,
                )
                state.events.append(event)
                created.append(event)
            if not commitment.escalated and not _is_quiet_hour(now):
                text = (
                    f"Hi {commitment.owner} — {commitment.task} is past the tracked deadline. "
                    "Could you share a quick status or blocker so the group can adjust?"
                )
                _send_outbox(state, commitment, "escalation", text)
                event = Event(
                    id=_event_id(state),
                    kind="escalation_sent",
                    commitment_id=commitment.id,
                    timestamp=now,
                    description="One overdue escalation added to the local outbox.",
                    evidence=commitment.source_message_id,
                )
                state.events.append(event)
                created.append(event)
            continue

        if (
            now >= commitment.deadline - REMINDER_WINDOW
            and commitment.nudge_count < 2
            and commitment.last_nudged_at != now
            and not _is_quiet_hour(now)
        ):
            tone = "friendly" if commitment.nudge_count == 0 else "firmer"
            text = (
                f"Hi {commitment.owner} — friendly {tone} check-in: {commitment.task} is due "
                f"by {commitment.deadline.strftime('%A at %H:%M')}. Reply with done, a blocker, or a new date."
            )
            _send_outbox(state, commitment, "reminder", text)
            event = Event(
                id=_event_id(state),
                kind="reminder_sent",
                commitment_id=commitment.id,
                timestamp=now,
                description=f"A bounded {tone} reminder was added to the local outbox.",
                evidence=commitment.source_message_id,
            )
            state.events.append(event)
            created.append(event)
    return created


def advance_clock(state: AgentState, delta: timedelta) -> list[Event]:
    state.clock = (state.clock or datetime.now()) + delta
    return run_agent(state)


def _find_commitment(state: AgentState, sender: str, text: str) -> Commitment | None:
    candidates = [
        commitment
        for commitment in state.commitments
        if commitment.owner and commitment.owner.lower() == sender.lower() and commitment.status not in ("done", "missed")
    ]
    if not candidates:
        return None
    lowered = text.lower()
    for candidate in candidates:
        if any(word in lowered for word in candidate.task.lower().split() if len(word) > 4):
            return candidate
    return candidates[0]


def _reply_deadline(text: str, reference: datetime) -> tuple[datetime | None, str | None]:
    match = re.search(
        r"\b(?:until|by|on)\s+(tomorrow(?:\s+(?:morning|afternoon|night))?|"
        r"next\s+(?:mon|tues?|wed(?:nesday)?|thu(?:rsday)?|fri|sat(?:urday)?|sun(?:day)?)|"
        r"(?:mon|tues?|wed(?:nesday)?|thu(?:rsday)?|fri|sat(?:urday)?|sun(?:day)?)|"
        r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    value = match.group(1)
    clean = value.replace("next ", "")
    return _resolve_deadline(clean, reference), value


def handle_reply(state: AgentState, sender: str, text: str) -> Commitment | None:
    """Apply a human reply to the most likely open commitment."""

    commitment = _find_commitment(state, sender, text)
    if commitment is None:
        return None
    now = state.clock or datetime.now()
    message = Message(id=f"m{len(state.messages) + 1:03d}", sender=sender, timestamp=now, text=text)
    state.messages.append(message)
    lowered = text.lower()
    commitment.last_update_message_id = message.id
    commitment.updated_at = now
    commitment.evidence.append(message.id)

    new_deadline, deadline_text = _reply_deadline(text, now)
    if new_deadline and any(token in lowered for token in ("more time", "extend", "until", "by ")):
        commitment.deadline = new_deadline
        commitment.deadline_text = deadline_text
        commitment.status = "in progress"
        commitment.clarification = None
        description = f"{sender} requested more time; tracked deadline moved to {new_deadline:%Y-%m-%d %H:%M}."
        kind = "deadline_changed"
    elif any(token in lowered for token in ("stuck", "blocked", "blocker", "can't", "cannot", "issue with")):
        commitment.status = "blocked"
        description = "Marked blocked. Suggested next step: ask for the smallest unblocker and a revised date."
        kind = "reply_blocked"
    elif re.search(r"\b(done|finished|complete|completed|sent it|all set)\b", lowered):
        commitment.status = "done"
        description = f"{sender} reported completion for {commitment.task}."
        kind = "reply_done"
    else:
        commitment.status = "in progress"
        description = f"Progress update received from {sender}."
        kind = "reply_progress"

    event = Event(
        id=_event_id(state),
        kind=kind,
        commitment_id=commitment.id,
        timestamp=now,
        description=description,
        evidence=message.id,
    )
    state.events.append(event)
    return commitment


def correct_commitment(
    state: AgentState,
    commitment_id: str,
    *,
    owner: str | None = None,
    status: str | None = None,
    clarification: str | None = None,
) -> Commitment | None:
    """Apply a visible board correction and preserve the correction as evidence."""

    commitment = next((item for item in state.commitments if item.id == commitment_id), None)
    if commitment is None:
        return None
    now = state.clock or datetime.now()
    changes: list[str] = []
    if owner is not None and owner.strip() and owner.strip() != commitment.owner:
        changes.append(f"owner: {commitment.owner or 'unassigned'} → {owner.strip()}")
        commitment.owner = owner.strip()
        commitment.clarification = None
    if status and status != commitment.status:
        changes.append(f"status: {commitment.status} → {status}")
        commitment.status = status
    if clarification is not None and clarification != commitment.clarification:
        changes.append("clarification updated")
        commitment.clarification = clarification or None
    if not changes:
        return commitment
    event = Event(
        id=_event_id(state),
        kind="commitment_corrected",
        commitment_id=commitment.id,
        timestamp=now,
        description="; ".join(changes),
        evidence=commitment.source_message_id,
    )
    state.events.append(event)
    commitment.evidence.append(event.id)
    commitment.updated_at = now
    return commitment
