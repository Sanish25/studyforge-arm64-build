# Curiosity Grade

## Executive Summary
The student explored SCRUM-127 through questions about S3/database consistency, orphan cleanup, worker retry and recovery behavior, duplicate processing, readiness, observability, rollback, and production verification. The student supplied the ticket’s scope and acceptance criteria, then used concrete failure scenarios to probe how the implementation behaves. The strongest evidence is in challenge/tradeoff questions about missing recovery mechanisms and in follow-ups about persistence and failure handling. The report records no observed errors or tests, so error-response behavior had no opportunity to be assessed.

## Curiosity Rubric

### (i) Clarification / requests for detail — 2
**Evidence (Transcript, Student turn 11):** “If the worker finishes processing but Django is down, what happens to all that work? Does it have to process the whole PDF again?”

**Depth:** This follows the earlier discussion of worker/S3 failures and asks for the consequential recovery behavior; substantive follow-up, but not a direct test of the answer’s correctness.

**Ungraded event count:** 12 turns with substantive clarification or detail-seeking questions.

### (ii) Challenge / skepticism — 3
**Evidence (Transcript, Student turn 8):** “Why don't we have a retry button for failed documents then? Wouldn't it be easier than making students upload the same PDF again?”

**Depth:** The student questions a missing recovery feature and tests the design against the student experience, pressing beyond the initial explanation of bounded automatic retries.

**Ungraded event count:** 3 turns that challenged an omission or asked for production-readiness verification.

### (iii) Why / tradeoffs — 3
**Evidence (Transcript, Student turn 15):** “If we deploy SCRUM-127 and something goes wrong with S3, can we switch back to local storage without losing access to the PDFs already uploaded?”

**Depth:** This probes a consequential alternative and its data-consistency implications, rather than asking only how to configure S3.

**Ungraded event count:** 4 turns asking why a design choice was made or probing alternatives and tradeoffs.

### (iv) Error-response behavior — N/A — no error episodes (no opportunity to observe)
**Evidence:** The report’s Section 3 states, “None observed.” The student asked hypothetical failure questions, such as “What happens if the processing worker loses connection to S3 while reading a PDF,” but did not report an observed error, failing test, or unexpected behavior.

**Ungraded event count:** 0 genuine error episodes.

**Episode tally:** Error episodes: 0 (PROBED 0, ACCEPTED 0, LOOPED 0).

## Notes for the Grader (neutral)
Curiosity concentrated on reliability and operational recovery: database/object-storage consistency, orphan cleanup, retrying existing uploads, callback loss, duplicate workers, monitoring, and rollback. The student also provided the SCRUM-127 acceptance criteria and asked what evidence would be required before production readiness. The session remained explanatory; the report records no code changes or validation runs by the student. Event counts above are descriptive turn-level counts; categories may overlap.

## AI Sycophancy — No grade impact, for your awareness
The assistant used mild validation: “So your intuition is right: this is a useful recovery feature.” This is brief affirmation, not substantial flattery or over-praise. No instance was observed where the assistant conceded an incorrect claim under challenge. It continued to distinguish existing automatic retries from a missing manual retry endpoint, stating that “there’s no user-facing or public API action to restart it.”

## Performativity (preliminary)
The questions are specific to the described system and build on prior answers—for example, distinguishing a Django-to-S3 failure from Django being down, and asking whether a local-storage rollback preserves post-cutover PDFs. This reads as substantive, scenario-based questioning rather than generic prompts. *This is a preliminary signal, not a definitive judgment of intent.*

## CSV score-row
```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
oeo36,Sudin Katuwal,SCRUM-127 - Production File Storage and Service Connections,2,3,3,NA,12,3,4,0,0,0,0,2026-11-15
```
