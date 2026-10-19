"""Explainable commitment extraction with conservative ambiguity handling."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .models import Commitment, Message


DIRECT_COMMITMENT_RE = re.compile(
    r"\b(i['’]?ll|i will|i can|i am taking|i'm taking|taking|main|mai)\b",
    re.IGNORECASE,
)
TENTATIVE_RE = re.compile(r"\b(i['’]?ll try|i will try|maybe i can|i might|try to)\b", re.IGNORECASE)
UNASSIGNED_RE = re.compile(r"\b(someone|anyone|somebody)\s+(should|can|needs? to|has to)\b", re.IGNORECASE)
VAGUE_DEADLINE_RE = re.compile(
    r"\b(sometime\s+next\s+week|sometime\s+this\s+week|later|soon|eventually|when\s+you\s+can)\b",
    re.IGNORECASE,
)
DEADLINE_RE = re.compile(
    r"\b(?:by|before|on|due(?:\s+on)?|until)\s+"
    r"(?P<value>tomorrow(?:\s+(?:morning|afternoon|night))?|tonight|today|"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu|fri|sat|sun)|"
    r"\d{1,2}(?:st|nd|rd|th)?(?:[/-]\d{1,2}(?:[/-]\d{2,4})?)?)\b",
    re.IGNORECASE,
)
BARE_WEEKDAY_RE = re.compile(
    r"\b(?P<weekday>mon(?:day)?|tues?(?:day)?|wed(?:nesday)?|thu(?:rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
    re.IGNORECASE,
)
TASK_PREFIX_RE = re.compile(
    r"^(?:i['’]?ll|i will|i can|i am taking|i'm taking|taking|main|mai|me|"
    r"try to|do|finish|handle|complete|work on)\s+",
    re.IGNORECASE,
)

WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def _next_weekday(reference: datetime, weekday: int) -> datetime:
    delta = (weekday - reference.weekday()) % 7
    if delta == 0:
        delta = 7
    return (reference + timedelta(days=delta)).replace(hour=18, minute=0, second=0, microsecond=0)


def _resolve_deadline(value: str, reference: datetime) -> datetime | None:
    clean = value.lower().strip()
    if clean.startswith("tomorrow"):
        hour = 21 if "night" in clean else 18
        return (reference + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    if clean == "tonight":
        return reference.replace(hour=21, minute=0, second=0, microsecond=0)
    if clean == "today":
        return reference.replace(hour=18, minute=0, second=0, microsecond=0)
    if clean in WEEKDAYS:
        return _next_weekday(reference, WEEKDAYS[clean])
    date_match = re.search(r"\d{1,2}(?:st|nd|rd|th)?[/-]\d{1,2}(?:[/-]\d{2,4})?", clean)
    if date_match:
        value = re.sub(r"(st|nd|rd|th)", "", date_match.group(0))
        parts = re.split(r"[/-]", value)
        try:
            if len(parts) == 2:
                day, month = (int(parts[0]), int(parts[1]))
                year = reference.year
            else:
                first, second, third = (int(part) for part in parts)
                if len(parts[2]) == 4 or first > 12:
                    year, month, day = first, second, third
                else:
                    month, day, year = first, second, third
                if year < 100:
                    year += 2000
            candidate = datetime(year, month, day, 18, 0)
            if candidate < reference:
                candidate = candidate.replace(year=candidate.year + 1)
            return candidate
        except ValueError:
            return None
    return None


def _deadline_for(message: Message) -> tuple[datetime | None, str | None, bool]:
    vague = VAGUE_DEADLINE_RE.search(message.text)
    if vague:
        return None, vague.group(0), True
    deadline_match = DEADLINE_RE.search(message.text)
    if deadline_match:
        value = deadline_match.group("value")
        return _resolve_deadline(value, message.timestamp), value, False
    bare_relative = re.search(r"\b(tomorrow(?:\s+(?:morning|afternoon|night))?|tonight|today)\b", message.text, re.IGNORECASE)
    if bare_relative:
        value = bare_relative.group(1)
        return _resolve_deadline(value, message.timestamp), value, False
    weekday = BARE_WEEKDAY_RE.search(message.text)
    if weekday and any(token in message.text.lower() for token in ("friday", "sunday", "monday", "tuesday", "wednesday", "thursday", "saturday")):
        value = weekday.group("weekday")
        return _resolve_deadline(value, message.timestamp), value, False
    return None, None, False


def _task_text(message_text: str, deadline_text: str | None) -> str:
    task = message_text.strip()
    if deadline_text:
        task = re.sub(
            rf"\b(?:by|before|on|due(?:\s+on)?|until)\s+{re.escape(deadline_text)}\b",
            "",
            task,
            flags=re.IGNORECASE,
        )
        task = re.sub(rf"\b{re.escape(deadline_text)}\b", "", task, flags=re.IGNORECASE)
    task = TASK_PREFIX_RE.sub("", task)
    task = re.sub(r"\b(i['’]?ll try|i will try|maybe i can|i might|try to)\b", "", task, flags=re.IGNORECASE)
    task = re.sub(r"^\s*(?:bro|yaar)\s+", "", task, flags=re.IGNORECASE)
    task = re.sub(r"^\s*to\s+", "", task, flags=re.IGNORECASE)
    task = re.sub(r"\b(someone|anyone|somebody)\s+(should|can|needs? to|has to)\b", "", task, flags=re.IGNORECASE)
    task = re.sub(r"\s+", " ", task).strip(" .,!?:;-\n")
    return task or "Unspecified project work"


def extract_commitments(messages: list[Message]) -> list[Commitment]:
    """Extract commitments conservatively and retain the source message as evidence."""

    commitments: list[Commitment] = []
    for message in messages:
        text = message.text.strip()
        lower = text.lower()
        unassigned = bool(UNASSIGNED_RE.search(text))
        direct = bool(DIRECT_COMMITMENT_RE.search(text))
        tentative = bool(TENTATIVE_RE.search(text))
        if not direct and not unassigned:
            continue
        if lower.startswith(("let's", "lets ", "we should", "we can ")) and not re.search(r"\bi('ll| will| can)\b", lower):
            continue

        deadline, deadline_text, vague = _deadline_for(message)
        task = _task_text(text, deadline_text)
        clarification: str | None = None
        owner = None if unassigned else message.sender
        if owner is None:
            clarification = "Who owns this work, and what date should I track?"
        elif deadline is None:
            clarification = "What deadline should I track for this commitment?"
        elif vague:
            clarification = "The deadline is vague. What exact date should I track?"

        if unassigned:
            confidence = 0.42
            strength = "unassigned"
            status = "proposed"
        elif tentative:
            confidence = 0.62 if deadline else 0.52
            strength = "tentative"
            status = "proposed"
        elif deadline is None:
            confidence = 0.74
            strength = "direct"
            status = "proposed"
        else:
            confidence = 0.94
            strength = "direct"
            status = "accepted"

        commitments.append(
            Commitment(
                id=f"c{len(commitments) + 1:03d}",
                owner=owner,
                task=task,
                deadline=deadline,
                deadline_text=deadline_text,
                status=status,
                confidence=confidence,
                commitment_strength=strength,
                source_message_id=message.id,
                source_text=message.text,
                clarification=clarification,
                updated_at=message.timestamp,
                evidence=[message.id],
            )
        )
    return commitments
