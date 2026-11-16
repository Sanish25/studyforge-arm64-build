# Curiosity Grade

- Report graded: `curiosity-report-Paneru-SCRUM-86-2026-11-15.md`
- Student: Gaurav Paneru · Student ID: gqq14 · Assignment: SCRUM-86 Advanced notes options and generation
- Self-context: none provided (it's optional)

## 1. Executive summary

Over 19 student turns (2026-11-14 to 2026-11-15 local time), the student directed an AI to plan and build SCRUM-86 in a Django/DRF and React project:
- **Options:** note type, detail level and format, chosen from fixed lists.
- **Prompt:** built from fixed fragments.
- **Storage:** the options are saved on the note, and source documents are stored as plain IDs following SCRUM-98.
- **Errors:** two separate 503 codes, one for an unavailable provider and one for unusable output.

The AI wrote the code, tests, commits and a teammate validation report. The student set the rules (fixed lists, no free text in the prompt, ask before editing, testing or committing) and made the decisions.

Their curiosity shows in four places:
- **Questions about how the system behaves:** with the plan rejection (turn 3), in a long follow-up (turn 7), and in turns 9 and 17.
- **Which branch owned a test failure after the rebase** (turn 27).
- **Reading their reviewer Sudin's findings back** (turn 31).
- **Asking for causes and how each fix solves them** (turn 33).

There are four error or unexpected-behavior episodes:
- Docker not starting.
- Two backend test failures on the first run.
- A SCRUM-79 test broken by this branch's change.
- Two problems from Sudin's live review.

The last one was finished by the student outside the session (*"i fixed the issue."*, turn 37).

## 2. Curiosity rubric (four raw numbers; no composite)

### (i) Clarification / requests for detail: **2 (substantive)**
- Evidence (turn 7): *"where does each note records its type? What actually happens when a user clicks a detail level? When does notes provider unavailable happen? and when does notes invalid output happen? Does these two error codes not implemented before? What do you mean by merge too large? What is the criteria? How much is too large?"*
- Evidence (turn 9): *"What is the fixed list that backend checks the value against?"*
- Evidence (turn 3): *"How is gemini model going to know for the detail_level? What is the difference between each detail_level?"*
- Why 2: the student picks up terms the AI introduced ("merge too large", the two new codes, the "fixed list") and asks for the exact mechanism, the trigger condition and the threshold. Turn 9 follows up on the answer in turn 8. The questions engage the AI's reasoning and narrow what they want explained. They ask for an explanation of the design rather than testing it, so the score is 2, not 3.
- Events (ungraded): 6 turns (3, 7, 9, 17, 31, 33).

### (ii) Challenge / skepticism [PRIORITY]: **2 (substantive)**
- Evidence (turn 27): *"so, the fix is of branch 79, not branch 86? If it is, suggest exactly which line on which file needs change for the code of branch 79. If it is my error because 79 is already merged, fix that line and rerun the tests."*
- Evidence (turn 17): *"Any edge cases that aren't tested yet?"*
- Evidence (turn 31): *"can you check if all the tests cases passed on his end? Whether or not this PR was approved? What were the problems ?"*
- Evidence (turn 35): the student dismissed the AI's request to make live OpenAI calls and said: *"I asked sudin to rerun the tests and commit the validation report one more time."* They chose to get evidence from the reviewer's run rather than let the AI test against a real provider.
- Supporting verification: the student requested test runs (*"Run the tests"*, turn 11; *"can you run backend tests now"*, turn 15; *"fix that line and rerun the tests"*, turn 27). The Evidence Appendix shows:
  - the full backend suite passing (716, then 723 after the SCRUM-79 fix);
  - each commit checked on its own in a separate worktree;
  - a regression test shown to fail without the frontend fix.

  An outside reviewer (Sudin) then ran the branch independently.
- Why 2: turn 27 questions where the AI placed the fix, covers both possible answers, and makes the AI justify its attribution. Turn 17 asks the AI to list the gaps in its own testing. Both check the AI's work rather than accept it. Neither directly disputes a claim with the student's own evidence, and the student accepted both answers, so the score is 2, not 3.
- Events (ungraded): 4 turns (17, 27, 31, 35).

### (iii) Why / tradeoffs: **2 (substantive)**
- Evidence (turn 3): *"Does more detail mean more tokens? Are the answers going to be same for the format and just difference in either points or paragraphs?"*
- Evidence (turn 17): *"For my clarity, the contents are saved as JSON, right? Give me simple answer on why ?"*
- Evidence (turn 33): *"Explain much better on why those problems occurred? And how your fix solves that problem."*
- Why 2: the student asks about cost (tokens per detail level), whether an option changes the content or only its layout, why a storage choice was made, and why a defect happened. Those are why-questions about the design's consequences. Six design decisions were presented with two options each, and the student chose the recommended option for all of them (*"A for D1, A for D2, A for D3, A for D4, A for D5, A for D6"*, turn 3) without asking about the alternatives. So the score is 2, not 3.
- Events (ungraded): 4 turns (3, 17, 27, 33).

### (iv) Error-response behavior [PRIORITY]: **2 (substantive)**
- Episode 1, Docker not starting (turns 13–15), **ACCEPTED**: *"why my docker is not starting?"* The student asked for a diagnosis, applied it, and reported *"now docker is up. can you run backend tests now."* They didn't engage with the reasoning. This is the same pattern as the Docker episode in the student's SCRUM-52 report, which was labelled ACCEPTED.
- Episode 2, two backend test failures on the first run (turn 16), **ACCEPTED**: the AI found and fixed a mock signature and an input size in a test. The student moved on to other questions without asking about either failure.
- Episode 3, the SCRUM-79 test failing after the rebase (turns 26–28), **PROBED**: turn 27 asks whose error it is (*"so, the fix is of branch 79, not branch 86? … If it is my error because 79 is already merged, fix that line"*). The question decides where the fix belongs.
- Episode 4, Sudin's review findings (turns 31–37), **PROBED**:
  - The student asked whether the tests passed on the reviewer's machine, whether the PR was approved, and what the problems were (turn 31).
  - They then asked for *"why those problems occurred? And how your fix solves that problem"* (turn 33).
  - They declined live provider calls, sent the branch back to the reviewer for a rerun (turn 35), and later reported fixing the remaining issue themselves (turn 37).
- Why 2: the two probed episodes involve real questioning: one about which branch owns the failure, one about the cause and how the fix works. The other two followed the first diagnosis or fix. That mix lands at 2. No episode shows a back-and-forth loop of fixes.
- **Error episodes: 4 (PROBED 2, ACCEPTED 2, LOOPED 0)**

## 3. Notes for the grader (neutral)

- **Where curiosity concentrated:** how the system behaves at runtime and its contracts:
  - how a detail level reaches the model;
  - token cost;
  - where options are stored;
  - when each 503 code fires and whether it is new;
  - the merge-size threshold;
  - which list values are validated against;
  - what happens on delete.

  The questions are tied to the artifact, and most come before testing and committing.
- **Where the student worked by approval:** the implementation and design decisions (all six D-options taken as recommended), the commit split (*"Propose how to split this into commits before committing."*, *"Propose how tests split per commit look like."*), and the validation report (*"make teammate validation report just like 52 for my reviewer."*). This describes how the work was divided; it isn't a deficiency.
- **An earlier warning that became a review finding (no grade impact):** in turn 18 the AI listed an untested risk: the notes view crashes if the frontend ships before the backend. It offered a fix in turns 18, 20 and 22. The student moved on to committing without answering whether to include it. Sudin's review later hit that exact crash. The student did ask the question that surfaced the risk (turn 17).
- **Process ownership (not scored):** the student set the rules up front (ask before editing, testing or committing; keep the scrum-52 report unstaged). They routed review through a teammate, and they declined live API calls when asked.

## 4. AI Sycophancy (no grade impact; for your awareness)

- **Held its ground under a challenge (positive).** In turn 27 the student asked whether the failing test belonged to the already-merged SCRUM-79 branch. The AI held its position that the fix belongs on SCRUM-86, and said why: *"SCRUM-79's test was correct against `development`, where the `source_documents` link still existed. My branch removes that link."*
- **Corrected itself without prompting (positive).** In turn 8 the AI wrote, *"My earlier summary made the 422 change sound more important than it is. If you'd rather keep the PR smaller, I can revert that part."*
- **Stated uncertainty plainly (positive).** For the live `NOTES_INVALID_OUTPUT` failure (turn 36), the AI presented its cause as unconfirmed (*"This is my most likely cause, but it's unconfirmed"*) and asked for the reviewer's log line. It did not claim a fix.
- **Did not overstate success (positive).** In turn 26 the AI declined to record a pass in the validation report while one test was failing: *"I don't want to send Sudin a report that says the branch passes when it currently doesn't."*
- No flattery phrases ("great question", "excellent", "you're right") were found. There was no instance of the AI giving in to an incorrect challenge.

## 5. Performativity (preliminary)

The questions are specific and tied to the artifact. They name exact error codes, environment thresholds, branch numbers and the reviewer's findings, and several have consequences: who owns a fix, whether to make live API calls, and asking for the cause and the fix's mechanism before accepting a fix. Some later turns are purely directive (commit, write a report), but nothing reads as asked for show. *This is a preliminary signal, not a definitive judgment of intent.*

## 6. CSV score-row

```csv
student_id,student_name,assignment,dim_i,dim_ii,dim_iii,dim_iv,events_i,events_ii,events_iii,err_episodes,probed,accepted,looped,date
gqq14,Gaurav Paneru,SCRUM-86 Advanced notes options and generation,2,2,2,2,6,4,4,4,2,2,0,2026-11-15
```
