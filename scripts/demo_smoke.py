"""Run the complete offline product loop without opening a browser."""

from __future__ import annotations

from datetime import timedelta

from project_chaser.agent import advance_clock, handle_reply, new_state, run_agent
from project_chaser.demo_data import SAMPLE_CHAT
from project_chaser.report import build_report


def main() -> None:
    state = new_state(SAMPLE_CHAT)
    assert len(state.messages) == 40, "demo fixture should contain 40 messages"
    assert state.commitments, "demo fixture should produce commitments"

    initial_events = run_agent(state)
    assert any(event.kind == "reminder_sent" for event in initial_events), "initial risk check should create a reminder"

    blocked = handle_reply(state, "Dev", "I am stuck on the API authentication")
    assert blocked is not None and blocked.status == "blocked", "reply should mark Dev blocked"

    advance_clock(state, timedelta(days=3))
    report = build_report(state)
    assert any(item.purpose == "escalation" for item in state.outbox), "silent overdue work should escalate"
    assert report["summary"]["blocked"] >= 1, "report should include the blocker"
    assert report["summary"]["missed"] >= 1, "report should include missed work"
    assert all(item["evidence"] for item in report["commitments"]), "report rows need evidence"

    print("Project Chaser demo check passed")
    print(f"  messages after reply: {len(state.messages)} (40 chat messages + 1 reply)")
    print(f"  commitments: {len(state.commitments)}")
    print(f"  outbox messages: {len(state.outbox)}")
    print(f"  report summary: {report['summary']}")


if __name__ == "__main__":
    main()
