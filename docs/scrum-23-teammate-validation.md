# SCRUM-23 Teammate Validation Report (Real PR Review)

## Report purpose

This report records an independent teammate's experience reviewing the SCRUM-23
branch: Pandu’s **agent loop with tool calling** (scope gate → tools → grounded
reply), plus the follow-up fixes for reliability, chat formatting, and
student-facing UX.

Automated tests matter, but they are **not enough**. Please also run the app
locally and talk to Pandu (about **4–8** real questions). Record every problem:
setup issues, unclear instructions, weak answers, rate-limit / timeout
behavior, formatting bugs, or design concerns.

## Review status

- Reviewer: Gaurav
- Report status: `complete`
- Overall result: `pass` — all automated checks green; live session good, with one unretried generic failure and minor UX notes
- Final recommendation: `approve with notes` (`approve` / `approve with notes` / `request changes`)

## Branch under review

```text
feature/SCRUM-23-pandu-agent-loop-tool-calling
```

Owner: Aashish Dhital

## What this branch does

- Adds the Pandu agent package and `POST /api/v1/agent/pandu/` (JWT).
- Hybrid **scope gate** (fixed rules + Gemini classifier) before tools run.
- Tool loop with ownership-checked tools (materials, RAG ask/retrieve, notes,
  quizzes, tasks, memory, list courses).
- Evidence gate: empty retrieval must not become an invented answer.
- Course chat UI talks to the agent endpoint; history parsers accept agent
  `tool_trace` / citation shapes.
- Assistant replies render **Markdown + LaTeX** in chat.
- Student-facing tool line shows only **successful** tools with plain labels
  (no `ask_course_question failed` noise).
- Internal IDs (`course_id`, etc.) stay server-side; greetings should not say
  “Course ID: …”.

## Bugs found during development (brief) and fixes

Use this as a checklist while you chat — these should *not* still bite you in
the obvious ways below.

| Issue | Why it failed | Fix (brief) |
| --- | --- | --- |
| Valid study questions marked out of scope; some turns 400’d | Scope classifier too strict; Gemini rejected unsupported tool JSON Schema fields; thought signatures dropped | Loosen classifier guidance; sanitize FunctionDeclaration schemas; preserve thought signatures |
| History / tools / citations broke on agent replies | Frontend expected only SCRUM-24 `search_sources` shapes | Relax parsers; map `{ name, ok }` tool_trace and partial citations |
| `ask_course_question` often `RAG_GENERATION_FAILED` | Citations failed exact-match even when the answer was good; `allow_uncited` never ran because `generate()` raised first; occasional Gemini 503 | Salvage uncited answers after repair; fall back ask → retrieve + `answer_from_sources`; more Gemini retries |
| Raw `**bold**` / `$math$` in chat | No Markdown/LaTeX renderer | `ChatMarkdown` (react-markdown + KaTeX) |
| Greeting leaked `(Course ID: 23)` | Model payload included internal ids | Omit ids from model payload; keep them in server context for tools |
| “Conversation session could not be found” + failed-tool spam | Model invented wrong `conversation_id` after ids were removed from the prompt; UI printed `… failed` | Always override tool ids from trusted context; hide failed tools; prompt: no tool/session jargon |

## Prerequisites

- Python 3.12 and `backend/venv` with dependencies installed.
- **Node.js 24.15+** (CI / lockfile use **24.19.0**). `scripts/check.py`
  **refuses Node 22** and any version below 24.15.0. If you use nvm:
  `nvm install 24.19.0 && nvm use 24.19.0` (or pin via a repo `.nvmrc` when
  one exists). Then `cd frontend && npm ci` if `node_modules` is missing.
- Docker Desktop (Linux containers) for `scripts/check.py` disposable Postgres.
- For **live Pandu chat**: local backend + frontend running, valid `.env`
  (`GEMINI_API_KEY`, agent/RAG backends as the owner uses for local demo).

## Rate limits / cost (intentional)

Live Gemini calls are **intentionally limited** to keep API cost down for the
team. Please:

- Do **not** hammer Pandu with long automatic scripts.
- Ask about **4–5 focused questions** (up to **5–8** if answers look good and
  you still have quota).
- If you see a short “couldn’t finish / try again” style reply, wait a bit and
  retry once — transient Gemini 429/503 is expected under free/shared limits.
  That is **not** automatically a product bug; note it in findings if it
  blocks review.

Judge answer **quality and grounding** on the successful turns, not only on
whether every call succeeds first try.

---

## A. Automated validation commands

Run from the repository root unless noted. Prefer these before (or alongside)
manual chat.

### A1. Full backend (CI-style) — Docker required

From the **repository root** (wherever you cloned StudyForge):

```bash
backend/venv/bin/python scripts/check.py --component backend --suite all
```

**Expect**

- `[check] Django system checks: PASS`
- Missing-migrations check: **PASS**
- `[check] Fresh database migrations: PASS`
- `[check] Backend tests (all): PASS`
- Exit code **0** (all green; **0 failed**)

### A2. Full frontend via check.py

```bash
backend/venv/bin/python scripts/check.py --component frontend
```

**Expect**

- `[check] Oxlint: PASS`
- `[check] Frontend tests: PASS`
- `[check] TypeScript and build: PASS`
- Exit code **0**

### A3. Everything

```bash
backend/venv/bin/python scripts/check.py --component all
```

**Expect:** all PASS lines from A1 + A2, exit **0**.

### A4. Faster local smoke (optional if Docker is slow)

**Do not** run `python manage.py test apps.agent.tests` under normal
`config.settings`. That loads `backend/.env`, keeps a real `GEMINI_API_KEY`,
and can make **live billed Gemini calls** against your **dev database** if a
mock is missing.

Prefer **A1** for backend (isolated `config.test_settings`, strips API keys,
forces fake LLM backends). Agent coverage (~105 tests) is included in A1’s
full backend run; count them from `test-results/backend-all.xml` if you want
the suite number.

Frontend-only smoke (no Docker), from the repository root:

```bash
cd frontend
npm test
npx tsc -b --pretty false
npm run lint
npm run build
# Expect: all Test Files / Tests passed; tsc/lint/build exit 0
```

Record your actual pass/fail counts below in **Findings**.

---

## B. Local app — interact with Pandu (required)

### B1. Setup

1. Check out `feature/SCRUM-23-pandu-agent-loop-tool-calling`.
2. Start backend (`manage.py runserver` with `.env` loaded) and frontend
   (`npm run dev`).
3. Log in, open a course that has at least one **READY** material selected in
   Pandu Sources.
4. Use a normal course chat thread (new or existing).

### B2. Suggested question set (pick 5–8; at least 4–5)

Keep prompts short. Prefer topics that exist in the selected materials.

1. Greeting: `hi` / `hello` — should greet **without** mentioning Course ID.
2. In-scope materials Q: e.g. explain a concept from the notes (DFA, NFA,
   regular expressions, etc.).
3. Follow-up: `explain more` / `what does that mean?` — should stay on topic.
4. Out-of-scope: e.g. `how to rock climb` or weather — should politely refuse /
   abstain, not invent course content.
5. Another grounded Q on a different topic in the same PDF.
6. Optional: ask to list materials or courses (tool path).
7. Optional: ask something with math/symbols — check Markdown/LaTeX rendering
   (lists, bold, `$...$` if the model uses them).
8. Optional: ask with **no** READY sources selected — should clarify to select
   materials, not hallucinate.

### B3. What “good” looks like

- Answers grounded in selected materials when evidence exists.
- Tools line (if any) uses plain language (e.g. “Searched course materials”),
  **not** `… failed`.
- No “Course ID: …” in student text.
- No invented “conversation session could not be found” when the chat is open
  and materials are selected (that was a fixed bug).
- Markdown/lists/math readable when the model uses formatting.
- Out-of-scope stays out of scope.

### B4. Known flaky live behavior

- Occasional Gemini blip → generic “couldn’t finish… try again”. Retry once.
- Long tool loops can be slow; note latency in findings if it feels too slow.

---

## C. Browser / UX checklist

Mark each: `pass` / `fail` / `n/a`

| # | Check | Result | Notes |
| --- | --- | --- | --- |
| 1 | Greeting has no Course ID | pass | 3 greetings; none mention an ID |
| 2 | Grounded course question gets a usable answer | pass | Assignment + exercises answers accurate; Assignment.pdf p.1 cited. Two answers had no citation (see Suggestions) |
| 3 | Follow-up stays coherent | pass | "break this down into tasks" and "explain more" stayed on topic |
| 4 | Out-of-scope is refused cleanly | pass | Rock-climbing and election questions refused. "What is 2+2?" was answered (see Suggestions) |
| 5 | Tools summary has no “failed” wording | pass | No "failed" wording anywhere in the session |
| 6 | Markdown / math looks OK when present | pass | Headings and lists rendered; no math in this session (math is covered by `ChatMarkdown` tests) |
| 7 | Missing READY selection clarifies instead of fabricating | pass | With no material checked, "what is option 6…" got "Select or upload at least one READY material, then ask again." |
| 8 | Refresh still shows the chat history | pass | live session |

---

## D. Findings and suggestions (Gaurav fills this in)

### Automated tests

```text
Backend check.py:        PASS — exit 0. Django checks PASS, migration drift PASS
                         ("No changes detected"), fresh migrations PASS, tests PASS:
                         912 passed, 1 skipped, 0 failed (549 subtests) in ~118 s.
                         Skip is the opt-in S3 integration test (SCRUM127_S3_INTEGRATION).
Frontend check.py:       PASS — exit 0. Oxlint PASS, Frontend tests PASS,
                         TypeScript and build PASS (Node v24.19.0).
apps.agent.tests:        105 / 105 passed — counted from the check.py JUnit report
                         (test-results/backend-all.xml), matches the expected 105.
npm test:                637 / 637 passed (60 / 60 test files).
tsc / lint / build:      PASS — Oxlint has 10 warnings, all from earlier
                         non-SCRUM-23 commits (CalendarMonth, CourseTasks,
                         AuthContext, CourseWorkspace.test, CourseDetailPage.test).
                         Build warns the main chunk is over 500 kB (see Suggestions).
```

A1 and A2 were run as separate `check.py` invocations; together they cover A3.
A4's backend command was not run. It uses the development settings, which load
`backend/.env` and keep the real Gemini key (see Suggestions). The isolated
`check.py` run covers the same 105 agent tests.

### Live Pandu session

```text
Course used:                     Internet Software Development
Materials selected:              Assignment.pdf, Javascript Exercises.pdf (cited);
                                 none checked for the final question
Approx. questions asked (4–8):   ~11 distinct prompts (incl. 3 greetings, 2 off-topic)
Gemini rate-limit / retry seen?  yes — 1 generic "couldn't finish" reply on
                                 "what is a header?"; not retried
```

**Question log** (copy short notes; no need for full transcripts)

| # | Question (short) | Result (good / weak / fail) | Notes |
| --- | --- | --- | --- |
| 1 | `hi` (asked 3 times) | good | No Course ID; wording varies a little each time |
| 2 | what is a header? | fail | "Pandu couldn't finish the answer right now." Not retried, so a transient Gemini blip (B4) can't be ruled out |
| 3 | explain the assignment | good | Accurate React assignment summary; headings/lists rendered; cites Assignment.pdf p.1 |
| 4 | break this down into tasks | good | Coherent 5-step breakdown; cites Assignment.pdf p.1 |
| 5 | explain the exercises | weak | Accurate list of all 8 exercises, but no citation shown |
| 6 | explain more | weak | Detailed, on-topic follow-up (DOM, JSON.stringify/parse), but no citation shown |
| 7 | how to climb mountains? / who won US election last week? | good | Both refused with the standard abstain message |
| 8 | What is 2+2? | weak | Answered "2 + 2 = 4"; the scope gate let a general question through |
| 9 | list options 6-8 | good | Correct titles; the citation "Javascript Exercises.pdf · Page 2" appears twice |
| 10 | what is option 6 to create url. | good | No material checked → correct "Select or upload at least one READY material" clarify |

### Bugs / issues found

```text
1. No blocking bugs found. Automated suites are fully green.
2. One generic failure ("what is a header?" → "Pandu couldn't finish the
   answer right now."). Not retried, so it may be the transient Gemini
   429/503 described in B4. Worth checking the server log for that turn.
```

### Suggestions (UX, prompts, performance, docs)

```text
1. Bundle size: the main JS chunk is 863.77 kB (257.54 kB gzip) and trips
   Vite's 500 kB warning. Consider lazy-loading ChatMarkdown
   (react-markdown + KaTeX) with React.lazy / dynamic import so pages
   without chat don't pay for it.
2. Guide A4 (`python manage.py test apps.agent.tests`) runs under
   config.settings, which loads backend/.env and does not strip
   GEMINI_API_KEY or force fake LLM backends. A missing mock would then make
   live, billed Gemini calls against the dev database. Suggest dropping A4 or
   adding an "agent" suite to SUITES in scripts/check.py
   (`--suite agent` → backend/apps/agent) so the fast path stays isolated.
3. Guide A1 hard-codes the owner's machine path
   (`cd /Users/aashishdhital20/Documents/studyforge`); replace with
   "from the repository root".
4. Prerequisites: call out that check.py refuses Node 22 (needs 24.15+);
   an `.nvmrc` with 24.19.0 would make `nvm use` a one-step fix.
5. Citations: "explain the exercises" and "explain more" showed no source
   chip, so the student can't verify grounding. If these come from the
   uncited-salvage path, consider still attaching the retrieved document/page.
6. Duplicate citation: "list options 6-8" showed "Javascript Exercises.pdf ·
   Page 2" twice. Dedupe chips by document + page.
7. Scope: "What is 2+2?" was answered. That's harmless, but it shows the
   classifier lets general questions through; decide whether that's intended.
8. Abstain wording "— not that kind of request." reads a bit curt. Consider
   something like "That's outside this course — I can help with your
   materials, tasks, notes, and quizzes."
```

### Overall recommendation

```text
[ ] approve
[x] approve with notes
[ ] request changes

Summary (2–4 sentences):
SCRUM-23 passes all automated checks: backend 912 passed / 1 opt-in skip,
Pandu agent suite 105/105, frontend 637/637, with lint, types and build
green. In the live session (Internet Software Development, ~11 prompts),
greetings had no Course ID, grounded answers were accurate, follow-ups
stayed coherent, off-topic questions were refused, and with no material
checked Pandu asked for one instead of guessing. Non-blocking notes: one
unretried generic failure, two answers without citations, a duplicated
citation chip, plus bundle size and guide fixes.
```

---

## E. Sign-off

- Reviewer name: Gaurav
- Date: 2026-11-19
- Branch SHA reviewed (`git rev-parse HEAD`): `290c13acf361df946347df959f7839bc2ca0ea86`
- Time spent (approx.): automated checks ~5 min (backend ~2 min of tests); live session: ~5 min of tests

---

## F. Post-review follow-ups (owner)

Owner (Aashish) follow-ups after Gaurav’s `approve with notes` review
(2026-11-19). **Sections A–E above are unchanged** as the teammate’s
historical record. This section documents what the owner changed
afterward, which notes we reviewed and **kept as-is**, and one small
optional polish item still open.

### F0. Status at a glance

| # | Gaurav suggestion | Owner status | Where |
| --- | --- | --- | --- |
| 1 | Lazy-load ChatMarkdown / shrink main bundle | **Done** | `CourseChat.tsx`, `ChatMarkdown.test.tsx` |
| 2 | A4 `manage.py test` can bill Gemini / hit dev DB | **Done** (docs) | §A4 in this file |
| 3 | A1 hard-coded owner machine path | **Done** (docs) | §A1 in this file |
| 4 | Call out Node 24 / reject Node 22 | **Done** (docs; no `.nvmrc` yet) | Prerequisites in this file |
| 5 | Missing citation chips on some grounded answers | **Accepted — keep as-is** | citations deliberately optional (see F6) |
| 6 | Duplicate citation chip | **Open** (non-blocking polish) | optional UI dedupe later |
| 7 | Scope lets general Qs like `2+2` through | **Accepted — keep as-is** | harmless; true OOS still abstains (see F6) |
| 8 | Softer abstain wording | **Done** | `backend/apps/agent/pandu/loop.py` |

---

### F1. Lazy-load ChatMarkdown (suggestion 1) — Done

**Problem Gaurav reported.** Vite warned that the main JS chunk was
~863.77 kB (~257.54 kB gzip), over Vite’s soft 500 kB guideline.
`ChatMarkdown` pulls in `react-markdown`, remark plugins, `rehype-katex`,
and KaTeX CSS. A static import from course chat meant that stack was
bundled into the main download even on routes that never open Pandu.

**What we changed.**

- `frontend/src/components/chat/CourseChat.tsx`
  - Replaced `import ChatMarkdown from "./ChatMarkdown"` with
    `const ChatMarkdown = lazy(() => import("./ChatMarkdown"))`.
  - Wrapped the assistant bubble in `<Suspense>`.
  - **Fallback while the chunk loads:** plain `<p>{message.text}</p>`
    (plus streaming cursor if streaming) so the student still sees the
    reply immediately; Markdown/LaTeX replace it once the async chunk
    arrives.
- `frontend/src/components/chat/ChatMarkdown.test.tsx`
  - The `ChatMessageView` case is now `async` and uses
    `await screen.findByText("DFA")` instead of synchronous `getByText`,
    because the lazy chunk is not ready on the first paint.
  - Direct unit tests that import `ChatMarkdown` eagerly were left as-is.

**Build evidence (after change).**

```text
dist/assets/index-*.js           ~425 kB  (gzip ~126 kB)   ← main app shell
dist/assets/ChatMarkdown-*.js    ~438 kB  (gzip ~131 kB)   ← loaded on first assistant bubble
dist/assets/ChatMarkdown-*.css   ~30 kB   (gzip ~8 kB)
```

Vite’s main-chunk 500 kB warning is cleared. Markdown/math quality is
unchanged once the chunk is cached.

**What this does *not* change.** Pandu reply latency (backend + Gemini +
tools) is unchanged. This only affects first-load of non-chat pages and
the first time an assistant message needs Markdown rendering.

**Verification.** `cd frontend && npm test -- --run` → 60 files /
637 tests passed (includes ChatMarkdown + CourseChat).

---

### F2. Validation guide A4 / env risk (suggestion 2) — Done

**Problem Gaurav reported.** Optional §A4 told reviewers to run
`python manage.py test apps.agent.tests` under activated `backend/venv`.
That uses normal `config.settings`, which loads `backend/.env` and does
**not** strip `GEMINI_API_KEY` or force fake LLM backends the way
`scripts/check.py` does. A missing mock could therefore make **live,
billed Gemini calls** against the **dev database**.

**What we changed in this file (§A4).**

- Removed the `manage.py test apps.agent.tests` instructions.
- Added an explicit warning not to use that path for smoke testing.
- Directed reviewers to **§A1** (`scripts/check.py --component backend`),
  which uses isolated `config.test_settings`, strips API keys, and forces
  fake LLM backends. Agent suite (~105 tests) is covered inside A1; counts
  can be taken from `test-results/backend-all.xml`.
- Kept frontend-only smoke under A4 (`npm test`, `tsc`, lint, build).

**Not done in this pass.** Adding a dedicated `--suite agent` entry to
`scripts/check.py` `SUITES` (Gaurav’s alternate idea). A1 is enough for
reviewers; an agent suite remains a nice-to-have.

---

### F3. Hard-coded A1 path (suggestion 3) — Done

**Problem Gaurav reported.** §A1 began with
`cd /Users/aashishdhital20/Documents/studyforge`, which only works on the
owner’s machine.

**What we changed in this file (§A1).** Replaced that with “From the
**repository root** (wherever you cloned StudyForge):” and the same
`backend/venv/bin/python scripts/check.py …` command.

---

### F4. Node 24 prerequisites (suggestion 4) — Done (docs)

**Problem Gaurav reported.** `scripts/check.py` refuses Node below
24.15.0 (including Node 22). Reviewers on an older Node hit a hard error
without the guide explaining why. He also suggested a repo `.nvmrc` with
24.19.0.

**What we changed in this file (Prerequisites).**

- Stated **Node.js 24.15+**, CI/lockfile preference **24.19.0**.
- Explicitly noted that `scripts/check.py` **refuses Node 22**.
- Added an `nvm install 24.19.0 && nvm use 24.19.0` one-liner.

**Not done in this pass.** Adding a committed `.nvmrc` (still optional
follow-up).

---

### F5. Softer abstain wording (suggestion 8) — Done

**Problem Gaurav reported.** Out-of-scope replies used:

> I can help with your course materials, tasks, notes, and quizzes —
> not that kind of request.

He found “not that kind of request” curt.

**What we changed.** In `backend/apps/agent/pandu/loop.py`, the
`OUT_OF_SCOPE` branch of the agent loop now returns:

> That request is outside my current capabilities. I can help with
> course materials, academic questions, notes, tasks, and quizzes.
> Feel free to ask me anything related to your studies!

Behavior is unchanged (status still `abstain`, no tools). Only the
student-facing string changed. Restart / reload the Django process to
pick it up in a live session; ask an off-topic question (e.g. weather /
rock climbing) to confirm.

---

### F6. Reviewed suggestions we are keeping as-is (5, 7) + remaining polish (6)

We went through Gaurav’s remaining notes with the owner after the review.
For **missing citations** and **`2+2` scope**, we **deliberately decided to
keep current behavior** (no code change). Duplicate chips stay a small
optional polish item.

#### 5. Missing citation chips — Accepted / keep as-is

**What Gaurav saw.** Accurate answers such as “explain the exercises” and
“explain more” sometimes showed **no** source chip, so the student could
not click through to verify grounding.

**Owner decision.** Keep citations **optional**. We deliberately made
citation attachment non-mandatory after hard citation matching caused
bugs and blocked usable answers (RAG would fail or withhold a good reply
when exact cite validation failed). The salvage / allow-uncited path was
added so students still get a grounded answer when evidence exists but
cite shaping fails. Prefer **answer over empty/error** when the model
produced a useful reply; chips appear when citations validate cleanly.

Requiring a chip on every turn would undo that reliability fix. A later
enhancement could attach soft document/page hints without failing the
turn; that is **not** required for SCRUM-23 merge.

#### 7. Scope allows light general Qs (`2+2`) — Accepted / keep as-is

**What Gaurav saw.** “What is 2+2?” was answered (`2 + 2 = 4`) instead of
abstaining — the scope classifier let a general question through.

**Owner decision.** Keep as-is. That case is **harmless**. Truly unrelated
queries (e.g. rock climbing, elections / weather-style asks in the live
session) are still classified **OUT_OF_SCOPE** and abstain. Tightening
the classifier to refuse trivial arithmetic would add little product
value and risks false “unclear/out of scope” on borderline academic
phrasing. No scope-prompt change for SCRUM-23.

#### 6. Duplicate citation chip — Still open (non-blocking)

**What Gaurav saw.** “list options 6-8” showed
“Javascript Exercises.pdf · Page 2” **twice**.

**Owner note.** Cosmetic only; answer quality was fine. Optional later
dedupe of UI chips by `(document, page)`. Not blocking merge; no change
in this follow-up pass.

#### Transient Gemini failure (from Findings, not a suggestion #)

The unretried “what is a header?” → “Pandu couldn't finish…” reply was
already treated as likely transient Gemini 429/503 (B4). No product
change; retry once in future reviews / check server logs if it repeats.

---

### F7. Files touched in this follow-up pass

| File | Change |
| --- | --- |
| `docs/scrum-23-teammate-validation.md` | Fixed Prerequisites, §A1, §A4; added this §F report |
| `backend/apps/agent/pandu/loop.py` | New OUT_OF_SCOPE abstain copy |
| `frontend/src/components/chat/CourseChat.tsx` | `React.lazy` + `Suspense` for ChatMarkdown |
| `frontend/src/components/chat/ChatMarkdown.test.tsx` | Async wait for lazy assistant markdown |

Suggested commit split (by functionality): guide/docs, abstain copy,
lazy-load ChatMarkdown (+ test).
