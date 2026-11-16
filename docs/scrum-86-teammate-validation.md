# SCRUM-86 Teammate Validation Report

## Report purpose

This report records an independent teammate's experience running and reviewing
the SCRUM-86 branch. The branch lets a student generate one set of notes from
several processed documents and choose how the notes are written: the note
type, the detail level and the format.

The teammate's feedback is the most important result. Record every problem they
encounter, including setup failures, unclear instructions, unexpected output,
slow behavior, missing prerequisites, and concerns about the design. Do not mark
the report complete only because automated tests pass.

## Review status

- Reviewer: Sudin
- Report status: in progress; Sudin's findings are recorded, but the manual checks and final recommendation are incomplete.
- Overall result: pending; a cause of the live generation failure (summary notes omitting `key_concepts`) has been found and fixed, but Sudin has not retested.
- Final recommendation: pending Sudin's recommendation and a follow-up validation run.

## Branch under review

```text
feature/SCRUM-86-advanced-notes
```

Commits, oldest first:

```text
e9731ee feat(SCRUM-86): add note options and per-type checks to notes validation
37887ca feat(SCRUM-86): build the notes prompt from fixed option fragments
550cece feat(SCRUM-86): generate provider notes with the chosen options
5a6f4eb feat(SCRUM-86): make the fake notes LLM reflect every option
650f062 feat(SCRUM-86): store note sources as plain document ids
255a266 feat(SCRUM-86): accept, save and return note options in the notes API
c3c4caf feat(SCRUM-86): return a separate error code for each notes failure
04d5787 feat(SCRUM-86): add note type, detail level and format choices to the notes form
e6a3cb0 feat(SCRUM-86): show the options used and render paragraph notes as prose
7994cdd feat(SCRUM-86): explain each notes failure code to the student
4ca3a2b docs(SCRUM-86): document note options, storage and AI error codes
8340ae7 docs(SCRUM-86): add teammate validation report
3d2e28c docs: add Sudin's SCRUM-86 PR review findings
65d25db fix(SCRUM-86): record validation and diagnose notes output
```

The hashes are from after the branch was rebased onto `origin/development`
(`9826d74`) on 2026-11-15.

## What this branch does

- Adds three options to notes generation, each from a fixed list:

  | Option | Values | Default |
  |---|---|---|
  | `note_type` | `summary`, `outline`, `key_concepts` | `outline` |
  | `detail_level` | `brief`, `standard`, `detailed` | `standard` |
  | `format` | `bullets`, `paragraphs` | `bullets` |

  The defaults match the notes generated before this branch.
- Each option value selects a fixed paragraph of instructions in the AI prompt.
  The student never types anything into the prompt; any value outside the
  lists is `400` before the AI is called.
- Every batch and the final merge of a large selection use the same prompt, so
  merged notes keep the chosen options.
- Validates the AI output against the chosen note type. Key-concepts notes need
  concepts in every section, outline sections need points, and a summary may
  have no key concepts.
- Saves the chosen options on each note and returns them as `"options"`.
- Stores each note's source documents as plain document IDs in a new
  `NoteSource` table, with no foreign key to `Document`. This is the SCRUM-98
  pattern. Migration `0003` copies existing notes' sources and gives existing
  notes the default options.
- Splits AI failures into two `503` codes, `NOTES_PROVIDER_UNAVAILABLE` and
  `NOTES_INVALID_OUTPUT`. They replace `NOTES_GENERATION_FAILED`. Nothing is
  saved on either, and the selected documents stay `READY`.
- Returns `422 NOTES_INPUT_TOO_LARGE` when the partial notes from a large
  selection are too large to merge. Before this branch that was a generic `503`.
- Adds three option groups to the notes form, shows the options used on each
  note, and shows bullet notes as a list and paragraph notes as prose.

Endpoints (both existed before; the request and response gain options):

```text
POST /api/v1/courses/{course_id}/notes/   generate and save notes
GET  /api/v1/notes/{notes_id}/            read saved notes back
```

Request example:

```json
{"document_ids": [12, 13], "note_type": "summary", "detail_level": "brief", "format": "paragraphs"}
```

Expected results:

```text
Two READY documents, default options               -> 201, options outline/standard/bullets
Same documents, note_type summary                   -> 201, one "Main themes" section (fake LLM)
note_type "essay" or detail_level "Brief"           -> 400, nothing saved, AI not called
No document_ids                                     -> 400 "Select at least one material."
A document that is not READY                        -> 409 DOCUMENT_NOT_READY with its id
Another student's document                          -> 404, nothing saved
AI backend misconfigured or down                    -> 503 NOTES_PROVIDER_UNAVAILABLE, nothing saved
```

## Main files touched

- `backend/apps/notes/llm/base.py`
  - `NoteOptions`, the option lists, per-type validation, and
    `NotesMergeTooLargeError`. A section that omits `key_concepts` or `points`
    is read as an empty list; a value of the wrong type is still rejected.
- `backend/apps/notes/llm/prompts.py` (new)
  - The base notes prompt plus one fixed fragment per option value.
- `backend/apps/notes/llm/provider.py`
  - Builds the prompt from the options. The "output too short" retry
    thresholds depend on the detail level, so correct brief notes are not
    rejected. Each rejected attempt logs a `Notes output rejected` warning with
    the phase, attempt number, options and validation reason, but never the
    model's text or the student's material.
- `backend/apps/notes/llm/fake.py`
  - The fake LLM's output changes visibly with each option.
- `backend/apps/notes/models.py`, `migrations/0003_note_options_and_sources.py`
  - Option columns on `CourseNotes`, the `NoteSource` table, the data copy, and
    removal of the old many-to-many link.
- `backend/apps/notes/services.py`, `selectors.py`, `serializers.py`,
  `views.py`, `signals.py`
  - Options in and out of the API. The note and its sources are saved in one
    transaction. Source names are looked up scoped to the owner. Material
    deletion now finds notes by ID. The two `503` codes and the `422`.
- `backend/apps/notes/tests/test_note_prompts.py` (new),
  `backend/apps/notes/tests/test_note_options.py` (new),
  `backend/apps/notes/tests/test_course_notes.py` (updated)
- `backend/tests/documents/test_scrum79_cleanup.py` (updated)
  - SCRUM-79, merged into `development` while this branch was open, built its
    deletion test on the old `source_documents` link. The test now creates the
    note's source as a `NoteSource` row. What it checks is unchanged: deleting
    a material deletes the notes built from it.
- `frontend/src/types/notes.ts`, `frontend/src/api/notes.ts`
  - Option lists with labels and help text; options sent with the request.
- `frontend/src/components/notes/NotesSetup.tsx`, `NotesPanel.tsx`,
  `NotesView.tsx`, `frontend/src/styles/course-workspace.css`
  - The option groups, error messages, and rendering by format. `NotesView`
    falls back to the default options when a response has no `options` field.
- `frontend/src/components/notes/NotesPanel.test.tsx`,
  `frontend/src/api/notes.test.ts`
- `docs/notes-api.md`
  - Options, storage, error codes and retry thresholds.

## Prerequisites

- Python 3.12 and the repository's `backend/venv` with dependencies installed.
- Node with `frontend/node_modules` installed (`npm ci` in `frontend`).
- Docker Desktop running Linux containers, for the isolated test database and
  the local Postgres used by manual checks.
- `curl` and `jq`, or Postman, for the manual API checks.
- Two local student accounts. Student A needs a course with at least two
  `READY` documents. Student B needs a course with one `READY` document.

The tests use the fake notes generator and do not call a paid model provider.
`scripts/check.py` sets `NOTES_LLM_BACKEND=fake` and `QUIZ_LLM_BACKEND=fake` and
removes provider API keys. Database-backed tests use a disposable database; do
not point them at a development database.

## Local setup

From the repository root:

```bash
git fetch origin
git checkout feature/SCRUM-86-advanced-notes
docker compose up -d
```

For the manual checks, apply the migration and start the backend with the fake
generator:

```bash
cd backend
NOTES_LLM_BACKEND=fake venv/bin/python manage.py migrate
NOTES_LLM_BACKEND=fake venv/bin/python manage.py runserver
```

In a second terminal, start the frontend:

```bash
cd frontend
npm run dev
```

Log in with `POST /api/v1/auth/token/` (`email`, `password`) and send the
returned `access` token as `Authorization: Bearer <token>`.

The fake generator makes each option easy to see:

- `summary` returns a single section headed `Main themes`.
- `key_concepts` returns sections with concepts and no points.
- `brief`, `standard` and `detailed` give 1, 2 and 4 points per section.
- `paragraphs` points are three sentences each, starting `Fake paragraph`.

If `docker info` hangs or the engine never starts, quit every Docker process
and start a single copy of Docker Desktop. If Docker keeps its disk image on an
external drive, check that the drive is mounted under the same name as before.

## Validation commands

Run the AI-learning suite, which includes every notes test:

```bash
backend/venv/bin/python scripts/check.py \
  --component backend --suite ai-learning
```

Run the full backend check (system checks, migration drift, fresh migrations,
all backend tests):

```bash
backend/venv/bin/python scripts/check.py --component backend
```

Run the frontend checks:

```bash
cd frontend
npm run lint
npx vitest run
npm run build
```

Run the manual API checks. Replace the `<...>` values from earlier responses:

```bash
API=http://localhost:8000/api/v1
A=$(curl -s -X POST $API/auth/token/ -H 'Content-Type: application/json' \
  -d '{"email":"<student A email>","password":"<password>"}' | jq -r .access)

# 1. List student A's documents and note two READY ids
curl -s $API/courses/<course_id>/documents/ -H "Authorization: Bearer $A" | jq

# 2. Generate notes from two documents with chosen options
curl -s -X POST $API/courses/<course_id>/notes/ \
  -H "Authorization: Bearer $A" -H 'Content-Type: application/json' \
  -d '{"document_ids":[<doc_1>,<doc_2>],"note_type":"summary","detail_level":"brief","format":"paragraphs"}' | jq

# 3. Same documents, different options (compare sections with step 2)
curl -s -X POST $API/courses/<course_id>/notes/ \
  -H "Authorization: Bearer $A" -H 'Content-Type: application/json' \
  -d '{"document_ids":[<doc_1>,<doc_2>],"note_type":"key_concepts","detail_level":"detailed","format":"bullets"}' | jq

# 4. Read a saved note back
curl -s $API/notes/<notes_id>/ -H "Authorization: Bearer $A" | jq

# 5. Invalid option, no documents, and another student's document
curl -s -X POST $API/courses/<course_id>/notes/ -H "Authorization: Bearer $A" \
  -H 'Content-Type: application/json' -d '{"document_ids":[<doc_1>],"note_type":"essay"}' | jq
curl -s -X POST $API/courses/<course_id>/notes/ -H "Authorization: Bearer $A" \
  -H 'Content-Type: application/json' -d '{"document_ids":[]}' | jq
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/courses/<course_id>/notes/ \
  -H "Authorization: Bearer $A" -H 'Content-Type: application/json' \
  -d '{"document_ids":[<doc_1>,<student B doc id>]}'
```

To check the provider-unavailable path, restart the backend with a backend that
has no API key, repeat step 2, and confirm `503 NOTES_PROVIDER_UNAVAILABLE` and
that no new note exists:

```bash
NOTES_LLM_BACKEND=gemini GEMINI_API_KEY= venv/bin/python manage.py runserver
```

The invalid-output path (`NOTES_INVALID_OUTPUT`) cannot be triggered with the
fake generator. It is covered by automated tests E12, E13 and P10. When it
happens with a real backend (`openai` or `gemini`), the runserver terminal
shows two warnings like this, one per attempt:

```text
Notes output rejected: phase=batch attempt=1 options=outline/standard/bullets reason=Model did not return JSON
```

Record the `phase` and `reason` lines in the evidence section. They contain no
model output or document text.

In the browser, open a course's Notes tab as student A, select two documents,
generate notes with different options, and confirm the form, the options
caption on each note, and the bullet and paragraph layouts.

## Test cases

### Generator options — `backend/apps/notes/tests/test_note_prompts.py` (14)

| # | Test | What it proves |
|---|---|---|
| P1 | `test_unknown_option_values_are_refused` | `NoteOptions` rejects values outside the lists |
| P2 | `test_every_option_value_has_a_fragment` | Every option value has prompt text |
| P3 | `test_the_prompt_carries_exactly_the_chosen_fragments` | For all 18 combinations, the prompt contains the chosen fragments and no others |
| P4 | `test_every_combination_gets_its_own_prompt_within_budget` | 18 different prompts, each under 5,000 characters |
| P5 | `test_key_concepts_notes_need_concepts_in_every_section` | A key-concepts section without concepts is invalid |
| P6 | `test_outline_sections_need_points` | An outline section without points is invalid |
| P7 | `test_a_summary_may_have_no_key_concepts` | A summary may omit concepts but not leave a section empty |
| P8 | `test_batches_and_merge_all_use_the_chosen_prompt` | Every batch call and the merge call get the same prompt |
| P9 | `test_brief_notes_are_not_mistaken_for_skimmed_output` | Output of about 1.3% passes for brief and fails for standard |
| P10 | `test_invalid_json_reports_retry_without_logging_model_text` | Invalid JSON is retried once; each attempt logs its phase, attempt and options; neither the logs nor the error contain the model's text (added in `65d25db`) |
| P11 | `test_each_option_changes_the_output` | The fake LLM's sections change with each option |
| P12 | `test_the_output_matches_what_each_option_promises` | Summary, key-concepts, detail and paragraph output look as described |
| P13 | `test_an_omitted_list_counts_as_empty_but_a_wrong_type_does_not` | A summary section without `key_concepts`, or a key-concepts section without `points`, is valid; `null`, a string, or a section with neither list is still invalid (problem 2) |
| P14 | `test_the_prompt_asks_for_empty_lists_instead_of_missing_keys` | All 18 prompts tell the model to send `[]` rather than leave a list out (problem 2) |

### Storage, API and failures — `backend/apps/notes/tests/test_note_options.py` (17)

| # | Test | What it proves |
|---|---|---|
| O1 | `test_llm_option_lists_match_the_model_choices` | The LLM option lists match the model choices |
| E1 | `test_chosen_options_are_saved_and_returned` | Options are saved and returned by POST and GET |
| E2 | `test_omitted_options_use_the_defaults` | Missing options get outline/standard/bullets |
| E3 | `test_values_outside_the_lists_are_rejected_before_the_model_is_called` | Invalid or `null` options are `400`; the AI is not called; nothing saved |
| E4 | `test_each_option_produces_visibly_different_notes` | Type, detail and format each change the saved notes |
| E5 | `test_two_materials_make_one_note_that_records_its_sources_in_upload_order` | Two documents make one note; sources saved by ID in upload order |
| E6 | `test_no_material_selected_is_a_clear_400` | Empty selection is `400` "Select at least one material." |
| E7 | `test_another_students_material_is_a_404_and_saves_nothing` | Another student's document is `404`; nothing saved |
| E8 | `test_material_not_ready_is_a_409` | A document that is not `READY` is `409 DOCUMENT_NOT_READY` |
| E9 | `test_a_missing_source_id_is_left_out_of_the_names_not_an_error` | A source ID with no document is left out, not an error |
| E10 | `test_deleting_a_source_material_deletes_the_notes_through_the_plain_ids` | Deleting a document deletes only the notes built from it |
| E11 | `test_provider_failure_is_a_503_that_saves_nothing_and_leaves_documents_ready` | `503 NOTES_PROVIDER_UNAVAILABLE`; no note or sources; documents and chunks unchanged |
| E12 | `test_invalid_model_output_is_a_503_that_saves_nothing` | Prose, empty sections, and wrong item types are `503 NOTES_INVALID_OUTPUT` after one retry |
| E13 | `test_output_valid_in_shape_but_wrong_for_the_type_is_rejected` | Key-concepts output with no concepts is `503 NOTES_INVALID_OUTPUT` |
| E14 | `test_a_retry_after_a_failure_saves_exactly_one_note` | A failed attempt followed by a retry saves exactly one note |
| E15 | `test_partial_notes_too_large_to_merge_are_a_422_not_an_outage` | Merge too large is `422 NOTES_INPUT_TOO_LARGE`; nothing saved |
| M1 | `test_links_become_ordered_plain_ids_with_default_options` | Migration 0003 turns old links into ordered `NoteSource` rows with default options |

### Updated SCRUM-112 tests — `backend/apps/notes/tests/test_course_notes.py`

| # | Test | Change |
|---|---|---|
| U1 | `test_every_selected_material_reaches_the_model_in_upload_order` | Expects the options argument; checks sources through `NoteSource` |
| U2 | `test_material_deleted_during_generation_is_not_saved` | The fake model call accepts the options argument |
| U3 | `test_model_failure_returns_503_and_saves_nothing` | Expects `NOTES_PROVIDER_UNAVAILABLE` |

### Frontend — `NotesPanel.test.tsx` and `api/notes.test.ts`

| # | Test | What it proves |
|---|---|---|
| F1 | `posts the selected ids and options to the course notes endpoint` | The request body carries the document IDs and the three options |
| F2 | `offers only fixed option choices, with the defaults selected` | 3, 3 and 2 radio buttons; defaults checked; no text box |
| F3 | `sends the chosen options with the selected materials` | Changed options are sent with the selection |
| F4 | `keeps the chosen options when the student creates new notes` | Options survive "Create new notes" |
| F5 | `disables the options while generating` | Options cannot change during a request |
| F6 | `renders bullet notes as a list and paragraph notes as prose, with the options shown` | List versus prose, and the options caption |
| F7 | `explains a failed generation and allows a retry` (3 new cases) | Messages for `NOTES_PROVIDER_UNAVAILABLE`, `NOTES_INVALID_OUTPUT`, and a `503` with no code |
| F8 | `shows default options when an older API response has no options field` | A response without `options` renders with the default caption instead of crashing (added in `65d25db`) |

## Success criteria for SCRUM-86

The task is successful when every ticket acceptance criterion below passes both
its automated tests and its manual check, and the whole backend check passes.

| # | Acceptance criterion | Automated tests | Manual check passes when |
|---|---|---|---|
| AC1 | A student can select two or more documents and generate one note from them | E5, F3 | Step 2 returns `201` with both documents in `source_documents`, in upload order |
| AC2 | Changing note type, detail level or format produces visibly different notes | E4, P3, P11, P12, F6 | Steps 2 and 3 return different sections; in the browser, bullets show as a list and paragraphs as prose |
| AC3 | The saved note records its options and source documents | E1, E5, M1 | Step 4 returns the same `options` and `source_documents` as the POST |
| AC4 | Generation is blocked with a clear message if no document is selected or a document is not processed | E6, E8, existing panel test | Empty selection is `400` "Select at least one material."; the Generate button is disabled with a hint; a non-`READY` document is `409 DOCUMENT_NOT_READY` |
| AC5 | A student can only select their own documents | E7, existing SCRUM-112 tests | Student B's document in A's request is `404` and no note is created |
| AC6 | Tests cover options handling and multi-document generation using a fake LLM | P1–P12, E1–E5 | `scripts/check.py` runs with `NOTES_LLM_BACKEND=fake` and passes |
| AC7 | LLM failures and invalid output are handled gracefully with clear error messages | E11–E13, F7 | The no-key run returns `503 NOTES_PROVIDER_UNAVAILABLE`; the browser shows "The AI service is unavailable right now…" |
| AC8 | Failed generation does not create incomplete or invalid saved notes | E11–E15 | After the no-key run, step 4 for the latest id shows no new note |
| AC9 | Tests cover provider failures, invalid output and recovery after a failed attempt | E11, E12, E13, E14, P10, P13 | Automated only |

Also required for success:

- No student free text reaches the AI prompt: E3, P3, F2. Note that material
  titles still appear in the prompt as section labels, as they did in SCRUM-112.
- Source documents are stored as plain IDs, not foreign keys: E5, E10, M1.
- A notes failure is not a document failure, so documents stay usable: E11.
- Existing notes behave as before: the SCRUM-112 tests pass with only the
  updates listed under U1–U3.
- `scripts/check.py --component backend` passes all four steps: Django system
  checks, migration drift, fresh database migrations, and all backend tests.

## Known limitations for the reviewer to judge

- The detail-level counts (for example "2 to 4 sections" for brief) are
  instructions to the model, not enforced limits. A brief note that comes out
  long is still saved.
- The brief and detailed retry thresholds (0.5% and 3% of the batch input) are
  estimates. Nobody has yet checked them against a real model. The live
  `gpt-4o-mini` runs for problem 2 used the 5,502-character sample fixture,
  which is below the 20,000-character size where the check starts, so they did
  not exercise these thresholds, batching or the merge call.
- No automated test generates notes with a real model. Only the fake LLM and
  mocked provider calls are tested. The one live attempt so far, Sudin's with
  OpenAI, failed with `NOTES_INVALID_OUTPUT` (problem 2 below).
- There is no endpoint to delete one saved note yet; that is SCRUM-91.
  "Create new notes" leaves the old note in the database.
- Migration 0003's reverse path (IDs back to the many-to-many link) is written
  but not tested.

## Expected results

- AI-learning suite passes, including the 31 new backend tests listed above.
- Full backend check passes all four steps. The author's run on 2026-11-14 at
  `086704e` plus the SCRUM-79 test update: 723 passed, 494 subtests passed,
  about 2 minutes.
- Frontend lint passes, all frontend tests pass (437 in the author's run
  before the rebase onto `origin/development`), and `npm run build` succeeds.
- Migration `notes.0003_note_options_and_sources` applies on a fresh database
  and on a database with existing notes.
- Every manual check in the success criteria table behaves as described.

These are expected results, not a record of the teammate's run. Fill the
validation results below only after the teammate has tried the setup and tests.

## Teammate chat feedback — required

After the teammate has tried the setup and tests, ask only:

> Do you have any improvements, concerns, or suggestions for this branch?

Let the teammate explain freely in chat. Do not require answers to a question
list. Ask follow-up questions only when their feedback needs clarification, such
as the exact command that failed, the expected behavior, or the change they
recommend.

The teammate does not need to edit this file while answering. The facilitator
should turn the conversation into the documentation record below afterward.

## Validation report from the chat

After the conversation, replace the placeholders below with a concise account of
the teammate's answers. Preserve important disagreement and uncertainty. The
teammate's feedback is the primary outcome of this exercise.

### Environment

- Name: Sudin
- Date: not reported for Sudin's run (findings added to this report on 2026-11-15)
- Operating system: not reported
- Docker version: not reported
- Python version: not reported
- Node version: not reported
- Branch/commit tested: SCRUM-86 review; exact commit not reported

### Results

- AI-learning suite: not confirmed; Sudin reported 80/80 backend tests passing with `NOTES_LLM_BACKEND=fake`, but did not identify this suite.
- Full backend check: not confirmed; no command or result was reported.
- Frontend lint, tests and build: PASS in Sudin's reported run (31/31 tests, lint with 0 errors and 4 unrelated warnings, build passed).
- AC1 one note from two or more documents: not confirmed by Sudin's manual run; live generation failed.
- AC2 options produce visibly different notes: not confirmed by Sudin's manual run.
- AC3 saved note records options and sources: not confirmed by Sudin's manual run.
- AC4 blocked with a clear message (no selection, not processed): not reported.
- AC5 only the student's own documents: not reported.
- AC7 clear messages for AI failures: partly observed; the frontend displayed the `NOTES_INVALID_OUTPUT` error, but the no-key path was not reported.
- AC8 failed generation saves nothing: not confirmed in Sudin's manual run.
- Migration on a database with existing notes: not reported.

### Teammate feedback summarized

Sudin reported passing backend and frontend checks in the scope stated above.
He reproduced a TypeError when the new `NotesView` receives an older API
response without `options` and suggested a fallback with a regression test.
During a live OpenAI demonstration, the API returned `503 NOTES_INVALID_OUTPUT`.
The frontend showed the error correctly, but successful live generation and the
cause of the rejected output were not established. Sudin did not record a final
merge recommendation or further positive observations.

## Problems encountered

Record every problem reported by the teammate, including problems that were
resolved during the session.

| # | Problem or unexpected behavior | Where it occurred | Evidence | Impact | Resolved? | Recommended action |
|---|---|---|---|---|---|---|
| 1 | Older API response has no `options`, causing `NotesView` to throw a TypeError | frontend | Sudin reproduced it with the older response format | medium | partial; fallback and regression test F8 added in `65d25db`, teammate retest pending | Retest against an older response |
| 2 | Live OpenAI notes generation did not succeed | API / prompt | `503 NOTES_INVALID_OUTPUT`. Reproduced with live `gpt-4o-mini`: summary notes failed 3 of 4 standard/detailed runs with `key_concepts and points must be lists`, because the model left `key_concepts` out of sections that had none | high | partial; validator and prompt fixed, 6 of 6 live combinations then passed; Sudin's own options and material not yet retested | Sudin repeats the live request; if it still fails, record the `Notes output rejected` warnings from the runserver terminal |
| 3 | Lint reported four warnings in unrelated files | frontend | 0 errors, 4 warnings | low | no | Track separately if the team wants a warning-free lint run |

## Positive observations

Sudin observed that the frontend displayed the live `NOTES_INVALID_OUTPUT`
message correctly. His reported backend and frontend tests and build passed.
No other positive observations were recorded.

## Suggested improvements

| # | Suggested improvement | Reason given by teammate | Priority | Planned action |
|---|---|---|---|---|
| 1 | Add a default-options fallback and regression test | An older API response crashed `NotesView` | high | Implemented; teammate retest pending |

Facilitator follow-up: diagnose the live output rejection before judging
provider quality. Log the validation reason and retry number without content,
then repeat the same request and inspect the result. Done on 2026-11-15; see
problem 2 and the facilitator conclusion.

## Evidence collected

Paste concise evidence from the teammate's run. Never include secrets, API keys,
tokens, passwords, or private connection strings.

```text
Commands run: exact commands not supplied by Sudin.

Test results: 80/80 backend tests passed with NOTES_LLM_BACKEND=fake;
31/31 frontend tests passed; lint 0 errors and 4 unrelated warnings;
frontend build passed. Full backend check not reported.

Options and output observations (type, detail level, format): not reported
from a successful live generation.

Ownership and blocked-generation observations: not reported.

AI failure observations: live OpenAI request returned HTTP 503
NOTES_INVALID_OUTPUT; frontend displayed the error. Whether nothing was
saved was not reported.

Error messages or logs: TypeError reproduced with an older response that
omits options; underlying model validation reason not reported.
```

### Evidence and suggestions

Paste concise command output, screenshots, error messages, or log excerpts here.
Do not include secrets, API keys, tokens, or private connection strings.

```text
Teammate result: test and build results passed within the reported scope;
manual live notes generation failed.

What worked: frontend displayed NOTES_INVALID_OUTPUT correctly.

What failed: NotesView on an older response; live OpenAI notes generation.

What was confusing: the reason the provider output failed validation is unknown.

Suggested changes: default-options fallback and regression test.

Final recommendation: not supplied by Sudin.
```

### Facilitator conclusion

Sudin's frontend compatibility finding is confirmed. A fallback and regression
test have been added, but he has not retested them. The live OpenAI failure is
still unexplained; safe diagnostics now record the validation reason and retry
count without model or document text. Reproduce the request and inspect that
reason before deciding whether to adjust the prompt, output checks, or provider.
Changing to a Gemini key alone does not address this failure: notes generation
must be configured to use the Gemini backend, and both backends share the same
notes validator. A same-material comparison can follow diagnosis. The missing
manual checks and Sudin's final recommendation still need to be recorded.

Follow-up checks on 2026-11-15 by the facilitator, not Sudin: the backend
prompt, notes provider, and Gemini test modules passed (32 tests); the
NotesPanel test file passed (25 tests); frontend lint passed with the same
four unrelated warnings; and the frontend build passed. These checks do not
establish the missing manual acceptance results or explain the live provider
failure.

Re-run by the author on 2026-11-15 at `65d25db`, after Sudin's fixes: the
AI-learning suite passed (`scripts/check.py --component backend --suite
ai-learning`: 349 passed, 315 subtests passed, all four steps PASS), and the
notes frontend tests passed (`npx vitest run src/components/notes
src/api/notes.test.ts`: 32 passed, including F8). Like the earlier checks, these
neither replace Sudin's retest nor explain the live failure.

Live diagnosis by the author on 2026-11-15, with `gpt-4o-mini` and the
repository's sample fixture split into two materials (5,502 characters, one
batch). Outline and key-concepts notes passed. Summary notes failed 3 of 4 runs
at standard and detailed level with `key_concepts and points must be lists`:
the summary rule says a section "may have none" key concepts, and the model
read that as permission to leave the `key_concepts` key out. The validator
required both keys, so the attempt and its retry were usually both rejected,
which a student sees as `503 NOTES_INVALID_OUTPUT`. The key-concepts rule says
the same about `points`, so it carried the same risk.

Fix: the validator now reads an omitted `key_concepts` or `points` as an empty
list, and the prompt asks for `[]` instead of a missing key. Wrong types,
`null`, and sections with neither list are still rejected (P13, P14). After the
fix, six live runs (four summary combinations, key-concepts and outline) all
passed, and every section contained both lists. The AI-learning suite passed
again: 351 passed, 335 subtests passed.

Sudin's exact options and material were not recorded, so this is a confirmed
cause, not necessarily the only one. Long materials, which go through the
output-length check and the merge call, were not tested live.

## Final decision

- Problems requiring fixes before merge: none known. Before merge, Sudin should repeat the failed live generation with the same material and options, and the frontend fallback against an older response.
- Accepted improvements: default-options fallback, regression test, content-free validation diagnostics, and accepting omitted `key_concepts`/`points` lists.
- Deferred improvements: a live run with long materials to check the output-length thresholds and the merge call; same-material Gemini comparison; the four unrelated lint warnings (in `CourseTasks.tsx`, `AuthContext.tsx` and `CalendarMonth.tsx`, which belong to other tickets).
- Follow-up owner: not assigned.
- Follow-up issue or task: SCRUM-86 follow-up validation; separate issue identifier not assigned.
- Final recommendation: pending Sudin's final recommendation and follow-up evidence.

## Teammate PR Review — Sudin

- Backend tests: 80/80 passed with `NOTES_LLM_BACKEND=fake`.
- Frontend tests: 31/31 passed.
- Lint completed with 0 errors and 4 warnings in unrelated files.
- Build passed.

### Confirmed frontend compatibility issue

`NotesView.tsx:27` destructures `notes.options` without a fallback. The older
API response does not include `options`, and I reproduced a TypeError with that
response format. I suggest adding a fallback and a regression test.

### Live notes generation

I tried generating notes with the real OpenAI backend and received
`NOTES_INVALID_OUTPUT` (HTTP 503). The frontend displayed the error correctly,
but I couldn't successfully generate notes during the live demonstration. I
haven't confirmed what caused the underlying validation failure.
