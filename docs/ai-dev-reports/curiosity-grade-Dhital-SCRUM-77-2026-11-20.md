# Curiosity Grade

Source report: `curiosity-report-Dhital-SCRUM-77-2026-11-20.md`  
Student: Aashish Dhital (`wor21`) · Assignment: SCRUM-77 Persistent Pandu Chat History · Session date: 2026-11-20

## 1. Executive summary

Aashish closed SCRUM-77’s main gap (auto-inject prior turns for AC2), kept `recall_history` optional, capped history at 8 ANSWERED-only Q&A pairs, added AC6 persistence tests, authored a Nischal review guide, confirmed live AC2 on video after Nischal’s blocked clarify session, and resolved a CourseChat Send-without-READY test mismatch by reverting a READY-gate UI restore and updating the test to match optional-sources UX. Curiosity concentrated on failure-mode classification for vague follow-ups, citation-style non-blocking recall, pending/failed prompt inclusion, latency of always-inject, failed-ask edge cases, interpreting Nischal’s “no AC2 regression” wording, and challenging the READY-gate fix against remembered product behavior.

Self-context (OPTIONAL, ungraded): *(blank in report)*

## 2. Curiosity rubric

Four raw scores only — no composite / letter grade.

### (i) Clarification / requests for detail — **3**

**Quote (best instance):** “so currently “Give me an analogy for that” this is taken as out of conetxt scope or not enough knowledge ]?” (Transcript — after AC2 gap explanation).

**Depth justification:** Incisive clarification — forces a precise failure-mode classification (scope gate vs RAG insufficient vs lost referent) rather than a vague “explain more,” exposing that AC2 fails from missing antecedents, not those other paths.

**Supporting quotes:** “lets fill in the gaps we have for scrum 77: explain me more about the folow - up context (AC2 + scope #3)”; “Why do we include failed or pending messages? what does that exactly mean”; “READY gate what do you exacty mean by ready gate? and how is the agent gonna react give example”; “The live result does not establish an AC2 regression or a definitive cause. expalin this issue”.

**Ungraded event count:** (i) ~12 events

### (ii) Challenge / skepticism **[PRIORITY]** — **3**

**Quote (best instance):** “make sure to keep recall_history as an optional deeper lookback only if needed. it should not create bug like we had for itation: where it would not give reply w/o citation. is its theres goood, if not pandu should still be able to give ans” (Transcript — after auto-inject implementation).

**Depth justification:** Tests a consequential correctness claim against a known prior bug class (optional tool must not block replies); redirects hardening of prompts/evidence gate rather than accepting “recall stays available” as sufficient.

**Supporting quotes:** “the test was worng not the usua behavior i believe”; “so what was it like befor? because i remember being able to say hi but when i asked smth it asked me to attach the document”; “What if a student wants to continue a question that failed earlier? wghat does pandu responds”; “doesnt that make the agent slow?”.

**Supporting verification (Evidence Appendix, not a separate score):** Live Pandu demo (Separation Edges → “explain that more”); `CourseChat.test.tsx` vitest 16/16 after READY-gate revert + test update; backend AC6 suite reported covered.

**Ungraded event count:** (ii) ~6 events

### (iii) Why / tradeoffs — **3**

**Quote (best instance):** “doesnt that make the agent slow?” (Transcript — after learning prior turns always inject, not only on referential follow-ups).

**Depth justification:** Explicit cost/latency tradeoff on the always-inject design (not only “how do I implement history”), probing whether AC2 reliability is worth unbounded prompt growth; later knobs (limit 8, ANSWERED-only) follow from that concern.

**Supporting quotes:** “What if we tighten to just ANSWERED user +their assistant replies?”; “What if a student wants to continue a question that failed earlier? wghat does pandu responds”; “so if a query fails and i ask the same qn differnetly how does that work”; before/after READY-gate vs optional-sources product behavior discussion.

**Ungraded event count:** (iii) ~5 events

### (iv) Error-response behavior **[PRIORITY]** — **3**

**Quote (best instance):** “the test was worng not the usua behavior i believe” (Transcript — after READY-gate restore and recalling optional-sources “hi without document” UX).

**Depth justification:** On a real review/test mismatch, student challenged the applied UI fix with specific product memory, rejected aligning the product to a stale test, and redirected to update the test instead — deep probe, not report-and-accept.

**Supporting quotes:** “why am i not able to genrate notes”; “CourseChat.test.tsx Send-without-READY what was the issue he was facing”; “so what was it like befor? because i remember being able to say hi…”.

**Episode tally (genuine error / unexpected-behavior only; Section 3 eps 1–3):**  
`Error episodes: 3 (PROBED 3, ACCEPTED 0, LOOPED 0)`

| Ep | Student report | Label |
|----|----------------|-------|
| 1 | Could not generate notes — “why am i not able to genrate notes” | PROBED |
| 2 | Nischal review: blocked live AC2 clarify + failing `CourseChat.test.tsx` — asked for findings, AC2-regression wording, and “what was the issue” before fixing | PROBED |
| 3 | Challenged READY-gate restore after recalling optional-sources UX; asserted test was wrong | PROBED |

**Ungraded event count:** (iv) 3 episodes

### Scores (raw)

`(i) 3  (ii) 3  (iii) 3  (iv) 3`

## 3. Notes for the grader (neutral)

Curiosity concentrated on AC2 failure semantics (scope vs knowledge vs lost referent), optional `recall_history` vs citation-blocking risk, pending/FAILED in prompt context, inject latency/window size, failed-ask continue/rephrase behavior, Nischal review interpretation (blocked demo ≠ AC2 regression), and the READY-gate vs optional-sources product rule. Large stretches are implementation-by-approval (implement inject, set limit 8, commit summaries, review-guide edits, “are we done?”) without challenge — descriptive only. Post-review work shows product judgment (video proof for AC2; test updated to match optional sources after an initial READY-gate restore).

## 4. AI Sycophancy — No grade impact, for your awareness

- No strong “Great question!” / empty flattery patterns flagged as dominant; AI replies are mostly technical walkthroughs and status tables.
- **Correct student challenge / AI reversal:** after the student directed a READY-gate restore to match the failing test, then later recalled optional-sources “hi without document” and said the test was wrong, the AI agreed and reverted the UI while updating the test — correct reversal under a **CORRECT** student challenge.
- **Caveat (not flattery):** when the student first said “okay fix that” to restore the READY status string, the AI complied with that instruction; the temporary wrong product direction came from following the student’s then-stated fix, not from the AI inventing flattery. No observed case of the AI inventing agreement with an incorrect factual claim against clear evidence in the sampled turns.

## 5. Performativity (preliminary)

Questioning is largely **task-specific** (analogy failure-mode class, citation-style non-blocking recall, pending status semantics, inject latency, failed-ask edge cases, Nischal’s AC2 wording, READY gate vs remembered optional-sources UX). Depth tracks real product and review risks rather than generic “why?” loops. *This is a preliminary signal, not a definitive judgment of intent.*

## 6. CSV score-row

```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
wor21,Aashish Dhital,SCRUM-77,3,3,3,3,12,6,5,3,3,0,0,2026-11-20
```
