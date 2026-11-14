# Curiosity Grade

## 1. Executive Summary

- Student: Sanish Shrestha
- Student ID: mpr92
- Assignment: SCRUM-109 — Horizontal autoscaling and worker failure handling
- Session date: 2026-11-14
- Report assessed: [SCRUM-109 AI chat / curiosity report](./curiosity-report-Shrestha-SCRUM-109-2026-11-14.md)

> Assessment provenance: this is a provisional Codex-generated application of the repository's curiosity rubric, not an official professor grade or output from the configured Copilot/Claude grader. It is generated in the same working session that produced the report and should receive independent human review. Scores below are explicit qualitative judgments grounded in quoted student text, not test-derived measurements or imported teammate scores.

The report contains student messages covering queue semantics, Celery acknowledgement, database idempotency, Kubernetes replacement, KEDA thresholds, polling, cooldown behavior, phases, live failures, and reporting. The student's strongest curiosity was shown when distinguishing Redis delivery from database duplicate prevention, correcting an unsolicited file change, and requiring live evidence for scaling and recovery.

## 2. Curiosity Rubric

### (i) Clarification / requests for detail — 3/3 (incisive)

**Evidence:** The student asks, “redis will check for duplicacy and then send to a new worker what is happennig till now if worker fails” and later asks, “what is polling ineterval”.

**Depth justification:** The first question identifies a specific boundary error in the proposed design and asks what the current system actually does. The second separates queue polling from worker scale-down timing. These are consequential clarification requests tied to system behavior.

**Ungraded event count:** 8 selected clarification events.

### (ii) Challenge / skepticism [PRIORITY] — 3/3 (incisive)

**Evidence:** The student says, “i never told you to do it i asked you but anyway what happened now”. The student also asks for validation of “failed pods being replaced and whether the failed task are redeliversd through reddid or not and mainly no dupliccy”.

**Depth justification:** The student directly challenges an unauthorized repository mutation and requires evidence for the central reliability claims rather than accepting an implementation summary. The later request tests multiple independent failure properties.

**Supporting verification:** The evidence appendix records live KEDA scale testing, worker deletion, Redis redelivery, and database duplicate-result tests. These are supporting verification and do not create a separate score.

**Ungraded event count:** 6 selected challenge/verification events.

### (iii) Why / tradeoffs — 3/3 (incisive)

**Evidence:** The student asks, “why do we need a cooldown period for” and later asks, “why did you make a checklist in this way is it a better way or efficeint way”. The student also asks whether keeping five workers would “take memory unnnecesary”.

**Depth justification:** These questions probe operational tradeoffs: worker churn versus warm capacity, process structure versus execution efficiency, and resource cost versus availability. They redirect the implementation toward phased reliability work and measured autoscaling.

**Ungraded event count:** 7 selected why/tradeoff events.

### (iv) Error-response behavior [PRIORITY] — 3/3 (incisive)

**Evidence:** After the test could not run, the student asks, “why could you nor run the test why was it not installed”. After live validation, the student asks, “why 3 skipped” and “what do you mena live”. The student also corrects the AI after the unsolicited change: “i never told you to do it”.

**Depth justification:** The student repeatedly asks for causes and scope when behavior differs from expectation, distinguishes skipped tests from passed tests, and challenges the assistant's action boundary. The transcript shows the student redirecting the work toward actual integration evidence.

**Error episodes scored:** 10 (PROBED 7, ACCEPTED 3, LOOPED 0).

| Episode | Transcript pointer | Classification and evidence |
| --- | --- | --- |
| System Python lacked Django | Report Episode 1 | PROBED: asks why the test could not run and why the dependency was absent. |
| PostgreSQL/Docker unavailable | Report Episode 2 | PROBED: explicitly requests database and two-worker tests and asks for successes and failures. |
| Unsolicited Phase 2 edits | Transcript near “i never told you to do it” | PROBED: challenges the action and asks what happened. |
| KEDA scale semantics | Transcript near “what is polling ineterval” | PROBED: requests the distinction between polling and cooldown behavior. |
| KEDA/cluster setup failures | Report Episode 3 | ACCEPTED: continues after explanations without independently proposing an alternative. |
| Redis probe timeout | Report Episode 4 | ACCEPTED: accepts the longer observation window after the reported timeout. |
| Missing packaging dependency | Report Episode 7 | ACCEPTED: allows the proposed dependency fix and rebuild. |
| Concurrency mismatch | Report Episode 8 | PROBED: requires the scaling target to match actual worker workload. |
| Synthetic queue test flaw | Report Episode 9 | PROBED: requests a test that makes the behavior sure; the failed test was corrected. |
| Skipped live tests | Transcript near “why 3 skipped” | PROBED: asks what the test mode means and why checks were skipped. |

**Ungraded event count:** 10 assessable error or unexpected-behavior episodes.

**Four raw scores:** (i) 3, (ii) 3, (iii) 3, (iv) 3. No composite, weighting, or course letter grade is calculated.

## 3. Notes for the Grader (neutral)

Curiosity concentrated on reliability semantics, operational tradeoffs, and
verification evidence. The student used short and informal wording, but several
questions were consequential and redirected implementation decisions. The
student also explicitly corrected an AI action that exceeded the request scope.
The grade uses the student's observable chat behavior; teammate feedback and
live test evidence are not treated as proof of internal understanding.

## 4. AI Sycophancy — No grade impact, for your awareness

The AI frequently used affirmative language such as “Yes” and “Correct,” but the
selected exchanges do not show the AI agreeing to a false technical claim after
an incorrect student challenge. The AI correctly corrected the Redis duplicate
misconception by stating that Redis does not check database duplicacy. The AI
also acknowledged the scope error after the student said, “i never told you to
do it”. This section has no effect on the four scores.

## 5. Performativity (preliminary)

The student's questions are tied to concrete implementation behavior: queue
length, cooldown, worker failure, Redis acknowledgement, duplicate persistence,
test skips, and unauthorized edits. The questioning appears specific and
consequential rather than merely performative. This is a preliminary signal, not
a definitive judgment of intent.

## 6. CSV score-row

Provisional Codex assessment only; the numbers below match the quoted-evidence
judgments above. They are not an official Canvas award or a substitute for the
professor's review.

```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
mpr92,Sanish Shrestha,SCRUM-109,3,3,3,3,8,6,7,10,7,3,0,2026-11-14
```
