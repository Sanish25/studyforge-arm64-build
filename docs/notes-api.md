# Notes API

Tasks: SCRUM-68, SCRUM-112, SCRUM-86
Owner: Gaurav Paneru

Both generators read a document's chunks in reading order (SCRUM-69), never by
similarity search, because they summarize whole materials instead of answering
a query. All routes require authentication.

## Generate notes from course materials

POST /api/v1/courses/{course_id}/notes/

    {"document_ids": [12, 13], "note_type": "summary", "detail_level": "brief", "format": "paragraphs"}

Accepts 1 to 20 unique ids. Every id must be a READY material the student owns
in this course; chat uploads are not accepted.

### Options (SCRUM-86)

Each option is optional and must come from its fixed list; any other value is a
400 and the model is not called. Only these keys select prompt text, so nothing
a student types reaches the model.

| Field | Values | Default |
|---|---|---|
| `note_type` | `summary`, `outline`, `key_concepts` | `outline` |
| `detail_level` | `brief`, `standard`, `detailed` | `standard` |
| `format` | `bullets`, `paragraphs` | `bullets` |

The defaults match notes generated before options existed.

- **note_type.** `summary`: most of the content is in the overview, sections are a few
  themes, and key concepts may be empty. `outline`: one section per topic in source
  order, and every section has points. `key_concepts`: a glossary, and every section
  has key concepts.
- **detail_level.** These are written targets in the prompt, not enforced
  limits. `brief`: 2–4 sections, at most 3 concepts and 3 points each, and a
  1–2 sentence overview. `standard`: every definition, rule, value and date.
  `detailed`: standard plus examples, conditions and exceptions, with 2–3
  sentence explanations. More detail means more output tokens and a longer
  wait. Input tokens stay about the same.
- **format.** It sets how each `points` item is written: one short sentence for
  `bullets`, a 3–5 sentence paragraph for `paragraphs`. The saved shape is the
  same either way.

The validator enforces only the structure each type promises. The counts and
lengths for each detail level are guidance to the model.

### 201 Created
{
  "id": 5,
  "title": "Notes: Lecture 1, Lecture 2",
  "course": 42,
  "options": {"note_type": "summary", "detail_level": "brief", "format": "paragraphs"},
  "overview": "...",
  "sections": [
    {
      "heading": "...",
      "key_concepts": [{"term": "...", "explanation": "..."}],
      "points": ["..."]
    }
  ],
  "source_documents": [{"id": 12, "name": "Lecture 1"}, {"id": 13, "name": "Lecture 2"}],
  "created_at": "2026-10-30T12:00:00Z"
}

Materials are read in upload order, regardless of the order of `document_ids`.
Each request calls the model and saves a new row; it is not idempotent.

### Errors

Branch on `code`, because several errors share a status.

| Status | `code` | Meaning |
|---|---|---|
| 400 | none | Empty, duplicate, malformed, or more than 20 ids, or an option outside its list. |
| 401 | none | No valid credentials. |
| 404 | none | The course or any id is missing, not the student's, in another course, or a chat upload. A material deleted during generation also returns 404. The response does not say which id. |
| 409 | `DOCUMENT_NOT_READY` | Some materials are not READY. `document_ids` lists them. |
| 409 | `DOCUMENT_HAS_NO_TEXT` | Some READY materials have no readable text. `document_ids` lists them. |
| 422 | `NOTES_INPUT_TOO_LARGE` | The selection exceeds the total size limit, or the batch notes were too large to merge in one call (most likely with `detailed`). Select fewer materials or a lower detail level. |
| 503 | `NOTES_PROVIDER_UNAVAILABLE` | The AI provider failed (outage, rate limit, timeout, missing key). Nothing was saved, so retrying is safe. |
| 503 | `NOTES_INVALID_OUTPUT` | The model's output was still unusable after one retry: not JSON, the wrong shape, or the wrong structure for the note type. Nothing was saved, so retrying is safe. |

SCRUM-86 replaced `NOTES_GENERATION_FAILED` with the two 503 codes above. A
notes failure never changes a material: it stays READY, keeps its chunks, and
can be used again right away.

### Input limits

Sizes are characters, roughly 4 per token. Generation runs inside one HTTP request.

| Setting | Default | Effect |
|---|---|---|
| `NOTES_BATCH_CHAR_LIMIT` | 60000 | Maximum size of one notes batch. A larger selection is split into batches, summarized batch by batch, and merged in a final call. A material split across batches keeps its title on every part. |
| `NOTES_TOTAL_CHAR_LIMIT` | 300000 | Maximum selection size. Larger selections are rejected, not sampled, so notes never knowingly omit content. |

A batch of about 200,000 characters occasionally came back as a brief summary
that dropped most topics while still being valid, which is why batches are small.

### Output checks

Each model call is repeated once if its output is invalid or too short for its
input, for input of 20,000 characters or more. "Too short" depends on the
detail level, because brief notes are meant to be short:

| `detail_level` | Batch minimum | Merge minimum |
|---|---|---|
| `brief` | 0.5% | 10% |
| `standard` | 2% | 25% |
| `detailed` | 3% | 30% |

The brief and detailed thresholds are estimates and still need measuring
against the real model. If the repeat also fails, the request returns 503 and
saves nothing. Every batch and the merge use the same options.

Long generations run inside one HTTP request. A `detailed` selection near the
total limit can take several minutes, so a proxy or server timeout shorter than
that shows up as a 502 or 504, not as one of the codes above.

The length check catches a model that skimmed. It cannot prove that every topic
was covered, so a selection can still lose individual details.

## Read saved notes

GET /api/v1/notes/{notes_id}/

Returns the same body as generation, with status 200, and never calls the model.
Returns 404 when the notes do not exist or belong to another student.

## Storage

Saved notes keep their three options and their sources. Each source is a
`NoteSource` row holding a plain `document_id` (a positive `BigInteger`, indexed
and unique per note), with no foreign key to Document. This follows the SCRUM-98
pattern for `Execution.document_id`. `position` keeps the materials' upload
order. `source_documents` names are looked up when the note is read, scoped to
the note's owner. An id with no matching material is left out.

## Deletion

Deleting a material deletes all notes built from it, including notes that also
used other materials, so its content does not outlive it. Deleting the course
deletes its notes. Renaming a material keeps them, and `source_documents` shows
the new name.

## Generate a single-document study guide

POST /api/v1/documents/{document_id}/study-guide/

Used by the panel shown after an upload. Every request calls the model and
replaces the document's saved guide; no route reads a saved guide back.

### 200 OK
{
  "key_concepts": ["...", "..."],
  "important_points": ["...", "..."],
  "summary": "..."
}

### Errors

| Status | `code` | Meaning |
|---|---|---|
| 401 | none | No valid credentials. |
| 404 | none | The document does not exist or is not the student's. 404 rather than 403, so the API never reveals that someone else's document exists. |
| 409 | `DOCUMENT_NOT_READY` | The document is still processing. |
| 409 | `DOCUMENT_HAS_NO_TEXT` | The document reached READY with no readable text, such as a scanned PDF. |
| 503 | `STUDY_GUIDE_GENERATION_FAILED` | The provider failed or returned invalid output. Retrying is safe. |
