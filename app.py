"""Small dependency-free local web UI for Project Chaser."""

from __future__ import annotations

import cgi
import html
import os
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from project_chaser.agent import advance_clock, correct_commitment, handle_reply, new_state, run_agent
from project_chaser.demo_data import SAMPLE_CHAT
from project_chaser.models import STATUSES, AgentState
from project_chaser.report import build_report


STATE: AgentState | None = None
RAW_CHAT = SAMPLE_CHAT


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def clock_text(state: AgentState | None) -> str:
    return state.clock.strftime("%a %d %b %Y, %H:%M") if state and state.clock else "not started"


def report_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Project Chaser progress report",
        f"Generated at: {report['generated_at']}",
        "",
        f"{summary['done']} done · {summary['blocked']} blocked · {summary['missed']} missed · {summary['clarifications']} need clarification",
        "",
        "## Commitments",
    ]
    for item in report["commitments"]:
        lines.append(f"- {item['owner']} — {item['task']} — {item['status']} — due {item['deadline']} — evidence {item['evidence']}")
    return "\n".join(lines)


def _board(state: AgentState) -> str:
    if not state.commitments:
        return '<p class="notice">No commitments were extracted yet.</p>'
    cards: list[str] = []
    for item in state.commitments:
        deadline = item.deadline.strftime("%a %d %b %H:%M") if item.deadline else "Unclear"
        options = "".join(
            f'<option value="{esc(status)}" {"selected" if status == item.status else ""}>{esc(status)}</option>'
            for status in STATUSES
        )
        warning = f'<p class="warning">Clarification needed: {esc(item.clarification)}</p>' if item.clarification else ""
        cards.append(
            f"""<article class="card">
              <h3>{esc(item.owner or 'Unassigned')} · {esc(item.task)}</h3>
              <p><b>Status:</b> {esc(item.status)} &nbsp; <b>Deadline:</b> {esc(deadline)} &nbsp; <b>Confidence:</b> {esc(item.confidence_label)} ({item.confidence:.0%})</p>
              <p class="source"><b>Evidence {esc(item.source_message_id)}:</b> {esc(item.source_text)}</p>
              {warning}
              <form method="post" action="/correct" class="inline-form">
                <input type="hidden" name="commitment_id" value="{esc(item.id)}">
                <label>Owner <input name="owner" value="{esc(item.owner or '')}"></label>
                <label>Status <select name="status">{options}</select></label>
                <button>Save correction</button>
              </form>
            </article>"""
        )
    return "\n".join(cards)


def _timeline(state: AgentState) -> str:
    if not state.events:
        return '<li class="notice">No events yet. Run the agent or advance the clock.</li>'
    return "".join(
        f'<li><code>{event.timestamp:%m-%d %H:%M}</code> <b>{esc(event.kind)}</b> — {esc(event.description)} — evidence: <code>{esc(event.evidence or "policy")}</code></li>'
        for event in reversed(state.events[-20:])
    )


def _outbox(state: AgentState) -> str:
    if not state.outbox:
        return '<p class="notice">No outgoing message is ready. Run the agent or advance the clock.</p>'
    return "".join(
        f'<article class="outbox"><b>{esc(item.purpose.title())} → {esc(item.recipient)}</b> · {item.created_at:%Y-%m-%d %H:%M}<p>{esc(item.text)}</p></article>'
        for item in state.outbox
    )


def _report(state: AgentState) -> str:
    report = build_report(state)
    summary = report["summary"]
    rows = "".join(
        f'<tr><td>{esc(item["owner"])}</td><td>{esc(item["task"])}</td><td>{esc(item["status"])}</td><td>{esc(item["deadline"])}</td><td><code>{esc(item["evidence"])}</code></td></tr>'
        for item in report["commitments"]
    )
    return f"""<section id="report"><h2>Evidence-based progress report</h2>
      <div class="metrics"><span><b>{summary['total']}</b> tracked</span><span><b>{summary['done']}</b> done</span><span><b>{summary['blocked']}</b> blocked</span><span><b>{summary['missed']}</b> missed</span><span><b>{summary['clarifications']}</b> clarify</span></div>
      <table><tr><th>Owner</th><th>Task</th><th>Status</th><th>Deadline</th><th>Evidence</th></tr>{rows}</table>
      <p><b>Fairness:</b> contribution is based on tracked commitments and status evidence, not message volume or judgments about people.</p>
      <details><summary>Downloadable report text</summary><pre>{esc(report_markdown(report))}</pre></details>
    </section>"""


def _uploaded_text(field: object) -> str | None:
    """Read a selected upload without letting an empty file input erase pasted text."""

    filename = getattr(field, "filename", None)
    file_object = getattr(field, "file", None)
    if not filename or file_object is None:
        return None
    return file_object.read().decode("utf-8", errors="replace")


def render_page(state: AgentState | None, raw_chat: str, notice: str = "") -> str:
    if state:
        board = _board(state)
        open_items = [item for item in state.commitments if item.owner and item.status not in ("done", "missed")]
        reply_options = "".join(f'<option value="{esc(item.id)}">{esc(item.owner)} — {esc(item.task)}</option>' for item in open_items)
        agent_section = f"""<section id="agent"><h2>Agent loop and simulated time</h2>
          <p class="clock"><b>Demo clock:</b> {esc(clock_text(state))}</p>
          <form method="post" action="/run" class="button-row"><button class="primary">Run agent now</button></form>
          <form method="post" action="/advance" class="button-row"><button name="hours" value="6">+6 hours</button><button name="hours" value="24">+1 day</button><button name="hours" value="48">+2 days</button><button name="hours" value="72">+3 days</button></form>
          <h3>Reply handling</h3>
          <form method="post" action="/reply" class="reply-form"><select name="commitment_id">{reply_options}</select><input name="reply" placeholder="e.g. I’m stuck on the API authentication" required><button>Process reply</button></form>
          <h3>Local outbox</h3>{_outbox(state)}
          <h3>Evidence timeline</h3><ul>{_timeline(state)}</ul>
        </section>"""
        report = _report(state)
        board_section = f'''<section id="board"><h2>Commitment board</h2><div class="metrics"><span><b>{len(state.commitments)}</b> candidates</span><span><b>{sum(item.status == "accepted" for item in state.commitments)}</b> accepted</span><span><b>{sum(item.needs_clarification for item in state.commitments)}</b> clarify</span><span><b>{sum(item.status == "done" for item in state.commitments)}</b> done</span></div>{board}</section>'''
    else:
        board_section = '<section id="board"><p class="notice">Extract the demo chat or paste your own group chat to begin.</p></section>'
        agent_section = '<section id="agent"><p class="notice">The agent controls appear after extraction.</p></section>'
        report = '<section id="report"><p class="notice">The report appears after extraction.</p></section>'

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project Chaser</title>
      <style>
      :root {{ font-family: Inter, system-ui, sans-serif; background:#f7f8fc; color:#172033; }} body {{ max-width:1100px; margin:0 auto; padding:24px; }} h1 {{ margin-bottom:4px; }} h2 {{ margin-top:0; }} section {{ background:white; border:1px solid #dce1ed; border-radius:14px; padding:20px; margin:18px 0; box-shadow:0 3px 12px #1720330d; }} textarea {{ width:100%; box-sizing:border-box; min-height:220px; font:inherit; padding:12px; border:1px solid #bfc7d9; border-radius:8px; }} input, select, button {{ font:inherit; padding:9px 11px; border:1px solid #bfc7d9; border-radius:7px; }} button {{ background:#eef2ff; cursor:pointer; }} button.primary {{ background:#3659d9; color:white; border-color:#3659d9; }} .button-row {{ display:inline-flex; gap:8px; margin:4px 4px 16px 0; }} .card {{ border:1px solid #e2e6f0; border-radius:10px; padding:14px; margin:10px 0; }} .card h3 {{ margin:0 0 8px; }} .source {{ color:#536078; font-size:.92rem; }} .warning {{ background:#fff4d6; padding:10px; border-radius:7px; }} .notice {{ background:#eef2ff; padding:12px; border-radius:8px; }} .metrics {{ display:flex; flex-wrap:wrap; gap:10px; margin:10px 0 18px; }} .metrics span {{ background:#f0f3fa; padding:10px 13px; border-radius:8px; }} .metrics b {{ font-size:1.25rem; }} .inline-form, .reply-form {{ display:flex; flex-wrap:wrap; align-items:end; gap:8px; }} label {{ display:flex; flex-direction:column; gap:4px; font-size:.9rem; }} .outbox {{ border-left:4px solid #3659d9; background:#f5f7ff; padding:10px 14px; margin:8px 0; }} li {{ margin:8px 0; }} table {{ border-collapse:collapse; width:100%; }} th, td {{ text-align:left; padding:9px; border-bottom:1px solid #e2e6f0; }} code {{ background:#edf0f6; padding:2px 4px; border-radius:4px; }} .nav {{ display:flex; gap:12px; margin:16px 0; }} .nav a {{ color:#3659d9; }} </style></head><body>
      <h1>🧭 Project Chaser</h1><p>The agent that takes the social hit of following up — politely, with evidence, and without spam.</p>
      <nav class="nav"><a href="#intake">Intake</a><a href="#board">Board</a><a href="#agent">Agent loop</a><a href="#report">Report</a><a href="#honesty">Honesty sheet</a></nav>
      {f'<p class="notice">{esc(notice)}</p>' if notice else ''}
      <section id="intake"><h2>1. Give Project Chaser the group chat</h2><form method="post" action="/ingest" enctype="multipart/form-data"><textarea name="chat">{esc(raw_chat)}</textarea><p><label>Optional .txt upload <input type="file" name="upload" accept=".txt"></label></p><button class="primary">Extract commitments</button></form><form method="post" action="/reset" class="button-row"><button>Reset demo chat</button></form><p><small>Privacy: this prototype keeps the supplied chat on this machine. Outgoing messages are simulated locally.</small></p></section>
      {board_section}{agent_section}{report}
      <section id="honesty"><h2>Honesty sheet</h2><h3>Real</h3><ul><li>Chat parsing, conservative commitment extraction, confidence, and clarification.</li><li>Board corrections, evidence events, time simulation, bounded nudges, reply handling, and report generation.</li></ul><h3>Simulated</h3><ul><li>The local outbox shows what a Telegram or email adapter would send; it does not deliver messages.</li><li>The fast-forward clock stands in for real elapsed time.</li><li>The extractor uses explainable rules and a small slang/Hinglish vocabulary rather than a hosted model.</li></ul><h3>Privacy guardrails</h3><ul><li>No hidden monitoring or private one-to-one chat access.</li><li>No guessed owner or deadline.</li><li>Quiet hours, two reminder maximum, and one overdue escalation.</li></ul></section>
      <script>const target=new URLSearchParams(window.location.search).get("section"); if(target){{window.addEventListener("load",()=>{{const element=document.getElementById(target); if(element){{element.scrollIntoView({{block:"start",behavior:"instant"}});}}}});}}</script>
      </body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _redirect(self, notice: str, anchor: str = "intake") -> None:
        self.send_response(303)
        self.send_header("Location", "/?notice=" + quote(notice) + f"&section={anchor}#{anchor}")
        self.end_headers()

    def _body(self) -> dict[str, str]:
        content_type = self.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type})
            values: dict[str, str] = {}
            for key in ("chat", "owner", "status", "commitment_id", "reply", "hours"):
                if key in form:
                    field = form[key]
                    values[key] = field.value if hasattr(field, "value") else str(field)
            if "upload" in form:
                uploaded_text = _uploaded_text(form["upload"])
                if uploaded_text is not None:
                    values["chat"] = uploaded_text
            return values
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return {key: values[0] for key, values in parse_qs(raw).items()}

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        body = render_page(STATE, RAW_CHAT, query.get("notice", [""])[0])
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        global STATE, RAW_CHAT
        data = self._body()
        path = urlparse(self.path).path
        if path == "/ingest":
            RAW_CHAT = data.get("chat", "")
            STATE = new_state(RAW_CHAT)
            notice = f"Read {len(STATE.messages)} messages and found {len(STATE.commitments)} commitment candidates."
            anchor = "board"
        elif path == "/reset":
            RAW_CHAT = SAMPLE_CHAT
            STATE = new_state(RAW_CHAT)
            notice = "Demo chat reset."
            anchor = "intake"
        elif STATE is None:
            notice = "Extract a chat first."
            anchor = "intake"
        elif path == "/run":
            notice = f"Agent created {len(run_agent(STATE))} new event(s)."
            anchor = "agent"
        elif path == "/advance":
            notice = f"Clock advanced. Agent created {len(advance_clock(STATE, timedelta(hours=int(data.get('hours', '24')))))} new event(s)."
            anchor = "agent"
        elif path == "/reply":
            item = next((candidate for candidate in STATE.commitments if candidate.id == data.get("commitment_id")), None)
            changed = handle_reply(STATE, item.owner, data.get("reply", "")) if item and item.owner else None
            notice = f"Updated {changed.owner}'s commitment to {changed.status}." if changed else "No matching open commitment found."
            anchor = "agent"
        elif path == "/correct":
            changed = correct_commitment(STATE, data.get("commitment_id", ""), owner=data.get("owner"), status=data.get("status"))
            notice = "Correction recorded with evidence." if changed else "Commitment not found."
            anchor = "board"
        else:
            notice = "Unknown action."
            anchor = "intake"
        self._redirect(notice, anchor)


def main() -> None:
    port = int(os.environ.get("PORT", "8501"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Project Chaser running at http://localhost:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
