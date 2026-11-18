# Curiosity Grade

## 1. Executive Summary

- Student: Sanish Shrestha
- Student ID: mpr92
- Assignment: SCRUM-130 — Gemini-primary OpenAI fallback
- Session date: 2026-11-17
- Report assessed: [SCRUM-130 AI chat / curiosity report](./curiosity-report-Shrestha-SCRUM-130-2026-11-17.md)

> Assessment provenance: this is a provisional Codex-generated application of the repository's curiosity rubric, not an official professor grade or output from a configured external grader. It is generated in the same working session as the report and should receive independent human review.

The student asked about provider roles, phased implementation, private change tracking, per-request isolation, embeddings, cost, telemetry, and failure behavior. The student repeatedly corrected scope and clarified that OpenAI is a fallback rather than a replacement. The student also required tests for each phase and made a reasoned decision to defer embedding fallback after learning that separate vector storage would be required.

## 2. Curiosity Rubric

### (i) Clarification / requests for detail — 3/3 (incisive)

**Evidence:** The student asks, “what if gemini can still generate note” and “what will we accmplish in our phase 3”.

**Depth justification:** These questions clarify per-feature provider behavior and phase deliverables rather than accepting a global provider switch.

### (ii) Challenge / skepticism [PRIORITY] — 3/3 (incisive)

**Evidence:** The student asks, “u ony chaned the test file ddid you change the actual cod e” and states, “fallback is intened for failure and not actual replacement got it”.

**Depth justification:** The student checks whether implementation claims match production code and explicitly constrains the architectural role of the fallback.

### (iii) Why / tradeoffs — 3/3 (incisive)

**Evidence:** The student asks whether usage is greater when Gemini fails before OpenAI than when sending directly to OpenAI, asks which model strategy is most cost effective, and decides not to add embedding fallback after learning the storage and index cost.

**Depth justification:** These questions connect provider selection to cost, latency, vector compatibility, and scope.

### (iv) Error-response behavior [PRIORITY] — 3/3 (incisive)

**Evidence:** The student asks what happens when OpenAI also fails and requests verification that Gemini fallback is actually sent to OpenAI.

**Depth justification:** The student distinguishes primary failure from terminal double failure and requires tests that observe the actual handoff.

**Four raw scores:** (i) 3, (ii) 3, (iii) 3, (iv) 3. No composite, weighting, or course letter grade is calculated.

## 3. Notes for the Grader (neutral)

The student's questions focused on provider boundaries, request isolation, cost, test evidence, and the consequences of adding embedding fallback. The student used informal wording but repeatedly redirected implementation toward per-request behavior and verification. The final scope decision deferred embedding fallback after considering the separate vector-space requirement.

## 4. AI Sycophancy — No grade impact, for your awareness

The AI frequently confirmed the student's framing. The transcript also includes substantive corrections: generation fallback was distinguished from embedding fallback, OpenAI was described as a backup rather than a replacement, and the private-file location was corrected to match the repository convention. This section has no effect on the four scores.

## 5. Performativity (preliminary)

The student's questions were tied to concrete code and operational behavior: provider selection, unchanged request arguments, failure classification, telemetry, usage, vector indexes, and test results. The questioning appears consequential and implementation-directed rather than merely performative. This is a preliminary signal, not a definitive judgment of intent.

## 6. CSV score-row

Provisional Codex assessment only; the numbers below match the quoted-evidence judgments above. They are not an official Canvas award or a substitute for the professor's review.

```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
mpr92,Sanish Shrestha,SCRUM-130,3,3,3,3,8,7,7,3,3,0,0,2026-11-17
```
