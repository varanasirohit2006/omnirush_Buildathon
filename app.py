"""Polished dependency-free local web UI for Project Chaser."""

from __future__ import annotations

import cgi
import html
import os
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from project_chaser.agent import advance_clock, correct_commitment, handle_reply, new_state, run_agent
from project_chaser.demo_data import SAMPLE_CHAT
from project_chaser.llm import OpenAICompatibleReviewer
from project_chaser.models import STATUSES, AgentState, Commitment
from project_chaser.report import build_report


STATE: AgentState | None = None
RAW_CHAT = SAMPLE_CHAT
VIEWS = ("intake", "commitments", "chase", "report", "honesty")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def clock_text(state: AgentState | None) -> str:
    return state.clock.strftime("%A, %d %b %Y · %H:%M") if state and state.clock else "not started"


def status_class(status: str) -> str:
    return {
        "accepted": "blue",
        "proposed": "yellow",
        "in progress": "blue",
        "blocked": "orange",
        "done": "green",
        "missed": "red",
    }.get(status, "gray")


def nav_link(view: str, label: str, active: str) -> str:
    selected = " active" if view == active else ""
    return f'<a class="nav-link{selected}" href="/?view={view}">{label}</a>'


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
        ai_note = (
            f" — AI review: {item['ai_review']} ({item['ai_review_confidence']:.0%}) — {item['ai_review_reason']}"
            if item["ai_review"]
            else ""
        )
        lines.append(
            f"- {item['owner']} — {item['task']} — {item['status']} — due {item['deadline']} — evidence {item['evidence']}{ai_note}"
        )
    return "\n".join(lines)


def _uploaded_text(field: object) -> str | None:
    """Read a selected upload without letting an empty file input erase pasted text."""

    filename = getattr(field, "filename", None)
    file_object = getattr(field, "file", None)
    if not filename or file_object is None:
        return None
    return file_object.read().decode("utf-8", errors="replace")


def _metrics(state: AgentState) -> str:
    items = state.commitments
    values = (
        ("Tracked", len(items), "neutral"),
        ("Accepted", sum(item.status == "accepted" for item in items), "blue"),
        ("Clarify", sum(item.needs_clarification for item in items), "yellow"),
        ("Blocked", sum(item.status == "blocked" for item in items), "orange"),
        ("Done", sum(item.status == "done" for item in items), "green"),
    )
    return "".join(
        f'<div class="metric metric-{tone}"><span>{label}</span><strong>{value}</strong></div>'
        for label, value, tone in values
    )


def _ai_banner(state: AgentState) -> str:
    ai_status = esc(state.ai_review_status)
    if state.ai_review_error:
        ai_status += f" · {esc(state.ai_review_error)}"
    if state.ai_review_status.startswith("applied"):
        return f'<div class="ai-banner success"><span class="ai-icon">✦</span><div><strong>AI review is active</strong><p>{ai_status}. High-confidence commitments stayed on the local path.</p></div></div>'
    if state.ai_review_status.startswith("fallback"):
        return f'<div class="ai-banner warning"><span class="ai-icon">!</span><div><strong>AI review fell back safely</strong><p>{ai_status}. Deterministic extraction was kept.</p></div></div>'
    if state.ai_review_status == "not configured":
        return '<div class="ai-banner neutral"><span class="ai-icon">◇</span><div><strong>Local extraction mode</strong><p>AI review is not configured. The deterministic extractor is active.</p></div></div>'
    return f'<div class="ai-banner neutral"><span class="ai-icon">◇</span><div><strong>AI review</strong><p>{ai_status}</p></div></div>'


def _commitment_detail(item: Commitment) -> str:
    deadline = item.deadline.strftime("%a %d %b %H:%M") if item.deadline else "Unclear"
    options = "".join(
        f'<option value="{esc(status)}" {"selected" if status == item.status else ""}>{esc(status)}</option>'
        for status in STATUSES
    )
    ai_review = (
        f'<div class="ai-review"><span>✦</span><div><strong>AI review: {esc(item.review_decision)}</strong><p>{item.review_confidence:.0%} confidence · {esc(item.review_reason or "No reason supplied")}</p></div></div>'
        if item.review_decision
        else ""
    )
    clarification = f'<div class="callout warning"><strong>Clarification needed</strong><p>{esc(item.clarification)}</p></div>' if item.clarification else ""
    return f"""<details class="commitment-detail">
      <summary><span class="summary-owner">{esc(item.owner or 'Unassigned')}</span><span class="summary-task">{esc(item.task)}</span><span class="summary-deadline">{esc(deadline)}</span><span class="pill {status_class(item.status)}">{esc(item.status)}</span><span class="confidence">{item.confidence:.0%}</span></summary>
      <div class="detail-body">
        <div class="detail-grid"><div><small>Source evidence</small><p class="source">{esc(item.source_text)}</p><code>{esc(item.source_message_id)}</code></div><div><small>Commitment confidence</small><p><strong>{esc(item.confidence_label)}</strong> · {item.confidence:.0%}</p><small>Strength: {esc(item.commitment_strength)}</small></div></div>
        {ai_review}{clarification}
        <form method="post" action="/correct" class="inline-form"><input type="hidden" name="commitment_id" value="{esc(item.id)}"><label>Owner<input name="owner" value="{esc(item.owner or '')}"></label><label>Status<select name="status">{options}</select></label><button class="button small">Save correction</button></form>
      </div>
    </details>"""


def _commitment_board(state: AgentState) -> str:
    if not state.commitments:
        return '<div class="empty"><div class="empty-icon">◎</div><h3>No commitments yet</h3><p>Extract a group chat to build the board.</p></div>'
    header = '<div class="commitment-header"><span>OWNER</span><span>TASK</span><span>DEADLINE</span><span>STATUS</span><span>CONF.</span></div>'
    rows = "".join(_commitment_detail(item) for item in state.commitments)
    ignored = ""
    if state.ignored_candidates:
        ignored_rows = "".join(
            f'<li><span class="pill gray">ignored</span> {esc(item.owner or "Unassigned")} · {esc(item.task)}<small>{esc(item.review_reason or "AI classified this as non-actionable")}</small></li>'
            for item in state.ignored_candidates
        )
        ignored = f'<details class="ignored"><summary>Show {len(state.ignored_candidates)} AI-filtered conversation item(s)</summary><ul>{ignored_rows}</ul></details>'
    return header + rows + ignored


def _outbox(state: AgentState) -> str:
    if not state.outbox:
        return '<div class="empty compact"><div class="empty-icon">↗</div><strong>Outbox is quiet</strong><p>Run the agent or move the demo clock to create a controlled message.</p></div>'
    return "".join(
        f'<article class="outbox"><div class="outbox-top"><span class="pill {"red" if item.purpose == "escalation" else "blue"}">{esc(item.purpose)}</span><strong>→ {esc(item.recipient)}</strong><small>{item.created_at:%d %b · %H:%M}</small></div><p>{esc(item.text)}</p><small class="simulated">SIMULATED DELIVERY · local outbox</small></article>'
        for item in reversed(state.outbox)
    )


def _timeline(state: AgentState) -> str:
    if not state.events:
        return '<div class="empty compact"><strong>No events yet</strong><p>Agent decisions will appear here with evidence.</p></div>'
    return "".join(
        f'<li><span class="timeline-dot"></span><div><small>{event.timestamp:%d %b · %H:%M}</small><strong>{esc(event.kind.replace("_", " "))}</strong><p>{esc(event.description)}</p><code>{esc(event.evidence or "policy")}</code></div></li>'
        for event in reversed(state.events[-12:])
    )


def _report_content(state: AgentState) -> str:
    report = build_report(state)
    summary = report["summary"]
    rows = "".join(
        f'<tr><td><strong>{esc(item["owner"])}</strong></td><td>{esc(item["task"])}</td><td>{esc(item["deadline"])}</td><td><span class="pill {status_class(item["status"])}">{esc(item["status"])}</span></td><td>{esc(item["ai_review"] or "local")}</td><td><code>{esc(item["evidence"])}</code></td></tr>'
        for item in report["commitments"]
    )
    risks = "".join(
        f'<li><span class="pill {"orange" if risk["reason"] == "blocked" else "red"}">{esc(risk["reason"])}</span><strong>{esc(risk["owner"])}</strong> · {esc(risk["task"])} <code>{esc(risk["evidence"])}</code></li>'
        for risk in report["risks"]
    ) or '<li class="muted">No active risks.</li>'
    return f"""<div class="page-heading"><div><p class="eyebrow">PROJECT STATUS</p><h2>Evidence-based report</h2><p class="subheading">A fair summary built from commitments, replies, and recorded events.</p></div><a class="button primary" href="/report.txt">↓ Download report</a></div>
      <div class="metrics report-metrics"><div class="metric metric-neutral"><span>Tracked</span><strong>{summary['total']}</strong></div><div class="metric metric-green"><span>Done</span><strong>{summary['done']}</strong></div><div class="metric metric-orange"><span>Blocked</span><strong>{summary['blocked']}</strong></div><div class="metric metric-red"><span>Missed</span><strong>{summary['missed']}</strong></div><div class="metric metric-yellow"><span>Clarify</span><strong>{summary['clarifications']}</strong></div><div class="metric metric-blue"><span>AI reviewed</span><strong>{summary['ai_reviewed']}</strong></div></div>
      <div class="report-grid"><section class="panel"><div class="panel-heading"><div><p class="eyebrow">DELIVERY RECORD</p><h3>All tracked commitments</h3></div><span class="muted">Generated {esc(str(report['generated_at']))}</span></div><div class="table-wrap"><table><thead><tr><th>OWNER</th><th>TASK</th><th>DEADLINE</th><th>STATUS</th><th>REVIEW</th><th>EVIDENCE</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class="panel risk-panel"><div class="panel-heading"><div><p class="eyebrow">ATTENTION</p><h3>Risks & blockers</h3></div></div><ul class="risk-list">{risks}</ul><div class="fairness"><strong>Fairness guardrail</strong><p>Contribution is based on tracked commitments and status evidence, not message volume or guesses about people.</p></div></section></div>"""


def _intake_view(state: AgentState | None, raw_chat: str) -> str:
    loaded = f'<div class="loaded-note"><span class="status-dot green-dot"></span><span>Current workspace: {len(state.messages)} messages · {len(state.commitments)} candidates</span><a href="/?view=commitments">Open board →</a></div>' if state else ""
    return f"""<div class="hero"><div class="hero-copy"><p class="eyebrow">AUTOMATED FOLLOW-UP FOR GROUP PROJECTS</p><h2>Stop chasing.<br><span>Start finishing.</span></h2><p class="hero-lede">Project Chaser turns messy group-chat promises into clear commitments, polite nudges, and a fair progress report.</p><div class="hero-proof"><span>✦ AI-assisted review</span><span>◉ Evidence on every claim</span><span>↗ Offline-first demo</span></div></div><div class="hero-art"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="hero-mark">✦</div><div class="hero-float float-one">✓ <span>Reminder sent</span></div><div class="hero-float float-two">◌ <span>Blocked surfaced</span></div></div></div>
      {loaded}<section class="panel intake-panel"><div class="panel-heading"><div><p class="eyebrow">STEP 01 · INTAKE</p><h3>Give Project Chaser the group chat</h3><p class="muted">Paste a chat export or upload a WhatsApp-style .txt file. Your data stays on this machine.</p></div><span class="privacy-badge">⌂ LOCAL ONLY</span></div><form method="post" action="/ingest" enctype="multipart/form-data"><textarea name="chat" class="chat-input" placeholder="Paste your group chat here…">{esc(raw_chat)}</textarea><div class="intake-actions"><label class="upload-button">＋ Upload .txt<input type="file" name="upload" accept=".txt"></label><span class="file-hint">or use the demo fixture already loaded</span><button class="button secondary" type="button" onclick="document.querySelector('textarea[name=chat]').value='';">Clear</button><button class="button primary large" type="submit">Extract commitments <span>→</span></button></div></form><form method="post" action="/reset" class="reset-form"><button class="button secondary small" type="submit">↺ Reset demo chat</button></form></section><section class="three-up"><div class="mini-card"><span class="mini-icon purple">✦</span><div><strong>Extract, don’t guess</strong><p>Clear promises are tracked. Ambiguous ones become questions.</p></div></div><div class="mini-card"><span class="mini-icon blue">◷</span><div><strong>Nudge with limits</strong><p>Quiet hours, two reminders, one escalation.</p></div></div><div class="mini-card"><span class="mini-icon green">✓</span><div><strong>Report with proof</strong><p>Every outcome links back to a message or event.</p></div></div></section>"""


def _commitments_view(state: AgentState | None) -> str:
    if state is None:
        return '<div class="empty-page"><div class="empty-icon large-icon">◎</div><h2>Your board is waiting</h2><p>Start by giving Project Chaser a group chat.</p><a class="button primary" href="/?view=intake">Go to intake →</a></div>'
    return f"""<div class="page-heading"><div><p class="eyebrow">STEP 02 · REVIEW</p><h2>Commitment board</h2><p class="subheading">Review what was promised before the agent follows up.</p></div><a class="button secondary" href="/?view=chase">Go to chase controls →</a></div>{_ai_banner(state)}<div class="metrics">{_metrics(state)}</div><section class="panel board-panel"><div class="panel-heading"><div><h3>{len(state.commitments)} candidate commitments</h3><p class="muted">Expand a row to inspect evidence or correct an owner/status.</p></div><span class="legend"><span class="pill blue">accepted</span><span class="pill yellow">proposed</span><span class="pill gray">clarify</span></span></div>{_commitment_board(state)}</section>"""


def _chase_view(state: AgentState | None) -> str:
    if state is None:
        return '<div class="empty-page"><div class="empty-icon large-icon">↗</div><h2>Nothing to chase yet</h2><p>Extract commitments first, then come back here to run the agent.</p><a class="button primary" href="/?view=intake">Go to intake →</a></div>'
    open_items = [item for item in state.commitments if item.owner and item.status not in ("done", "missed")]
    reply_options = "".join(f'<option value="{esc(item.id)}">{esc(item.owner)} · {esc(item.task)}</option>' for item in open_items) or '<option>No open assigned work</option>'
    return f"""<div class="page-heading"><div><p class="eyebrow">STEP 03 · FOLLOW-UP</p><h2>Chase controls</h2><p class="subheading">Let the agent handle the social hit—politely, with limits.</p></div><div class="clock-badge"><span class="status-dot"></span><div><small>DEMO CLOCK</small><strong>{esc(clock_text(state))}</strong></div></div></div><div class="chase-layout"><section class="panel control-panel"><p class="eyebrow">SIMULATE TIME</p><h3>Move the project forward</h3><p class="muted">Fast-forward to show reminders and escalation without waiting.</p><form method="post" action="/run"><button class="button primary full" type="submit">✦ Run agent now</button></form><div class="time-grid"><form method="post" action="/advance"><button name="hours" value="6" class="button secondary full">+6 hours</button></form><form method="post" action="/advance"><button name="hours" value="24" class="button secondary full">+1 day</button></form><form method="post" action="/advance"><button name="hours" value="48" class="button secondary full">+2 days</button></form><form method="post" action="/advance"><button name="hours" value="72" class="button secondary full">+3 days</button></form></div><div class="policy"><strong>Agent guardrails</strong><span>Quiet hours 21:00–08:00</span><span>Maximum two nudges</span><span>One overdue escalation</span></div></section><section class="panel reply-panel"><p class="eyebrow">REPLY HANDLING</p><h3>What did the teammate say?</h3><p class="muted">Replies update the right commitment and become evidence.</p><form method="post" action="/reply" class="reply-form"><label>Commitment<select name="commitment_id">{reply_options}</select></label><label>Incoming reply<input name="reply" placeholder="e.g. I’m stuck on the API authentication" required></label><button class="button secondary" type="submit">Process reply →</button></form></section></div><div class="chase-columns"><section class="panel"><div class="panel-heading"><div><p class="eyebrow">OUTBOX</p><h3>Messages ready to send</h3></div><span class="simulated-badge">SIMULATED</span></div>{_outbox(state)}</section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">AUDIT TRAIL</p><h3>Recent decisions</h3></div></div><ul class="timeline">{_timeline(state)}</ul></section></div>"""


def _honesty_view() -> str:
    return """<div class="page-heading"><div><p class="eyebrow">ABOUT THE PROTOTYPE</p><h2>Honest by design</h2><p class="subheading">What Project Chaser does, what it simulates, and how it stays fair.</p></div></div><div class="honesty-grid"><section class="panel"><span class="honesty-icon green">✓</span><h3>Real in this prototype</h3><ul class="clean-list"><li>Chat parsing and conservative commitment extraction.</li><li>Optional Gemini review for low-confidence candidates.</li><li>Evidence-linked board corrections and status events.</li><li>Simulated time, bounded reminders, replies, and reports.</li></ul></section><section class="panel"><span class="honesty-icon yellow">◌</span><h3>Simulated for the demo</h3><ul class="clean-list"><li>The outbox shows messages but does not deliver them.</li><li>Fast-forwarding replaces real elapsed time.</li><li>The current state lives in the running process.</li><li>The language rules cover a focused demo vocabulary.</li></ul></section><section class="panel"><span class="honesty-icon purple">⌂</span><h3>Privacy & fairness</h3><ul class="clean-list"><li>No hidden monitoring or private one-to-one chats.</li><li>No guessed owner or deadline.</li><li>No message-count ranking or judgments about effort.</li><li>AI failure falls back to deterministic extraction.</li></ul></section></div>"""


STYLE = """
:root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #20233a; background: #f7f7fb; line-height: 1.45; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: radial-gradient(circle at 85% 0%, #ede9ff 0, #f7f7fb 32rem); }
a { color: inherit; text-decoration: none; }
button, input, select, textarea { font: inherit; }
.shell { max-width: 1280px; margin: 0 auto; padding: 0 28px 48px; }
.topbar { height: 76px; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.brand { display: flex; align-items: center; gap: 11px; font-weight: 800; letter-spacing: -.03em; font-size: 1.15rem; }
.brand-mark { display: grid; place-items: center; width: 35px; height: 35px; border-radius: 11px; color: #fff; background: linear-gradient(135deg, #7258e8, #a486ff); box-shadow: 0 8px 18px #765cf34d; }
.nav { display: flex; align-items: center; gap: 5px; background: #fff8; border: 1px solid #e9e7f3; padding: 5px; border-radius: 13px; }
.nav-link { padding: 9px 14px; border-radius: 9px; font-size: .86rem; color: #74758b; }
.nav-link:hover, .nav-link.active { color: #28233d; background: #f0edff; font-weight: 700; }
.top-status { display: flex; align-items: center; gap: 8px; color: #76768a; font-size: .78rem; white-space: nowrap; }
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #916dff; box-shadow: 0 0 0 4px #916dff1c; }
.green-dot { background: #35b879; box-shadow: 0 0 0 4px #35b8791c; }
.purple-dot { background: #916dff; }
.toast { position: fixed; z-index: 10; top: 86px; right: 28px; max-width: 420px; background: #25243a; color: #fff; border-radius: 12px; padding: 13px 16px; box-shadow: 0 15px 35px #27223a33; font-size: .88rem; }
.toast button { border: 0; color: #fff; background: none; float: right; margin-left: 16px; cursor: pointer; font-size: 1.1rem; }
.hero { display: grid; grid-template-columns: 1.2fr .8fr; min-height: 330px; align-items: center; padding: 48px 50px; margin: 16px 0 24px; border-radius: 26px; overflow: hidden; color: #fff; background: linear-gradient(120deg, #2f2849, #5c438e 60%, #8463cc); box-shadow: 0 20px 45px #493a7650; }
.eyebrow { margin: 0 0 8px; color: #8b72ed; font-size: .68rem; font-weight: 800; letter-spacing: .14em; }
.hero .eyebrow { color: #c6b8ff; }
h2 { margin: 0; color: #29243c; font-size: 2.35rem; line-height: 1.08; letter-spacing: -.055em; }
.hero h2 { color: #fff; font-size: 3.3rem; }
.hero h2 span { color: #cbbdff; }
h3 { margin: 0; font-size: 1.08rem; letter-spacing: -.02em; }
.hero-lede { max-width: 550px; margin: 18px 0; color: #ddd5f2; font-size: 1.02rem; }
.hero-proof { display: flex; flex-wrap: wrap; gap: 10px; color: #eee9ff; font-size: .76rem; }
.hero-proof span { padding: 7px 10px; background: #ffffff15; border: 1px solid #ffffff22; border-radius: 20px; }
.hero-art { position: relative; height: 250px; }
.hero-mark { position: absolute; top: 70px; left: 50%; transform: translateX(-50%); display: grid; place-items: center; width: 112px; height: 112px; border: 1px solid #ffffff55; border-radius: 36px; color: #fff; background: #ffffff1c; font-size: 4rem; box-shadow: 0 0 60px #d7c9ff5c; }
.orbit { position: absolute; top: 30px; left: 50%; border: 1px solid #ffffff32; border-radius: 50%; transform: translateX(-50%) rotate(-24deg); }
.orbit-one { width: 260px; height: 120px; }
.orbit-two { width: 230px; height: 210px; transform: translateX(-50%) rotate(52deg); }
.hero-float { position: absolute; padding: 10px 13px; color: #322a51; background: #fff; border-radius: 10px; box-shadow: 0 12px 22px #24163c33; font-size: .74rem; }
.hero-float span { margin-left: 5px; color: #68657b; }
.float-one { top: 35px; right: 0; }
.float-two { bottom: 22px; left: 0; }
.panel { padding: 25px; background: #fff; border: 1px solid #eae8f1; border-radius: 17px; box-shadow: 0 7px 24px #35304a08; }
.panel-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 18px; margin-bottom: 18px; }
.panel-heading p { margin: 5px 0 0; }
.muted { color: #868699; font-size: .84rem; }
.privacy-badge, .simulated-badge { padding: 6px 9px; border: 1px solid #e6e2f4; border-radius: 7px; color: #7762cf; background: #f7f5ff; font-size: .65rem; font-weight: 800; letter-spacing: .08em; white-space: nowrap; }
.intake-panel { margin-bottom: 18px; }
.chat-input { width: 100%; min-height: 205px; resize: vertical; border: 1px solid #e3e1ec; border-radius: 12px; padding: 15px; color: #45445b; background: #fbfbfd; outline: none; }
.chat-input:focus, input:focus, select:focus { border-color: #967ce9; box-shadow: 0 0 0 3px #967ce91c; outline: none; }
.intake-actions { display: flex; align-items: center; gap: 12px; margin-top: 14px; }
.button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid transparent; border-radius: 9px; padding: 10px 15px; cursor: pointer; font-weight: 700; font-size: .84rem; }
.button.primary { color: #fff; background: #765be3; box-shadow: 0 7px 16px #765be333; }
.button.primary:hover { background: #6649d7; }
.button.secondary { color: #51437c; border-color: #ddd7f4; background: #faf9ff; }
.button.secondary:hover { background: #f0edff; }
.button.small { padding: 8px 11px; font-size: .75rem; }
.button.large { margin-left: auto; padding: 12px 18px; }
.button.full { width: 100%; }
.upload-button { display: inline-flex; align-items: center; gap: 5px; padding: 10px 12px; border: 1px solid #ddd7f4; border-radius: 9px; color: #5d4b9d; background: #faf9ff; cursor: pointer; font-weight: 700; font-size: .8rem; }
.upload-button input { display: none; }
.file-hint { color: #9998a8; font-size: .75rem; }
.three-up, .honesty-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.mini-card { display: flex; gap: 12px; padding: 16px; border: 1px solid #eae8f1; border-radius: 14px; background: #fff; }
.mini-card p { margin: 5px 0 0; color: #8a8998; font-size: .78rem; }
.mini-icon, .honesty-icon { display: grid; place-items: center; flex: none; width: 32px; height: 32px; border-radius: 10px; font-weight: 800; }
.mini-icon.purple, .honesty-icon.purple { color: #735be0; background: #eeeaff; }
.mini-icon.blue { color: #3182d0; background: #e6f2ff; }
.mini-icon.green, .honesty-icon.green { color: #269e68; background: #e4f8ed; }
.honesty-icon.yellow { color: #bc7d22; background: #fff1d8; }
.loaded-note { display: flex; align-items: center; gap: 9px; padding: 11px 14px; margin: 0 0 18px; border: 1px solid #d8f0e3; border-radius: 10px; color: #51846d; background: #f2fbf6; font-size: .82rem; }
.loaded-note a { margin-left: auto; color: #6c50dc; font-weight: 700; }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin: 40px 0 24px; }
.subheading { margin: 8px 0 0; color: #868699; font-size: .91rem; }
.metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 18px; }
.metric { padding: 15px 17px; border: 1px solid #eae8f1; border-radius: 13px; background: #fff; }
.metric span { display: block; color: #888798; font-size: .72rem; font-weight: 700; }
.metric strong { display: block; margin-top: 4px; color: #2e2b43; font-size: 1.55rem; letter-spacing: -.05em; }
.metric-blue { border-color: #dcecff; background: #f6faff; }
.metric-green { border-color: #d8f1e3; background: #f6fcf8; }
.metric-orange { border-color: #f9e5cc; background: #fffaf4; }
.metric-red { border-color: #f6d9dc; background: #fff8f8; }
.metric-yellow { border-color: #f4eacb; background: #fffdf5; }
.ai-banner { display: flex; gap: 12px; align-items: flex-start; padding: 15px 17px; margin-bottom: 18px; border-radius: 13px; }
.ai-banner.success { border: 1px solid #cdebd9; color: #347a59; background: #f1fbf5; }
.ai-banner.warning { border: 1px solid #f1d6b6; color: #9b6527; background: #fff9f0; }
.ai-banner.neutral { border: 1px solid #e2dff0; color: #6c6484; background: #faf9ff; }
.ai-banner p { margin: 3px 0 0; font-size: .78rem; }
.ai-icon { display: grid; place-items: center; width: 25px; height: 25px; border-radius: 8px; background: #ffffffb5; font-weight: 800; }
.board-panel { overflow: hidden; }
.legend { display: flex; gap: 5px; flex-wrap: wrap; justify-content: flex-end; }
.commitment-header, .commitment-detail summary { display: grid; grid-template-columns: 1.05fr 2.2fr 1.25fr 1fr .55fr; align-items: center; gap: 12px; }
.commitment-header { padding: 0 15px 9px; color: #aaa9b5; font-size: .63rem; font-weight: 800; letter-spacing: .1em; }
.commitment-detail { border-top: 1px solid #f0eef5; }
.commitment-detail summary { padding: 14px 15px; cursor: pointer; list-style: none; font-size: .83rem; }
.commitment-detail summary::-webkit-details-marker { display: none; }
.commitment-detail summary:hover { background: #fbfaff; }
.summary-owner { font-weight: 750; color: #443968; }
.summary-task { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #4f4e61; }
.summary-deadline { color: #858494; font-size: .77rem; }
.confidence { color: #8b899c; font-size: .75rem; }
.pill { display: inline-flex; width: max-content; padding: 4px 8px; border-radius: 99px; font-size: .65rem; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }
.pill.blue { color: #376fb0; background: #e8f2ff; }
.pill.yellow { color: #a9751f; background: #fff1cd; }
.pill.orange { color: #af6826; background: #ffead8; }
.pill.green { color: #25865d; background: #ddf6e8; }
.pill.red { color: #b24d5a; background: #ffe3e5; }
.pill.gray { color: #777586; background: #eeedf2; }
.detail-body { padding: 4px 15px 18px; background: #fcfbfe; }
.detail-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; padding: 10px 0; }
.detail-grid p { margin: 5px 0; }
.detail-grid small, .commitment-detail small { color: #9897a6; font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.source { color: #696879; font-size: .8rem; }
code { color: #77708b; background: #f0eef5; padding: 3px 5px; border-radius: 5px; font-size: .7rem; }
.ai-review { display: flex; gap: 9px; margin: 10px 0; padding: 10px; border-left: 3px solid #8065e6; border-radius: 7px; color: #5b4ba2; background: #f4f1ff; font-size: .78rem; }
.ai-review span { font-size: 1rem; }
.ai-review p { margin: 2px 0 0; color: #7b72a0; }
.callout { padding: 10px; margin: 10px 0; border-radius: 8px; font-size: .78rem; }
.callout p { margin: 3px 0 0; }
.callout.warning { color: #986b2d; background: #fff6df; }
.inline-form { display: flex; align-items: end; gap: 10px; flex-wrap: wrap; }
label { display: flex; flex-direction: column; gap: 5px; color: #888798; font-size: .7rem; font-weight: 700; }
input, select { padding: 9px 10px; border: 1px solid #e3e1ec; border-radius: 8px; color: #4a485d; background: #fff; outline: none; }
.ignored { margin-top: 14px; color: #777586; font-size: .78rem; }
.ignored summary { cursor: pointer; font-weight: 700; }
.ignored ul { padding-left: 20px; }
.ignored li { margin: 8px 0; }
.ignored small { display: block; margin-left: 5px; color: #aaa9b5; }
.chase-layout, .chase-columns, .report-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chase-columns { margin-top: 16px; }
.control-panel { background: linear-gradient(145deg, #fbfaff, #fff); }
.time-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0; }
.policy { display: grid; gap: 5px; padding: 12px; border-radius: 9px; background: #f7f5ff; color: #77708b; font-size: .75rem; }
.policy strong { color: #58458f; }
.clock-badge { display: flex; align-items: center; gap: 9px; padding: 10px 13px; border: 1px solid #d8f0e3; border-radius: 10px; background: #f3fbf6; }
.clock-badge small { display: block; color: #77a28b; font-size: .6rem; font-weight: 800; letter-spacing: .1em; }
.clock-badge strong { display: block; color: #43805e; font-size: .78rem; }
.reply-form { display: grid; grid-template-columns: 1fr 1.3fr auto; align-items: end; gap: 10px; }
.reply-form label { min-width: 0; }
.reply-form input, .reply-form select { min-width: 0; width: 100%; }
.outbox { padding: 13px; margin: 8px 0; border: 1px solid #e7e4f0; border-left: 3px solid #8065e6; border-radius: 10px; background: #fcfbff; }
.outbox-top { display: flex; align-items: center; gap: 7px; }
.outbox-top small { margin-left: auto; color: #aaa9b5; font-size: .68rem; }
.outbox p { margin: 9px 0 6px; color: #5b596b; font-size: .82rem; }
.simulated { color: #aaa9b5; font-size: .62rem; letter-spacing: .08em; }
.empty { display: grid; place-items: center; min-height: 130px; text-align: center; color: #8b8998; }
.empty.compact { min-height: 110px; }
.empty p { margin: 5px 0 0; font-size: .78rem; }
.empty-icon { display: grid; place-items: center; width: 40px; height: 40px; margin-bottom: 8px; border-radius: 12px; color: #8065e6; background: #f0edff; font-size: 1.35rem; }
.empty-page { display: grid; place-items: center; min-height: 520px; text-align: center; }
.large-icon { width: 62px; height: 62px; font-size: 2rem; }
.empty-page p { color: #888798; }
.timeline { display: grid; gap: 0; padding: 0; margin: 0; list-style: none; }
.timeline li { display: grid; grid-template-columns: 16px 1fr; gap: 10px; position: relative; padding: 0 0 18px; }
.timeline-dot { width: 9px; height: 9px; margin-top: 5px; border: 2px solid #8a71e8; border-radius: 50%; background: #fff; }
.timeline li:not(:last-child) .timeline-dot:after { content: ""; position: absolute; top: 14px; left: 4px; height: calc(100% - 14px); border-left: 1px solid #ddd6f4; }
.timeline small, .timeline code { display: block; color: #aaa9b5; font-size: .65rem; }
.timeline strong { display: block; margin: 2px 0; color: #575469; font-size: .78rem; text-transform: capitalize; }
.timeline p { margin: 2px 0 4px; color: #858494; font-size: .73rem; }
.report-metrics { grid-template-columns: repeat(6, 1fr); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; white-space: nowrap; }
th, td { padding: 12px 9px; border-bottom: 1px solid #f0eef5; text-align: left; font-size: .76rem; }
th { color: #aaa9b5; font-size: .63rem; letter-spacing: .08em; }
td { color: #656375; }
.risk-panel { align-self: start; }
.risk-list { display: grid; gap: 10px; padding: 0; margin: 0; list-style: none; }
.risk-list li { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; padding-bottom: 10px; border-bottom: 1px solid #f0eef5; color: #666475; font-size: .77rem; }
.risk-list li code { margin-left: auto; }
.fairness { margin-top: 18px; padding: 13px; border-radius: 9px; color: #635b80; background: #f7f5ff; font-size: .76rem; }
.fairness p { margin: 4px 0 0; }
.honesty-grid { margin-top: 28px; }
.honesty-icon { margin-bottom: 15px; width: 38px; height: 38px; }
.clean-list { display: grid; gap: 10px; padding-left: 18px; color: #747386; font-size: .82rem; }
.clean-list li::marker { color: #9279e8; }
.notice { padding: 14px; border-radius: 10px; color: #6d6783; background: #f6f4ff; }
@media (max-width: 900px) { .nav { display: none; } .hero { grid-template-columns: 1fr; padding: 35px 28px; } .hero-art { display: none; } .metrics, .report-metrics { grid-template-columns: repeat(3, 1fr); } .commitment-header, .commitment-detail summary { grid-template-columns: 1fr 2fr 1fr; } .commitment-header span:nth-child(4), .commitment-header span:nth-child(5), .commitment-detail summary .pill, .commitment-detail summary .confidence { display: none; } .chase-layout, .chase-columns, .report-grid, .three-up, .honesty-grid { grid-template-columns: 1fr; } .reply-form { grid-template-columns: 1fr; } .intake-actions { flex-wrap: wrap; } .button.large { width: 100%; margin-left: 0; } }
@media (max-width: 580px) { .shell { padding: 0 14px 30px; } .topbar { height: auto; padding: 16px 0; } .top-status { display: none; } h2 { font-size: 1.9rem; } .hero h2 { font-size: 2.6rem; } .metrics, .report-metrics { grid-template-columns: repeat(2, 1fr); } .panel { padding: 17px; } .page-heading { align-items: flex-start; flex-direction: column; } .page-heading .button { width: 100%; } .commitment-header, .commitment-detail summary { gap: 7px; font-size: .7rem; } .summary-task { min-width: 0; } }
"""


def render_page(state: AgentState | None, raw_chat: str, notice: str = "", view: str = "intake") -> str:
    if view not in VIEWS:
        view = "intake"
    if view == "intake":
        content = _intake_view(state, raw_chat)
    elif view == "commitments":
        content = _commitments_view(state)
    elif view == "chase":
        content = _chase_view(state)
    elif view == "report":
        content = _report_content(state) if state else _commitments_view(None)
    else:
        content = _honesty_view()
    state_label = "AI review ready" if state and state.ai_review_status.startswith("applied") else "Offline-first workspace"
    state_dot = "green-dot" if state and state.ai_review_status.startswith("applied") else "purple-dot"
    notice_html = f'<div class="toast">{esc(notice)}<button onclick="this.parentElement.remove()">×</button></div>' if notice else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project Chaser</title><style>{STYLE}</style></head><body><div class="shell"><header class="topbar"><a href="/?view=intake" class="brand"><span class="brand-mark">✦</span>Project Chaser</a><nav class="nav">{nav_link('intake', 'Intake', view)}{nav_link('commitments', 'Commitments', view)}{nav_link('chase', 'Chase', view)}{nav_link('report', 'Report', view)}{nav_link('honesty', 'About', view)}</nav><div class="top-status"><span class="status-dot {state_dot}"></span>{state_label}</div></header>{notice_html}{content}</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _redirect(self, notice: str, view: str = "intake") -> None:
        self.send_response(303)
        self.send_header("Location", "/?notice=" + quote(notice) + f"&view={view}")
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

    def _send_text(self, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        encoded = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/report.txt" and STATE is not None:
            self._send_text(report_markdown(build_report(STATE)))
            return
        query = parse_qs(parsed.query)
        view = query.get("view", ["intake"])[0]
        notice = query.get("notice", [""])[0]
        self._send_text(render_page(STATE, RAW_CHAT, notice, view), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        global STATE, RAW_CHAT
        data = self._body()
        path = urlparse(self.path).path
        if path == "/ingest":
            RAW_CHAT = data.get("chat", "")
            STATE = new_state(RAW_CHAT, reviewer=OpenAICompatibleReviewer.from_env())
            notice = f"Read {len(STATE.messages)} messages and found {len(STATE.commitments)} commitment candidates."
            view = "commitments"
        elif path == "/reset":
            RAW_CHAT = SAMPLE_CHAT
            STATE = new_state(RAW_CHAT, reviewer=OpenAICompatibleReviewer.from_env())
            notice = "Demo chat reset."
            view = "intake"
        elif STATE is None:
            notice = "Extract a chat first."
            view = "intake"
        elif path == "/run":
            notice = f"Agent created {len(run_agent(STATE))} new event(s)."
            view = "chase"
        elif path == "/advance":
            notice = f"Clock advanced. Agent created {len(advance_clock(STATE, timedelta(hours=int(data.get('hours', '24')))))} new event(s)."
            view = "chase"
        elif path == "/reply":
            item = next((candidate for candidate in STATE.commitments if candidate.id == data.get("commitment_id")), None)
            changed = handle_reply(STATE, item.owner, data.get("reply", "")) if item and item.owner else None
            notice = f"Updated {changed.owner}'s commitment to {changed.status}." if changed else "No matching open commitment found."
            view = "chase"
        elif path == "/correct":
            changed = correct_commitment(STATE, data.get("commitment_id", ""), owner=data.get("owner"), status=data.get("status"))
            notice = "Correction recorded with evidence." if changed else "Commitment not found."
            view = "commitments"
        else:
            notice = "Unknown action."
            view = "intake"
        self._redirect(notice, view)


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
