# SCRUM-77 Teammate Validation Report (Real PR Review)

## Report purpose

This report records an independent teammate's experience reviewing the SCRUM-77
branch: **Persistent Pandu chat history** — durable conversations/messages on
the backend, plus this branch’s follow-up-context work so continuing a thread
lets Pandu use earlier completed turns.

Automated tests matter, but they are **not enough**. Please also run the app
locally and interact with Pandu. Record every problem: setup issues, unclear
instructions, weak follow-up context, sessionStorage still holding messages,
ownership leaks, or design concerns.

## Review status

- Reviewer: Nischal
- Report status: `complete` — review recorded; follow-up testing required
- Overall result: `fail` — one frontend test failed and live chat did not produce a usable answer; retesting required
- Final recommendation: `request changes` — investigate and rerun the failing frontend test, then retest Pandu's reply and follow-up context before approval

## Branch under review

```text
feature/SCRUM-77-persistent-pandu-chat-history
```

Owner: Aashish Dhital

```bash
git fetch origin
git checkout feature/SCRUM-77-persistent-pandu-chat-history
git log --oneline origin/development..HEAD
git diff --stat origin/development...HEAD
```

## What this branch does

Most durable chat storage already landed via **SCRUM-24** / **SCRUM-23**
(`ConversationMessage`, `GET …/messages/`, cascade delete, ownership 404s,
course chat loading history from the API, agent `remember_turn`). This branch
closes the remaining SCRUM-77 gap:

- Auto-inject recent **completed** Q→A pairs into each `POST /agent/pandu/` turn
  so follow-ups keep context (AC2).
- Window capped at **8** messages (full pairs only); skip `PENDING` / `FAILED`.
- Keep `recall_history` as **optional** deeper lookback — never block a reply if
  unused, failed, or empty (same idea as optional citations).
- Add SCRUM-77 **AC6** tests for save / load / continue / delete / ownership on
  the agent path.

## Main files to review

- `backend/apps/agent/pandu/tools/memory.py` — `prior_turns_for_prompt`,
  `AUTO_HISTORY_LIMIT = 8`, optional `recall_history` tool description
- `backend/apps/agent/views.py` — load prior turns **before** saving the new ask
- `backend/apps/agent/pandu/loop.py` — inject `prior_messages`; evidence gate
  ignores `recall_history`
- `backend/apps/agent/pandu/prompts.py` — follow-up / optional-recall guidance
- `backend/apps/agent/tests/test_scrum77_ac6_persistence.py` — AC6 suite
- Related: `test_memory_tools.py`, `test_loop.py`, `test_pandu_endpoint.py`

## Prerequisites

- Python **3.12** and `backend/venv` with dependencies installed.
- **Docker Desktop** (Linux containers) for `scripts/check.py` disposable
  Postgres.
- For **live Pandu chat**: local backend + frontend, valid `backend/.env`
  (`GEMINI_API_KEY`; agent/RAG backends as used for local demos).
- Optional for ownership: a second student account.

## Rate limits / cost (intentional)

Live Gemini calls are limited. Please:

- Do **not** hammer Pandu with long automated scripts.
- Keep the live session to a **short** checklist (section B).
- If you see a short “couldn’t finish / try again” reply, wait and retry once —
  transient Gemini 429/503 is expected. That is **not** automatically a
  SCRUM-77 product bug; note it in findings if it blocks review.

Judge follow-up **context** on successful turns.

---

## A. Automated validation commands

Run from the **repository root**. Prefer these before (or alongside) manual
chat.

**Do not** run bare `python manage.py test …` or bare `pytest` against
`config.settings` / your `.env`. That can hit the **dev database** and make
**live billed Gemini** calls. Use `scripts/check.py` (isolated test settings).

### A1. Full backend (CI-style) — Docker required

```bash
backend/venv/bin/python scripts/check.py --component backend --suite all
```

**Windows (PowerShell)**

```powershell
backend\venv\Scripts\python.exe scripts\check.py --component backend --suite all
```

**Expect**

- `[check] Django system checks: PASS`
- Migration drift: **PASS** (`No changes detected`)
- `[check] Fresh database migrations: PASS`
- `[check] Backend tests (all): PASS`
- Exit code **0**

This run includes `test_scrum77_ac6_persistence.py` (save / load / continue /
delete / ownership) and the related agent memory/loop/endpoint tests.

### A2. Frontend via check.py

```bash
backend/venv/bin/python scripts/check.py --component frontend
```

**Windows (PowerShell)**

```powershell
backend\venv\Scripts\python.exe scripts\check.py --component frontend
```

**Expect**

- `[check] Oxlint: PASS`
- `[check] Frontend tests: PASS`
- `[check] TypeScript and build: PASS`
- Exit code **0**

(Node **24.15+**; CI uses **24.19.0**. This branch does not change frontend
files, but run A2 so history UI regressions from `development` are still
caught before approve.)

### A3. Everything (optional)

```bash
backend/venv/bin/python scripts/check.py --component all
```

**Expect:** all PASS lines from A1 + A2, exit **0**.

Record pass/fail counts below in **Findings**.

---

## B. Local app — interact with Pandu (required)

Keep this short. Only what SCRUM-77 still needs to prove in the UI.

### B1. Setup

1. Check out `feature/SCRUM-77-persistent-pandu-chat-history`.
2. Start backend (`manage.py runserver` with `.env` loaded) and frontend
   (`cd frontend && npm run dev`).
3. Log in, open a course with ≥1 **READY** material selected in Sources.
4. Open DevTools → **Network** and **Application → Session Storage**.
5. Prefer **+ New chat**.

### B2. Check parameters (not scripted questions)

Use **your own wording**. No fixed question text.

| Parameter | What to do | Pass when |
| --- | --- | --- |
| First ask | Any clear course/material question | Reply appears; Network `POST /api/v1/agent/pandu/` then `GET …/messages/` |
| Follow-up | Same thread; ask that depends on the prior turn (pronoun / “that” / “explain more” / analogy-style) | Answer clearly uses prior context (AC2) |
| Refresh | Hard refresh while signed in | Same thread + messages reload in order; Network `GET …/messages/` (AC1, AC8) |
| Session Storage | Key `studyforge:course-chat:<userId>:<courseId>` | Only `conversationId` + `selected` — **no** message bodies (AC7) |
| Re-auth | Logout → login → same course | History still there (AC9) |

Optional (covered heavily by AC6 tests; only if you have time):

| Parameter | What to do | Pass when |
| --- | --- | --- |
| Citations / tools | Refresh after a materials answer | Citations/tools still on that reply (AC3) |
| Delete | Delete the thread, refresh | Thread stays gone (AC5) |

### B3. Known flaky live behavior

- Occasional Gemini blip → retry once. Not automatically a SCRUM-77 fail.

---

## C. Browser checklist

Mark each: `pass` / `fail` / `blocked` / `unverified` / `n/a`

| # | Check | Result | Notes |
| --- | --- | --- | --- |
| 1 | First ask persists | pass | Reviewer confirmed the earlier messages still existed after logout/login. The initial reply was a generic clarification; persistence does not establish answer quality. Supporting browser evidence is in the reviewer's video. |
| 2 | Follow-up uses earlier turn (AC2) | blocked | Initial course questions repeatedly returned "Could you clarify what you'd like help with for this course?" No usable explanation was available for a contextual follow-up. |
| 3 | Refresh reloads history in order (AC1 / AC8) | pass | Reviewer confirmed "the hard restore worked too": chat history returned after a hard refresh. Reviewer states the browser/Network evidence is in the video. |
| 4 | Session Storage has no message bodies (AC7) | pass | Reviewer found the chat metadata entry during the walkthrough, after checking for `conversationId` and `selected` without message bodies. |
| 5 | Logout → login resumes history (AC9) | pass | Reviewer confirmed the earlier messages were still present after following the logout/login steps. |
| 6 | Optional: delete chat (AC5) | pass | Reviewer reported "deletion successful" after the delete/confirm/refresh instructions. No backend cascade inspection was performed. |

---

## D. Findings and suggestions (Nischal fills this in)

### Automated tests

Recorded on 2026-11-20 from Nischal's supplied test output. TypeScript and build
were confirmed as passing by Nischal after the pasted output ended.

```text
Backend check.py (--suite all): Backend tests PASS
  930 passed, 0 failed, 1 skipped; 549 subtests passed.
  Duration: 242.04 seconds.
  Skipped: backend/tests/documents/test_s3_process_integration.py:115
    Requires SCRUM127_S3_INTEGRATION=1 for the Docker S3 integration test.

Frontend check.py: FAIL overall
  Oxlint: PASS (9 warnings, 0 errors).
  Frontend tests: FAIL (648 passed, 1 failed; 60 files passed, 1 failed).
  TypeScript and build: PASS (confirmed by reviewer).

SCRUM-77 AC6 covered in backend run? yes (included in the full backend suite;
  no separate AC6 count was supplied).

Notes:
  The backend excerpt confirms the test stage passed; system checks and
  migration-stage results were not included in the supplied excerpt.
  The frontend remains failing despite TypeScript and build passing.

Failed frontend test:
  File: frontend/src/components/chat/CourseChat.test.tsx:167
  Test: explains why a transcribed or typed draft cannot be sent without
    a READY source
  Expected: "Send to Pandu" button is disabled without a READY source.
  Actual: the button remained enabled; expect(element).toBeDisabled() failed.
  Cause has not yet been determined.
```

### Live Pandu session

Recorded on 2026-11-20 from Nischal's confirmations during the manual browser
walkthrough and the supplied chat screenshot. Nischal confirms the supporting
browser evidence is in the video; these results reflect the reviewer's account.

```text
Course used: CS 4332 (identified during the earlier local setup check).
Materials selected (READY): Screenshot shows 1 selected source. The earlier
  local setup check identified Relational A & C Part 2.pdf as READY.
Approx. turns (first + follow-up): 2 initial/rephrased course questions;
  no contextual follow-up verified.
Live behavior: repeated generic clarification; follow-up context blocked.
  No browser rate-limit response or successful retry was confirmed.
```

**Turn log** (parameters only)

| # | Parameter (first ask / follow-up / refresh / …) | Result (good / weak / fail / blocked / unverified) | Notes |
| --- | --- | --- | --- |
| 1 | First ask / rephrased ask | fail | `explain cartesian product` and `cartesian product` received the same generic clarification instead of an explanation. Screenshot shows the first exchange and 1 source selected. |
| 2 | Follow-up context | blocked | No usable initial answer; AC2 cannot be marked pass from this session. |
| 3 | Refresh | good | Reviewer confirmed that hard-refresh restoration worked and that supporting evidence is in the video. |
| 4 | Session Storage | good | Reviewer located the metadata entry after initially seeing an empty storage view. AC7 recorded as pass from the walkthrough. |
| 5 | Logout → login | good | Reviewer confirmed "they exist" when checking the earlier messages after re-authentication. |
| 6 | Delete chat | good | Reviewer confirmed "deletion successful" after the optional deletion steps. |

### Bugs / issues found

```text
Pandu repeatedly returned "Could you clarify what you'd like help with for
this course?" for a clear question about Cartesian product from the selected
PDF. This blocked a meaningful follow-up-context check. The live result
does not establish an AC2 regression or a definitive cause.

The frontend automated-test failure recorded above remains unresolved.
```

### Suggestions (UX, prompts, performance, docs)

```text
1. Investigate the single failing frontend test in CourseChat.test.tsx,
   address the cause, and rerun it and the frontend validation checks.
2. Retest the live chat reply for the selected PDF: Pandu should answer the
   question instead of repeating a generic clarification. Then verify a
   contextual follow-up in the same thread (AC2).

The reviewer confirms supporting browser evidence is already in the video.
```

### Overall recommendation

```text
[ ] approve
[ ] approve with notes
[x] request changes

Summary (2–4 sentences):
The reviewer confirmed Session Storage metadata, hard-refresh restoration,
history after logout/login, and successful chat deletion, with supporting
browser evidence in the video. One frontend test failed, and live Pandu replies
did not answer the question, leaving follow-up context blocked. Request changes:
investigate and rerun the failing frontend test, then retest the chat reply and
contextual follow-up before approval.
```

---

## E. Sign-off

- Reviewer name: Nischal
- Date: 2026-11-20
- Branch SHA reviewed (`git rev-parse HEAD`): `3d5a52bee0a3d2ee676ccf6eefecbb4947002dfc`
- Time spent (approx.): 1 hour
- Browser evidence: reviewer's validation video (confirmed by Nischal)

---

## F. Acceptance criteria map

| AC | Covered by |
| --- | --- |
| 1 Refresh / logout+login | C3, C5 |
| 2 Continuing uses earlier messages | C2 (+ AC6 continue tests) |
| 3 Citations / tools | Optional UI check; AC6 save/load |
| 4 Ownership | AC6 ownership test (UI optional) |
| 5 Delete removes messages | C6 browser deletion; AC6 delete test for backend cascade |
| 6 Automated tests | Section A + `test_scrum77_ac6_persistence.py` |
| 7 DB source of truth | C4 |
| 8 Chronological order | C3 |
| 9 Resume after sign-in | C5 |

---

## G. Owner follow-up (Aashish Dhital) — 2026-11-20

Separate from Nischal’s findings above (sections C–E unchanged). Owner validation video is in Slack.

### Live AC2 retest

| # | Parameter | Result | Notes |
| --- | --- | --- | --- |
| 1 | First ask | pass | Course: Honors Leadership Class. Ask: “explain me about Separation Edges and Vertices” → materials-based answer (not clarify). |
| 2 | Follow-up (AC2) | pass | “can you please explain that more” → expanded the same Separation Edges/Vertices topic. |
| — | Nischal’s clarify-only session | n/a | Treated as reviewer environment/setup; his note already said it did not establish an AC2 regression. |

### Frontend / automated tests (owner re-run)

```text
CourseChat.test.tsx:
  16 passed (optional-sources send test updated).
  Commit: c3272c0 test(SCRUM-77): align CourseChat send test with optional sources

scripts/check.py --component frontend (2026-11-20):
  Oxlint: PASS
  Frontend tests: PASS — 649 passed, 0 failed (61 files)
  TypeScript and build: PASS

Backend: left as Nischal recorded (930 passed, 0 failed, 1 skipped).
```

Finding: the failing READY-gate test was stale vs SCRUM-25 optional sources (send `hi` with no document still allowed; Pandu clarifies when materials are needed). Test updated; UI not re-gated.

### Owner note on Nischal’s suggestions

| # | Suggestion | Owner status |
| --- | --- | --- |
| 1 | Fix CourseChat.test.tsx + rerun frontend checks | Done |
| 2 | Retest live reply + AC2 follow-up | Done — video in Slack |

Branch SHA at owner follow-up: `c3272c0d58dd827f4a27ed27833185d5f6b4408e`
