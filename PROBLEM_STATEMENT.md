# Project Chaser — Client Brief & Problem Statement

**Prepared by:** The client (team lead, student, and reluctant nag)
**For:** The software engineer / build team
**Project:** An agent that chases group-project commitments so I don't have to
**Timeline:** Hackathon build — one working prototype and a 90-second demo

---

## 1. A note from me to you

Hi — I'm the person in every group project who ends up sending *"hey, any update?"* at 11pm. I'm tired of it. I don't want another task manager, another Notion page, or another bot that just summarizes chats. I want something that **takes over the chasing**.

Here's what happens every time. We split the work in a group chat. Someone says, "I'll do the slides by Friday." Someone else says, "I'll handle the backend, probably by Sunday." Nobody writes it down. Friday passes. Sunday passes. Two days before the deadline, I'm the bad guy asking everyone where their part is, and half the work lands in the last six hours.

The uncomfortable part isn't the work. It's the **follow-up**. Nobody wants to be the one nagging friends. So things slip, and then everyone panics.

I want an agent that reads our chat, remembers who promised what, reminds people politely before things slip, escalates when someone goes quiet, and gives me a fair progress report without me chasing anyone manually.

**In one sentence:** *I want an agent that takes the social hit of following up, so the group actually finishes on time.*

---

## 2. The problem I have today

### 2.1 Promises live in chat and die in chat

Our commitments are buried in WhatsApp, Discord, or Slack. They're informal:

- "I'll do the slides by Friday."
- "bro I'll try to finish the API tomorrow night"
- "I can take the report if someone else does the demo"
- "let's meet Sunday and figure it out"

There's no owner, no date, and no status. The moment the chat scrolls, the promise is gone.

### 2.2 Existing tools don't solve my problem

- **Trello / Notion / Asana:** I have to create and update every card myself. That's the work I'm trying to avoid.
- **Chat summarizers:** They tell me what was said. They don't follow up on what was promised.
- **Calendar reminders:** They remind *me*. They don't remind the person who owes the work.
- **Generic AI assistants:** They'll write a reminder if I ask. I don't want to ask. I want it handled.

### 2.3 The real cost

- Deadlines are missed or barely met.
- I do unpaid project-management work.
- The group avoids each other instead of raising blockers early.
- Contribution is judged by who talks the loudest, not who delivered.
- One person ends up doing everything, and resentment follows.

I don't need a better dashboard. I need **delegation of the follow-up itself**.

---

## 3. What I want you to build

A working prototype of **Project Chaser**: an agent that turns a messy group chat into tracked commitments, follows up automatically, and produces an honest progress report.

### 3.1 Core behaviors (must have)

**1. Read our chat**
- I paste text or upload a chat export (WhatsApp `.txt` export is enough).
- It handles messy, informal language, including Hinglish and slang.
- It should not require a perfect format.

**2. Extract commitments, not just tasks**
- Who promised to do what, by when.
- Distinguish "I'll do it" from "maybe," "I'll try," and "someone should."
- If a deadline is missing or unclear, **ask a clarifying question** instead of inventing one.
- Show me what it extracted with a confidence level, so I can correct it.

**3. Create a simple task board**
- One screen: owner, task, deadline, status, last update.
- Statuses that make sense: `proposed`, `accepted`, `in progress`, `blocked`, `done`, `missed`.
- I should be able to fix an entry in one click.

**4. Remind people at the right time**
- Send reminders before the deadline, not after.
- Polite by default. Firmer as the deadline approaches.
- Do not spam. Respect quiet hours. Have a maximum number of nudges.
- Reach people where they actually are — Telegram is fine for the prototype. Email is a fallback.

**5. Understand replies and update itself**
- If someone says "done," mark it done.
- If someone says "stuck on the API," mark it blocked and flag the risk.
- If someone asks for more time, record the new date and tell the group.
- If someone goes silent, notice it and escalate.

**6. Detect risk before it becomes a crisis**
- Task due soon with no update.
- Person has too many open commitments.
- A dependency is blocked.
- Someone has stopped responding.

**7. Produce a fair, evidence-based progress report**
- One page: what was promised, what was delivered, what slipped, what was blocked.
- Contribution based on **commitments kept and work completed**, not message count.
- Every claim should link back to a message or a status change.
- I want this to be defensible if I show it to a teammate or a professor. It should not feel like surveillance.

**8. Let me demonstrate it in under two minutes**
- Since real group projects take weeks, I need a way to **simulate time passing** — fast-forward a few days and show reminders, escalation, and the report happening without waiting.
- The demo must work offline if the internet dies.

### 3.2 Nice to have (only if the core works)

- Send a weekly digest to the group.
- Suggest reassignment when someone is overloaded or blocked.
- Let me approve a reminder before it sends (a "draft" mode).
- A tone setting: Friendly / Firm / "Mom mode."
- Discord or Slack webhook in addition to Telegram.

### 3.3 What I do **not** want

- Another full project-management suite.
- A real WhatsApp API integration (the export is enough).
- A mobile app.
- Reading private one-to-one chats. Only the group chat I provide.
- Automatic judgments about people's grades or "laziness."
- A system that sends messages without limits.
- A demo that only works if the internet and a third-party API are perfect.

---

## 4. How I will judge whether it works

I'm not a security engineer, and I don't care about your architecture. I care about whether it solves my problem. Here's what "good" looks like to me:

| What I test | What I expect |
|---|---|
| Paste a messy 40-message chat | At least 90% of clear commitments captured correctly |
| Ambiguous deadline ("sometime next week") | Agent asks, does not guess silently |
| Task due in 2 days, no update | Risk flag + a polite nudge sent automatically |
| Person replies "stuck on the API" | Status changes to blocked; I get a suggested next step |
| Person goes silent past the deadline | One clear escalation, not ten messages |
| Click "Generate report" | One page with evidence, no guessing |
| Watch the demo | Under 2 minutes, no manual data entry beyond pasting the chat |
| Setup | I can run it in under 5 minutes |

**The bar:** after seeing it, I should think, *"I would actually use this next semester."*

---

## 5. Constraints

- **Privacy:** Only the chat I provide. No hidden monitoring. Tell me where data is stored and whether it leaves my machine.
- **Politeness:** The reminders must sound like a helpful teammate, not a boss. If it embarrasses someone, I won't use it.
- **Reliability:** The demo must not depend on a live external API that can fail. Have a fallback.
- **Scale:** A group of 4–8 people, 10–30 commitments. It does not need to handle an enterprise.
- **Budget:** Free tiers and open-source tools only.
- **Time:** This is a hackathon. Build the smallest thing that proves the loop works, then polish the demo.

---

## 6. Deliverables

1. **Working prototype** I can run on my laptop.
2. **A 90-second demo** showing: paste chat → board → automatic nudge → reply handling → escalation → report.
3. **Source code** with setup instructions.
4. **A one-page honesty sheet** explaining what is real, what is mocked, and what you would build next with real integrations.
5. **A short explanation** of how you prevent false reminders and unfair reports.

---

## 7. Questions I want answered before you start

1. How will you handle ambiguous commitments like "I'll try to do it by Friday" without creating false tasks?
2. How will you stop the agent from nagging too much or embarrassing someone?
3. How will the progress report stay fair and evidence-based?
4. What happens if someone never replies?
5. What is real in the demo, and what is simulated?
6. Why is this an *agent* and not just a task extractor with a reminder bot?

---

## 8. The outcome I want

I want to hand this agent a messy group chat and walk away. When I come back:

- Every clear promise is on a board.
- The ambiguous ones have been clarified.
- The people who are on track have been left alone.
- The people at risk have been nudged, politely.
- The blockers have been surfaced before the deadline.
- I have a one-page report I can defend.

And at no point did I have to be the bad guy.

**That is the product. Build that.**
