# Project Chaser

Project Chaser is an offline-first prototype that turns a messy group chat into tracked commitments, polite bounded follow-up, and an evidence-based progress report.

## Current status

The application is being built as a focused hackathon prototype. The intended demo flow is:

1. Paste or upload a group chat export.
2. Review extracted commitments and clarification questions.
3. Fast-forward the demo clock.
4. See a controlled reminder in the local outbox.
5. Process a reply such as “done” or “stuck on the API”.
6. See one escalation for a silent overdue commitment.
7. Generate a report with evidence for every claim.

The prototype does not read private one-to-one chats, require a WhatsApp API, or depend on a live external service.

## Requirements

- Python 3.12
- `pip`

The runtime is pinned in `.python-version` and dependencies are pinned in `requirements.lock`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.lock
```

On Windows PowerShell, use `.venv\\Scripts\\python.exe` instead of `.venv/bin/python`.

## Run

```bash
.venv/bin/python app.py
```

Or use:

```bash
make run
```

## Test

```bash
make test
```

The test suite is designed to run without internet access or external API credentials.

## Docker

```bash
docker build -t project-chaser .
docker run --rm -p 8501:8501 project-chaser
```

Open <http://localhost:8501>. The interface is a standard-library local web server, so the running prototype does not require a third-party UI package or an internet connection.

## Privacy and honesty

The prototype stores data locally and displays outgoing reminders in a simulated outbox. It does not silently monitor chats or send real messages. A final honesty sheet will document the simulated parts and the next steps for real Telegram delivery.
