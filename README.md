# Project Chaser

Project Chaser is an offline-first prototype that turns a messy group chat into tracked commitments, polite bounded follow-up, and an evidence-based progress report.

## Current status

The application is a focused hackathon prototype. The intended demo flow is:

1. Paste or upload a group chat export.
2. Review extracted commitments and clarification questions.
3. Fast-forward the demo clock.
4. See a controlled reminder in the local outbox.
5. Process a reply such as “done” or “stuck on the API”.
6. See one escalation for a silent overdue commitment.
7. Generate a report with evidence for every claim.

The prototype does not read private one-to-one chats, require a WhatsApp API, or depend on a live external service.

## Optional AI-assisted review

The normal extractor is deterministic and works without an API. If the optional environment variables below are configured, only low-confidence or clarification candidates are sent in one batch to an OpenAI-compatible chat-completions endpoint. High-confidence commitments stay on the normal local path.

The AI reviewer may classify a candidate as `accepted`, `proposed`, `clarify`, or `ignore`. Safety gates still prevent it from inventing an owner or deadline, promoting tentative work into an accepted reminder-bearing commitment, or breaking the app when the API is unavailable.

Configure these variables locally; never put the key in a committed file:

```powershell
$env:LLM_API_URL="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
$env:LLM_API_KEY="your-key-in-the-terminal-only"
$env:LLM_MODEL="gemini-2.0-flash"
```

You can also put the same variable names in a local `.env` file. The application loads that file automatically; `.env` is ignored by Git. Then start the app from the same project folder. Leave the variables unset for the fully offline demo.

## Requirements

- Python 3.12
- `pip`

The runtime is pinned in `.python-version` and test dependencies are fully pinned in `requirements.lock`. The application runtime uses only Python’s standard library.

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

To verify the complete product loop without opening the browser:

```bash
make demo-check
```

On Windows PowerShell, the equivalent is:

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_smoke
```

For the presenter flow, see [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

## Docker

```bash
docker build -t project-chaser .
docker run --rm -p 8501:8501 project-chaser
```

Open <http://localhost:8501>. The interface is a standard-library local web server, so the running prototype does not require a third-party UI package or an internet connection.

## Clean Linux commands

From a fresh Linux checkout with Python 3.12, run:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.lock
make test
make demo-check
make run
```

Then open <http://localhost:8501>.

To build and run the container instead:

```bash
docker build --tag project-chaser .
docker run --rm --publish 8501:8501 project-chaser
```

The `.dockerignore` file excludes `.env`, `.venv`, Git metadata, caches, and logs from the image build context.

## Privacy and honesty

The prototype stores data locally and displays outgoing reminders in a simulated outbox. It does not silently monitor chats or send real messages. A final honesty sheet will document the simulated parts and the next steps for real Telegram delivery.
