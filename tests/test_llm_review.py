from project_chaser.agent import new_state
from project_chaser.chat import parse_chat
from project_chaser.extractor import extract_commitments
from project_chaser.llm import LLMConfig, LLMError, LLMReview, OpenAICompatibleReviewer


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
