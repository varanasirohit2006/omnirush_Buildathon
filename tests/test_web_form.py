from io import BytesIO
from types import SimpleNamespace

from app import _uploaded_text, render_page, report_csv


def test_empty_file_input_does_not_erase_pasted_chat():
    empty_file_input = SimpleNamespace(filename="", file=BytesIO(b""))

    assert _uploaded_text(empty_file_input) is None


def test_selected_file_is_used_as_chat_input():
    selected_file = SimpleNamespace(filename="group.txt", file=BytesIO(b"Alice: I will do the slides"))

    assert _uploaded_text(selected_file) == "Alice: I will do the slides"


def test_page_uses_focused_workflow_views_instead_of_one_long_page():
    intake = render_page(None, "", "", "intake")
    commitments = render_page(None, "", "", "commitments")

    assert "Stop chasing" in intake
    assert 'href="/?view=commitments"' in intake
    assert 'action="/reset"' in intake
    assert "loadChatFile" in intake
    assert 'id="chat-input"' in intake
    assert "Your board is waiting" in commitments
    assert 'href="/?view=intake"' in commitments


def test_loaded_workspace_renders_compact_board_and_chase_navigation():
    from project_chaser.agent import new_state

    state = new_state("2026-10-19 09:00 - Alice: I will do the slides by Friday")
    page = render_page(state, "", "", "commitments")

    assert "Commitment board" in page
    assert "Go to chase controls" in page
    assert "OWNER" in page
    assert "commitment-detail" in page


def test_report_download_route_is_linked_from_report_view():
    from project_chaser.agent import new_state

    state = new_state("2026-10-19 09:00 - Alice: I will do the slides by Friday")
    page = render_page(state, "", "", "report")

    assert "Evidence-based report" in page
    assert 'href="/report.txt"' in page
    assert 'href="/report.csv"' in page


def test_report_csv_contains_commitment_evidence():
    from project_chaser.agent import new_state
    from project_chaser.report import build_report

    state = new_state("2026-10-19 09:00 - Alice: I will do the slides by Friday")

    exported = report_csv(build_report(state))

    assert "Owner,Task,Status,Deadline,Evidence,AI review" in exported
    assert "Alice" in exported
    assert "m001" in exported
