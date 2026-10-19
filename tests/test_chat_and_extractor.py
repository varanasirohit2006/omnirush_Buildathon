from datetime import datetime

from project_chaser.chat import parse_chat
from project_chaser.extractor import extract_commitments


def test_parse_whatsapp_lines_and_continuations():
    messages = parse_chat(
        "2026-10-19 09:00 - Alice: I'll do the slides by Friday\n"
        "continued detail\n"
        "2026-10-19 09:05 - Ben: unrelated chat"
    )

    assert len(messages) == 2
    assert messages[0].sender == "Alice"
    assert "continued detail" in messages[0].text
    assert messages[1].timestamp == datetime(2026, 10, 19, 9, 5)


def test_clear_commitment_has_owner_deadline_and_evidence():
    messages = parse_chat("2026-10-19 09:00 - Alice: I'll do the slides by Friday")

    commitments = extract_commitments(messages)

    assert len(commitments) == 1
    commitment = commitments[0]
    assert commitment.owner == "Alice"
    assert commitment.task == "do the slides"
    assert commitment.deadline == datetime(2026, 10, 23, 18, 0)
    assert commitment.status == "accepted"
    assert commitment.confidence_label == "high"
    assert commitment.source_message_id == "m001"


def test_tentative_and_ambiguous_language_never_becomes_accepted():
    messages = parse_chat(
        "2026-10-19 09:00 - Ben: I'll try to finish the API tomorrow night\n"
        "2026-10-19 09:01 - Cara: Someone should handle the demo sometime next week"
    )

    commitments = extract_commitments(messages)

    assert len(commitments) == 2
    assert commitments[0].status == "proposed"
    assert commitments[0].commitment_strength == "tentative"
    assert commitments[1].owner is None
    assert commitments[1].deadline is None
    assert commitments[1].needs_clarification
    assert commitments[1].status == "proposed"


def test_bare_relative_deadline_is_resolved_without_a_guess_from_vague_language():
    messages = parse_chat("2026-10-19 09:00 - Ben: I'll try to finish the API tomorrow night")

    commitment = extract_commitments(messages)[0]

    assert commitment.deadline == datetime(2026, 10, 20, 21, 0)
    assert commitment.task == "finish the API"
    assert commitment.status == "proposed"


def test_non_commitment_conversation_is_ignored():
    messages = parse_chat(
        "2026-10-19 09:00 - Alice: Let's meet Sunday and figure it out\n"
        "2026-10-19 09:01 - Ben: The weather is nice today"
    )

    assert extract_commitments(messages) == []


def test_conversation_about_a_person_is_not_a_commitment():
    messages = parse_chat("2026-10-19 09:00 - Cara: Sunday meeting works for me")

    assert extract_commitments(messages) == []
