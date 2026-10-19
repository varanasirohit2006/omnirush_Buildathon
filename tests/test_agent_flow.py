from datetime import datetime, timedelta

from project_chaser.agent import advance_clock, handle_reply, new_state, run_agent
from project_chaser.report import build_report


CHAT = "\n".join(
    [
        "2026-10-19 09:00 - Alice: I'll finish the slides by tomorrow",
        "2026-10-19 09:05 - Ben: I'll handle the API by Friday",
        "2026-10-19 09:10 - Cara: Someone should handle the demo sometime next week",
    ]
)


def test_agent_reminds_once_and_does_not_duplicate_on_repeat():
    state = new_state(CHAT)
    state.clock = datetime(2026, 10, 19, 10, 0)

    created = run_agent(state)
    assert len([event for event in created if event.kind == "reminder_sent"]) == 1
    assert len(state.outbox) == 1

    assert run_agent(state) == []
    assert len(state.outbox) == 1


def test_reply_updates_blocked_and_completion_states():
    state = new_state(CHAT)
    state.clock = datetime(2026, 10, 19, 10, 0)

    blocked = handle_reply(state, "Ben", "I am stuck on the API authentication")
    assert blocked is not None
    assert blocked.status == "blocked"
    assert state.events[-1].kind == "reply_blocked"

    done = handle_reply(state, "Alice", "Done, slides are uploaded")
    assert done is not None
    assert done.status == "done"
    assert state.events[-1].kind == "reply_done"


def test_overdue_silent_commitment_gets_one_escalation_and_report_evidence():
    state = new_state(CHAT)
    state.clock = datetime(2026, 10, 19, 10, 0)
    advance_clock(state, timedelta(days=3))

    assert any(item.purpose == "escalation" for item in state.outbox)
    first_count = len(state.outbox)
    run_agent(state)
    assert len(state.outbox) == first_count

    report = build_report(state)
    assert report["summary"]["missed"] >= 1
    assert all(item["evidence"] for item in report["commitments"])
