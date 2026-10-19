from datetime import timedelta

from project_chaser.agent import advance_clock, handle_reply, new_state, run_agent
from project_chaser.demo_data import SAMPLE_CHAT
from project_chaser.report import build_report


def test_real_demo_fixture_completes_the_product_loop():
    state = new_state(SAMPLE_CHAT)

    initial_events = run_agent(state)
    assert len(state.messages) == 40
    assert any(event.kind == "reminder_sent" for event in initial_events)

    blocked = handle_reply(state, "Dev", "I am stuck on the API authentication")
    assert blocked is not None
    assert blocked.status == "blocked"

    advance_clock(state, timedelta(days=3))
    report = build_report(state)

    assert any(item.purpose == "escalation" for item in state.outbox)
    assert report["summary"]["blocked"] >= 1
    assert report["summary"]["missed"] >= 1
    assert all(item["evidence"] for item in report["commitments"])
