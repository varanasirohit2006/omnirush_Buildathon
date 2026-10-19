from io import BytesIO
from types import SimpleNamespace

from app import _uploaded_text, render_page


def test_empty_file_input_does_not_erase_pasted_chat():
    empty_file_input = SimpleNamespace(filename="", file=BytesIO(b""))

    assert _uploaded_text(empty_file_input) is None


def test_selected_file_is_used_as_chat_input():
    selected_file = SimpleNamespace(filename="group.txt", file=BytesIO(b"Alice: I will do the slides"))

    assert _uploaded_text(selected_file) == "Alice: I will do the slides"


def test_page_explicitly_restores_the_requested_section():
    page = render_page(None, "", "agent")

    assert 'get("section")' in page
    assert "scrollIntoView" in page
