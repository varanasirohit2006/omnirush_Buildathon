# Project Chaser — Project Flow

## One-line explanation

Project Chaser turns group-chat promises into trackable commitments, polite simulated follow-ups, blocker visibility, and an evidence-based project report.

## End-to-end user flow

### 1. Upload a group chat export

The user opens Project Chaser and uploads a WhatsApp-style `.txt` group chat export. The uploaded text is shown immediately in the chat box so the user can review it before extracting anything.

Example input:

```text
2026-10-19 09:00 - Alice: I will finish the slides by Friday
2026-10-19 09:05 - Dev: I will complete the API tomorrow
2026-10-19 09:10 - Cara: Someone should handle the demo sometime next week
```

The prototype processes the supplied file locally. It does not secretly monitor chats or connect to WhatsApp.

### 2. Extract possible commitments

The deterministic extractor reads each message and looks for clear, tentative, or unassigned project work.

Example result:

| Owner | Task | Deadline | Initial result |
| --- | --- | --- | --- |
| Alice | Finish the slides | Friday | Accepted |
| Dev | Complete the API | Tomorrow | Accepted |
| Unassigned | Handle the demo | Unclear | Needs clarification |

The system does not guess missing owners or deadlines. Tentative messages such as `I might try to finish the API` remain proposed instead of becoming confirmed work.

### 3. Review the commitment board

The user reviews the extracted commitments before follow-up begins. Each item shows:

- Owner and task
- Tracked deadline
- Current status
- Confidence and commitment strength
- Original source message
- Evidence/message ID
- Follow-up policy explanation

The user can correct an owner or status. Corrections are recorded as visible events.

### 4. Run the follow-up agent

The user opens **Chase** and runs the agent or advances the demo clock. The agent checks each commitment against its policy rules.

A reminder is allowed only when:

- The owner is known
- The exact deadline is known
- The work is not complete
- The work is not waiting for clarification
- Quiet hours are not active
- The reminder limit has not been reached

Eligible work produces a polite message in the local simulated outbox, for example:

```text
Hi Alice — friendly check-in: finish the slides is due by Friday.
Reply with done, a blocker, or a new date.
```

The prototype does not deliver this message to a real person.

### 5. Process a teammate reply

The user selects a commitment and enters the teammate's reply. The selected commitment ID is used, so a reply cannot accidentally update another task owned by the same person.

Examples:

| Reply | Resulting status |
| --- | --- |
| `Done, the slides are uploaded` | Done |
| `I am stuck on the API authentication` | Blocked |
| `I need more time until Friday` | In progress with an updated deadline |
| `I am working on it` | In progress |

The reply is stored as status evidence.

### 6. Handle overdue work

When a commitment passes its deadline without completion, the agent marks it missed and can create one escalation in the local outbox.

The follow-up policy is bounded:

- At most two reminders
- At most one overdue escalation
- No reminders during quiet hours
- No follow-up for completed work
- No follow-up when required information is missing

Blocked work is surfaced as a risk instead of being treated as silence.

### 7. Generate the report

The Report page summarizes the current project state using commitment and event evidence:

- Total tracked commitments
- Completed work
- Blocked work
- Missed deadlines
- Items needing clarification
- Risks and blockers
- Evidence identifiers for every commitment
- Optional AI review provenance

The report can be exported as Markdown or CSV.

## What is real and what is simulated

### Real in this prototype

- Local `.txt` chat parsing
- Conservative commitment extraction
- Owner and deadline clarification handling
- Commitment review and corrections
- Simulated clock and policy evaluation
- Reply classification
- Evidence-linked progress reports
- CSV and Markdown report exports

### Simulated for the demo

- Reminder and escalation delivery
- Fast-forwarding time
- Persistence between application restarts
- Real Telegram, WhatsApp, or email integration

## Privacy and fairness

- The user supplies the chat export explicitly.
- The prototype does not monitor private chats.
- Data is kept in the running local process.
- Reminders are never generated without an owner and exact deadline.
- The report does not rank people by message volume or guess effort, intent, or laziness.
- Optional AI review is limited to low-confidence candidates and falls back to deterministic extraction if unavailable.
