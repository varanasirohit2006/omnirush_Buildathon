from project_chaser.agent import new_state
from project_chaser.chat import parse_chat
from project_chaser.extractor import extract_commitments
from project_chaser.llm import LLMConfig, LLMError, LLMReview, OpenAICompatibleReviewer
from project_chaser.report import build_report
from app import render_page


class FakeReviewer:
    def __init__(self, decision_by_id=None, error=None):
        self.decision_by_id = decision_by_id or {}
        self.error = error
        self.seen_ids = []

    def review(self, messages, candidates):
        self.seen_ids = [candidate.id for candidate in candidates]
        if self.error:
            raise self.error
        return [
            LLMReview(
                candidate_id=candidate.id,
                decision=self.decision_by_id.get(candidate.id, "clarify"),
                confidence=0.9,
                reason="fake review for deterministic test",
                clarification="Can you confirm the exact deadline?",
            )
            for candidate in candidates
        ]


def test_ai_review_receives_only_low_confidence_candidates_and_can_filter_noise():
    reviewer = FakeReviewer({"c002": "ignore"})
    state = new_state(
        "2026-10-19 09:00 - Alice: I'll finish the slides by Friday\n"
        "2026-10-19 09:01 - Ben: Maybe I can clean up the README",
        reviewer=reviewer,
    )

    assert reviewer.seen_ids == ["c002"]
    assert [item.id for item in state.commitments] == ["c001"]
    assert [item.id for item in state.ignored_candidates] == ["c002"]
    assert state.ai_review_status == "applied to 1 low-confidence candidate(s)"


def test_ai_cannot_promote_tentative_work_to_an_accepted_commitment():
    reviewer = FakeReviewer({"c001": "accepted"})
    state = new_state(
        "2026-10-19 09:00 - Ben: I'll try to finish the API tomorrow night",
        reviewer=reviewer,
    )

    assert state.commitments[0].status == "proposed"
    assert state.commitments[0].review_decision == "accepted"


def test_api_failure_keeps_the_deterministic_candidates():
    reviewer = FakeReviewer(error=LLMError("offline"))
    state = new_state(
        "2026-10-19 09:00 - Ben: Maybe I can clean up the README",
        reviewer=reviewer,
    )

    assert len(state.commitments) == 1
    assert state.ai_review_status == "fallback: unavailable"
    assert state.ai_review_error == "offline"
    assert state.events[0].kind == "llm_review_failed"


def test_openai_compatible_json_response_is_parsed_without_network():
    messages = parse_chat("2026-10-19 09:00 - Ben: Maybe I can clean up the README")
    candidate = extract_commitments(messages)[0]
    reviewer = OpenAICompatibleReviewer(LLMConfig("https://example.invalid", "test-key", "test-model"))
    reviewer._request = lambda payload: {
        "choices": [
            {
                "message": {
                    "content": '{"reviews":[{"candidate_id":"c001","decision":"clarify","confidence":0.91,"reason":"possible work without a date","clarification":"What date should I track?"}]}'
                }
            }
        ]
    }

    reviews = reviewer.review(messages, [candidate])

    assert reviews[0].candidate_id == "c001"
    assert reviews[0].decision == "clarify"
    assert reviews[0].clarification == "What date should I track?"


def test_gemini_configuration_uses_expected_endpoint_without_network(monkeypatch):
    monkeypatch.setenv("LLM_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "placeholder-for-test")
    monkeypatch.setenv("LLM_MODEL", "gemini-test-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "17")

    config = LLMConfig.from_env()

    assert config is not None
    assert config.url.endswith("/v1beta/openai/chat/completions")
    assert config.model == "gemini-test-model"
    assert config.timeout_seconds == 17


def test_native_gemini_response_can_be_normalized_to_compat_shape():
    messages = parse_chat("2026-10-19 09:02 - Ben: Maybe I can clean up the README")
    candidate = extract_commitments(messages)[0]
    reviewer = OpenAICompatibleReviewer(LLMConfig("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "test-key", "gemma-test"))
    reviewer._request = lambda payload: (_ for _ in ()).throw(LLMError("compatibility failure"))
    reviewer._native_gemini_request = lambda payload: {
        "choices": [{"message": {"content": '{"reviews":[{"candidate_id":"c001","decision":"proposed","confidence":0.8,"reason":"needs confirmation","clarification":null}]}'}}]
    }

    reviews = reviewer.review(messages, [candidate])

    assert reviews[0].decision == "proposed"


def test_ai_review_provenance_is_visible_in_board_and_report():
    reviewer = FakeReviewer({"c001": "clarify"})
    state = new_state("2026-10-19 09:00 - Ben: Maybe I can clean up the README", reviewer=reviewer)

    report = build_report(state)
    page = render_page(state, "", "")

    assert report["summary"]["ai_reviewed"] == 1
    assert report["commitments"][0]["ai_review"] == "clarify"
    assert "AI review" in page
    assert "fake review for deterministic test" in page
