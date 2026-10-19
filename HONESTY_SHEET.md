# Project Chaser honesty sheet

## What is real in the prototype

- A supplied chat export is parsed locally into normalized messages.
- Clear and tentative commitments are separated.
- Missing owners and unclear deadlines become clarification questions rather than silently invented data.
- Each commitment retains source-message evidence.
- The board supports visible corrections and records them as events.
- A simulated clock drives risk checks, reminders, and overdue escalation.
- Replies can mark work done, blocked, in progress, or extended.
- The report is generated from commitment and event records and includes evidence identifiers.

## What is simulated

- The local outbox displays reminder and escalation text but does not send a real Telegram or email message.
- Fast-forwarding replaces real elapsed time so the complete demo fits in 90 seconds.
- Extraction uses explainable rules and a small English/slang/Hinglish pattern library. It is not presented as broad language understanding.
- Optional AI review is used only for low-confidence candidates and only when the operator configures an OpenAI-compatible endpoint. High-confidence items stay on the deterministic path.
- For Gemini, the prototype uses Google's OpenAI-compatible endpoint and sends only low-confidence candidate messages in the configured review request.
- The current running process keeps state in memory. A future version should persist approved state in local SQLite.

## How false reminders are prevented

1. A reminder requires a known owner and an exact deadline.
2. Tentative or incomplete commitments remain `proposed` and visibly ask for clarification.
3. Completed work is excluded from reminders.
4. Quiet hours are respected.
5. The policy permits at most two reminders and one overdue escalation.
6. Re-evaluating the agent at the same simulated time is idempotent.
7. Every outgoing message is recorded in the local outbox with a purpose and commitment ID.
8. If the AI API fails or returns invalid data, the deterministic result is kept and the failure is shown as a fallback status.

## How reports stay fair

- The report uses commitments kept, completed, blocked, extended, or missed.
- It does not use message volume as a contribution score.
- It does not infer laziness, grades, intent, or effort.
- Every commitment outcome links to its source message or later status evidence.
- Unknown and unresolved information remains visible as unresolved.

## Next step for a real integration

Add an explicit opt-in Telegram adapter behind the existing outbox policy. The adapter should require the same owner, quiet-hour, maximum-nudge, and evidence checks before any real delivery.
