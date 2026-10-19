"""Optional OpenAI-compatible review for low-confidence commitments.

The reviewer is deliberately a narrow classifier. It does not replace the
deterministic parser, and callers must still apply the safety gates in agent.py.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Commitment, Message


class LLMError(RuntimeError):
    """Raised when the optional reviewer cannot produce a valid response."""


@dataclass(frozen=True)
class LLMReview:
    candidate_id: str
    decision: str
    confidence: float
    reason: str
    clarification: str | None = None


@dataclass(frozen=True)
class LLMConfig:
    url: str
    api_key: str
    model: str
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> LLMConfig | None:
        url = os.environ.get("LLM_API_URL", "").strip()
        api_key = os.environ.get("LLM_API_KEY", "").strip()
        model = os.environ.get("LLM_MODEL", "").strip()
        if not url or not api_key or not model:
            return None
        try:
            timeout = int(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
        except ValueError:
            timeout = 30
        return cls(url=url, api_key=api_key, model=model, timeout_seconds=max(5, min(timeout, 120)))


SYSTEM_PROMPT = """You review only low-confidence group-project commitment candidates.
Return JSON only with this shape:
{"reviews":[{"candidate_id":"c001","decision":"accepted|proposed|clarify|ignore","confidence":0.0,"reason":"short explanation","clarification":"question or null"}]}

Rules:
- Do not invent an owner, task, or deadline.
- Use only the supplied candidate and source message.
- 'accepted' is allowed only when the source clearly commits a named owner to concrete work with a trackable deadline.
- 'proposed' means possible work that needs confirmation.
- 'clarify' means the message may describe work but owner, commitment strength, or deadline is unclear.
- 'ignore' means ordinary conversation, a general suggestion, a conditional offer, or non-actionable text.
- Keep confidence between 0 and 1.
- Return one review for every supplied candidate ID.
"""


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [item.get("text", "") for item in value if isinstance(item, dict)]
        return "".join(parts)
    return ""


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError("The reviewer returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("reviews"), list):
        raise LLMError("The reviewer response did not contain a reviews list")
    return payload


class OpenAICompatibleReviewer:
    """A minimal JSON reviewer for OpenAI-compatible chat-completions APIs."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @classmethod
    def from_env(cls) -> OpenAICompatibleReviewer | None:
        config = LLMConfig.from_env()
        return cls(config) if config else None

    def review(self, messages: list[Message], candidates: list[Commitment]) -> list[LLMReview]:
        if not candidates:
            return []
        source_by_id = {message.id: message for message in messages}
        candidate_payload = []
        for candidate in candidates:
            source = source_by_id.get(candidate.source_message_id)
            candidate_payload.append(
                {
                    "candidate_id": candidate.id,
                    "owner_from_parser": candidate.owner,
                    "task_from_parser": candidate.task,
                    "deadline_from_parser": candidate.deadline_text,
                    "parser_status": candidate.status,
                    "parser_strength": candidate.commitment_strength,
                    "source_message_id": candidate.source_message_id,
                    "source_sender": source.sender if source else None,
                    "source_text": source.text if source else candidate.source_text,
                }
            )
        user_prompt = "Review these candidates and return the required JSON:\n" + json.dumps(candidate_payload, ensure_ascii=False)
        payload = {
            "model": self.config.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        response = self._request(payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("The reviewer response had no assistant content") from exc
        parsed = _parse_json(_content_text(content))
        expected_ids = {candidate.id for candidate in candidates}
        reviews: list[LLMReview] = []
        for item in parsed["reviews"]:
            if not isinstance(item, dict) or item.get("candidate_id") not in expected_ids:
                continue
            decision = str(item.get("decision", "clarify")).lower()
            if decision not in {"accepted", "proposed", "clarify", "ignore"}:
                decision = "clarify"
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            reviews.append(
                LLMReview(
                    candidate_id=item["candidate_id"],
                    decision=decision,
                    confidence=max(0.0, min(confidence, 1.0)),
                    reason=str(item.get("reason", "No reason supplied"))[:500],
                    clarification=(str(item["clarification"])[:300] if item.get("clarification") else None),
                )
            )
        if {review.candidate_id for review in reviews} != expected_ids:
            raise LLMError("The reviewer did not return one valid review per candidate")
        return reviews

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.config.url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise LLMError(f"Reviewer API returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError("Reviewer API request failed") from exc
