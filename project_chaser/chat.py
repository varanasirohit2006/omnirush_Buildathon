"""Parse common WhatsApp exports and simple pasted chat text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .models import Message


CHAT_LINE_RE = re.compile(
    r"^\[?(?P<date>\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
    r"[, ]+?(?P<time>\d{1,2}:\d{2}(?:\s?[APap][Mm])?)\]?\s*[-–]?\s*"
    r"(?P<sender>[^:]+):\s?(?P<text>.*)$"
)
SIMPLE_LINE_RE = re.compile(r"^(?P<sender>[^:]{1,50}):\s?(?P<text>.+)$")


def _parse_timestamp(date_text: str, time_text: str) -> datetime:
    normalized = f"{date_text} {time_text.upper().replace('  ', ' ')}"
    formats = (
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%d/%m/%y %H:%M",
        "%d/%m/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %H:%M",
        "%d/%m/%y %I:%M %p",
        "%d/%m/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p",
        "%m/%d/%Y %I:%M %p",
        "%Y-%m-%d %I:%M %p",
    )
    for date_format in formats:
        try:
            return datetime.strptime(normalized, date_format)
        except ValueError:
            continue
    raise ValueError(f"Unsupported chat timestamp: {date_text} {time_text}")


def parse_chat(text: str, fallback_start: datetime | None = None) -> list[Message]:
    """Return normalized messages from a WhatsApp export or simple pasted text.

    Continuation lines are appended to the preceding message. For an un-timestamped
    paste, lines in ``Name: message`` form receive synthetic minute-spaced timestamps.
    The synthetic time is only for demo scheduling; the original text remains evidence.
    """

    if not text or not text.strip():
        return []

    fallback_start = fallback_start or datetime(2026, 10, 19, 9, 0)
    parsed: list[Message] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = CHAT_LINE_RE.match(line)
        if match:
            timestamp = _parse_timestamp(match.group("date"), match.group("time"))
            parsed.append(
                Message(
                    id=f"m{len(parsed) + 1:03d}",
                    sender=match.group("sender").strip(),
                    timestamp=timestamp,
                    text=match.group("text").strip(),
                )
            )
            continue

        simple = SIMPLE_LINE_RE.match(line)
        if simple:
            parsed.append(
                Message(
                    id=f"m{len(parsed) + 1:03d}",
                    sender=simple.group("sender").strip(),
                    timestamp=fallback_start + timedelta(minutes=len(parsed)),
                    text=simple.group("text").strip(),
                )
            )
            continue

        if parsed:
            previous = parsed[-1]
            parsed[-1] = Message(
                id=previous.id,
                sender=previous.sender,
                timestamp=previous.timestamp,
                text=f"{previous.text}\n{line}",
            )

    return parsed
