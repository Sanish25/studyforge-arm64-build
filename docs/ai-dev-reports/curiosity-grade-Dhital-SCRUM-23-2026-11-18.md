# Curiosity Grade

Source report: `curiosity-report-Dhital-SCRUM-23-2026-11-18.md`  
Student: Aashish Dhital (`wor21`) · Assignment: SCRUM-23 — Pandu agent loop with tool calling and course awareness · Session date: 2026-11-18 (append through 2026-11-19)

## 1. Executive summary

Aashish built SCRUM-23 end-to-end (ConversationMessage, `apps/agent/pandu`, tools, hybrid scope, HTTP endpoint, course-chat wiring) across a long transcript (~100 student turns) plus a 2026-11-18 continuation and a 2026-11-19 post-Gaurav-review append. Work included live Gemini failures, Markdown/LaTeX rendering, uncited RAG salvage, Course-ID leakage, hallucinated `conversation_id` tool failures, a teammate validation guide, then follow-ups (guide A1/A4/Node, softer abstain, lazy-loaded ChatMarkdown). Notable curiosity: challenging whether empty/failed answers were scope vs Gemini limits, testing uncited-answer hallucination risk, asking how materials are still found after stripping course IDs from the model payload, probing tool-failure UX, and weighing lazy-load tradeoffs against reply latency and SE practice before implementing.

Self-context (OPTIONAL, ungraded): *(blank in report)*

## 2. Curiosity rubric

Four raw scores only — no composite / letter grade.

### (i) Clarification / requests for detail — **3**

**Quote (best instance):** “now explain each of what you did one by one and why was it necessary or not necessary” (Transcript — after agent scaffold slice).

**Depth justification:** Incisive clarification — not a bare “explain,” but a demand to discriminate necessary vs unnecessary pieces of the scaffold, forcing engagement with the AI’s design rationale.

**Supporting quote:** “i still dont get it completely” (after ATOMIC_REQUESTS explanation); “1. Lazy-load ChatMarkdown… now for this help me understand this even better”; “ChatMarkdown.test.tsx explain code change”.

**Ungraded event count:** (i) ~18+ events

### (ii) Challenge / skepticism **[PRIORITY]** — **3**

**Quote (best instance):** “since now from_sources allows answers without citations, how do we prevent Pandu from giving unsupported or hallucinated answers?” (Transcript — after RAG / `allow_uncited` tools).

**Depth justification:** Tests a consequential safety claim (uncited ≠ invent); redirects the AI to justify grounding constraints rather than accepting the feature as safe by default.

**Supporting quotes:** “also if we remove course IDs from Gemini's input, how does it know which course materials to search?”; “Vite’s soft guideline is ~500 kB is this standard?”; “does that make the chatbopt render faster does that have any impact on getting reply faster”; “is this because of gemini limit?”; “the pandu is not able to give me the answers. is it because of scope prompt or something else? check”.

**Supporting verification (Evidence Appendix, not a separate score):** Live `ask_course_question` diagnose; frontend `npm test` 637/637; `npm run build` chunk split; loop/RAG targeted tests after fixes.

**Ungraded event count:** (ii) ~10 events

### (iii) Why / tradeoffs — **3**

**Quote (best instance):** “isnt it better to let the AI decide when to save conversation history instead of sabing every turn ? or is that too much of llm call?” (Transcript — memory / history slice).

**Depth justification:** Explicit alternative + cost tradeoff (model-gated saves vs always-persist), not only “how do I implement save.”

**Supporting quotes:** “also is adding a seperate pagent pandu app better than add9ng onto conversation that alrewady exst? why”; “whats the pros and cons” (lazy-load); “whast the sandard software engineering practice”; “isn that too much load for db?”; “for still open… we delberately made citation optional because we were getting bugs and not getting ans. and 2+2 was harmless as other completely unrealed quesries are declared out of scope” (weighs reliability vs citation completeness and scope strictness).

**Ungraded event count:** (iii) ~12 events

### (iv) Error-response behavior **[PRIORITY]** — **3**

**Quote (best instance):** “ask_course_question failed · Used list_courses · Used list_materials · ask_course_question failed · retrieve_chunks failed do not mention what failed in this technically. also why did it failed?” (Transcript — continuation after conversation-session / tool-failure UI).

**Depth justification:** On a live failure, student both redirects product UX (“do not mention what failed… technically”) and asks **why** it failed — probing cause rather than only requesting a patch.

**Supporting quotes:** “the pandu is not able to give me the answers. is it because of scope prompt or something else? check”; “is this because of gemini limit?” (UI “couldn't finish…” / still answering).

**Episode tally (genuine error / unexpected-behavior only; Section 3 eps 1–6):**  
`Error episodes: 6 (PROBED 4, ACCEPTED 2, LOOPED 0)`

| Ep | Student report | Label |
|----|----------------|-------|
| 1 | Agent unit test failed (`CourseNotes` / `source_documents`) — “it failed?” | ACCEPTED (reported; deferred fix to reviewer path) |
| 2 | Pandu not answering greeting — “is it because of scope prompt or something else?” | PROBED |
| 3 | Raw Markdown / `ask_course_question` failures — asked to fix | ACCEPTED |
| 4 | “Pandu couldn't finish…” / still answering — “is this because of gemini limit?” | PROBED |
| 5 | Greeting leaked Course ID — “do not mention course id” | PROBED |
| 6 | “conversation session could not be found” + failed-tool spam — “also why did it failed?” | PROBED |

Section 3 “Episode 7–8” (Gaurav review follow-ups / keep-as-is decisions) are **not** counted as error episodes for (iv).

**Ungraded event count:** (iv) 6 episodes

### Scores (raw)

`(i) 3  (ii) 3  (iii) 3  (iv) 3`

## 3. Notes for the grader (neutral)

Curiosity concentrated on architecture boundaries (hybrid agent vs conversations), RAG grounding / uncited risk, live Gemini vs product-bug diagnosis, ownership of course context after stripping IDs from the model payload, and post-review performance tradeoffs (lazy-load). Large stretches of the transcript are implementation-by-approval (implement X, commit summary, next slice) without challenge — descriptive only. Post-Gaurav append shows product judgment (keep optional citations; keep harmless `2+2`) after reading review notes.

## 4. AI Sycophancy — No grade impact, for your awareness

- No strong “Great question!” / empty flattery patterns flagged as dominant in sampled AI turns; replies are mostly technical.
- **Correct student challenges held / addressed:** hallucination risk under `allow_uncited`; Course-ID leak; tool-failure UX; scope vs Gemini-limit hypotheses — AI diagnosed and fixed rather than dismissing.
- **No observed case** of the AI caving to an **incorrect** student factual challenge in the sampled error/design turns (e.g. student hypothesized Gemini limit / scope; AI checked evidence and explained).

## 5. Performativity (preliminary)

Questioning is largely **task-specific** (schema storage, hallucination under uncited answers, course-id vs materials lookup, Gemini vs scope, lazy-load vs reply latency, SE practice before implementing). Depth tracks real product risks rather than generic “why?” loops. *This is a preliminary signal, not a definitive judgment of intent.*

## 6. CSV score-row

```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
wor21,Aashish Dhital,SCRUM-23,3,3,3,3,18,10,12,6,4,2,0,2026-11-19
```
