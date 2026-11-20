# Curiosity Grade

## 1. Executive Summary

- Student: Sanish Shrestha
- Student ID: mpr92
- Assignment: SCRUM-53 — Survival Quiz testing and frontend panda feedback
- Session date: 2026-11-19
- Report assessed: [SCRUM-53 curiosity report](./curiosity-report-Shrestha-SCRUM-53-2026-11-19.md)

> Provisional assessment of the available record, not an official professor or Canvas grade. The capture is incomplete after the early UI discussion; later AI replies are unavailable. The scores below are based on the visible student questions and documented outcomes.

The student sought details about existing tests, answer grading, animation state, sprite mapping, and the local backend failure. They also specified several implementation and layout requirements. The private work note records frontend tests/build passing and backend test execution blocked by missing pytest.

## 2. Curiosity Rubric

### (i) Clarification / requests for detail — 3/3 (incisive)

**Evidence:** “are we generating answer as we go or are answer generated already and we just mathcing them”; “what did survivalpanda tsx collection of imamges”; “what is the dimension for each frame”.

**Depth justification:** Questions move from the quiz's answer-grading flow to concrete implementation and asset details needed to understand the feature.

**Ungraded event count:** 8.

### (ii) Challenge / skepticism [PRIORITY] — 3/3 (incisive)

**Evidence:** “you had it setup up frommleft to right 3 2 1 0 and you used tht what if there was 5 images but only 3 2 1 0”.

**Depth justification:** This tests whether the assumed frame-to-life mapping holds when the sprite contains more frames than the game has states.

**Ungraded event count:** 2.

### (iii) Why / tradeoffs — 2/3 (substantive)

**Evidence:** “surival coould have used that tsx but we did a diffenent motion” and “how did we put the panda image in our project”.

**Depth justification:** The questions examine component reuse and how generated assets connect to the implementation, though the available wording does not show a fuller cost/benefit comparison.

**Ungraded event count:** 4.

### (iv) Error-response behavior [PRIORITY] — 2/3 (provisional)

**Evidence:** The student reported “Backend unavailable. Failed to fetch” and asked “why is backend not available”.

**Depth justification:** The student reported an unexpected runtime failure and asked for its cause. Because the AI response sequence is missing, it is not possible to fully determine whether the student probed a proposed fix or accepted it.

**Error episodes:** 2 (PROBED 2, ACCEPTED 0, LOOPED 0), provisional; classification is limited by missing replies.

No composite score is calculated.

## 3. Notes for the Grader (neutral)

The visible questions focus on implementation details: test coverage, answer grading, animation states, frame selection, asset dimensions, and runtime setup. The student also gave specific incremental layout directions. Missing AI replies limit assessment of the back-and-forth around the runtime issue and implementation explanations.

## 4. AI Sycophancy — No grade impact

The supplied excerpt includes routine confirmation and an explicit statement that tests were not run at the time. Later AI replies are unavailable, so sycophancy or reversals in the rest of the session cannot be assessed.

## 5. Performativity (preliminary)

The available questions are tied to concrete feature behavior, including the case where five sprite frames map to four life states. They appear task-specific. This is a preliminary signal, not a definitive judgment of intent.

## 6. CSV score-row

Provisional assessment based on the available record; the numbers are not an official Canvas award.

~~~csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
mpr92,Sanish Shrestha,SCRUM-53,3,3,2,2,8,2,4,2,2,0,0,2026-11-19
~~~
