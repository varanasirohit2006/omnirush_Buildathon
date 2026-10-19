# Project Chaser — 90-second demo script

This script uses the built-in 40-message fixture. It is deliberately deterministic and does not require internet access, API keys, or real message delivery.

## Before presenting

From the project folder, start the app:

```powershell
.\.venv\Scripts\python.exe app.py
```

Open <http://localhost:8501>.

Keep this recovery command available if the state gets confusing:

```powershell
make demo-check
```

On Windows PowerShell, use:

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_smoke
```

In the browser, click **Reset demo chat** before starting. The reset button restores the known fixture and the simulated state.

## Presentation sequence

### 0–10 seconds — Intake

Say:

> “I give Project Chaser the same messy group chat that normally gets forgotten.”

Click **Extract commitments**. The app opens the **Commitments** view automatically.

Expected result:

- 40 messages read
- Commitment candidates appear
- The compact board is shown automatically

### 10–25 seconds — Conservative extraction

Point to these examples:

- Alice’s slides: clear owner and deadline
- Ben’s API: tentative language, so it is proposed rather than treated as certain
- Cara’s demo: no owner and vague date, so the agent asks for clarification
- Each row has source-message evidence

Say:

> “It does not invent an owner or deadline. Unclear promises stay visible as questions.”

### 25–40 seconds — First follow-up

Click **Chase** in the top navigation, then click **Run agent now**.

Show the local outbox.

Say:

> “The agent sees work that is close to its deadline and prepares a polite reminder. This is a simulated outbox in the offline prototype.”

### 40–55 seconds — Reply understanding

Select Dev’s integration-test commitment and enter:

```text
I am stuck on the API authentication
```

Click **Process reply**.

Show that the status changes to `blocked`.

Say:

> “A blocker is not treated as silence. It becomes visible with a suggested next step.”

### 55–70 seconds — Bounded escalation

Click **+3 days**.

Show the overdue escalation in the outbox.

Say:

> “For someone who stays silent past the deadline, the agent escalates once. It does not spam the group.”

### 70–90 seconds — Defensible report

Click **Report** in the top navigation.

Show:

- Done, blocked, and missed counts
- Clarification count
- Evidence identifiers
- Fairness note

Finish with:

> “The report is based on commitments and status evidence, not message volume or guesses about people.”

## Recovery during the demo

- If the board is confusing, click **Intake**, click **Reset demo chat**, and extract again.
- Use the top navigation to move between **Commitments**, **Chase**, and **Report**; each view is intentionally focused so there is no long-page scrolling.
- If the server is stopped, restart it with `.\.venv\Scripts\python.exe app.py`.
- If asked whether messages are really sent, answer: “No. Delivery is intentionally simulated for the offline prototype; the policy and outbox are real.”
