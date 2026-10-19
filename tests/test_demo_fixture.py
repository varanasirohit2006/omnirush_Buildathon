from project_chaser.chat import parse_chat
from project_chaser.demo_data import SAMPLE_CHAT
from project_chaser.extractor import extract_commitments


def test_demo_fixture_is_large_enough_and_contains_the_required_cases():
    messages = parse_chat(SAMPLE_CHAT)
    commitments = extract_commitments(messages)

    assert len(messages) == 40
    assert len(commitments) >= 7
    assert any(item.owner is None for item in commitments)
    assert any(item.commitment_strength == "tentative" for item in commitments)
    assert all(item.source_message_id for item in commitments)
