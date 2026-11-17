# SCRUM-101 review guide for Aashish

## What changed

Document processing now belongs to the standalone service in
services/document-processing. Django saves an upload and a queued job, returns
the document as PENDING, and publishes
processing_service.tasks.process_document_task to the document-processing
Redis queue. The upload request does not wait for extraction or embeddings.

The worker fetches the private source through Django's authenticated
GET /internal/v1/jobs/{job_id}/document/, checks its digest, extracts and chunks
the text, creates document embeddings, then posts RUNNING and SUCCEEDED or
FAILED to POST /internal/v1/jobs/{job_id}/result/. Django validates the
callback and stores chunks and the final status in one database transaction.
There is no backend processing worker in this flow.

Pandu embeds a question through the new
backend/apps/knowledge/query_embeddings.py, searches the stored chunks with
pgvector, and checks citations against those chunks. Query and document
embeddings use the same unprefixed gemini-embedding-2 input and 768 dimensions.
Notes read the processed document's stored chunks in page order.

## Good places to review

- backend/apps/processing/ was deleted. backend/config/settings.py no
  longer installs it; backend/config/celery.py and its import from
  backend/config/__init__.py were removed. Django still has broker settings
  because it publishes jobs.
- backend/apps/knowledge/query_embeddings.py, retrieval.py, and
  services.py remove Pandu's imports from the old app and keep query
  embedding errors inside the knowledge app.
- backend/apps/documents/dispatch.py, internal_views.py, and
  result_callbacks.py show the queue, authenticated HTTP boundary, and chunk
  persistence. services/document-processing/processing_service/tasks.py
  shows the standalone worker. These boundary implementations already existed;
  SCRUM-101 tests their integration and removes the old backend implementation.
- backend/tests/documents/test_worker_integration.py covers success,
  failure, stored chunk retrieval, Pandu, and notes. The knowledge tests for
  query embeddings, retrieval, and questions cover Pandu's new boundary.
  scripts/check_processing_live.py adds the opt-in live broker/worker/HTTP
  test. backend/config/test_settings.py and scripts/check.py force fake RAG,
  notes, and quiz providers; backend/tests/test_ci_isolation.py checks this.

To see the branch changes together, run git diff development...HEAD --stat
from the repository root.

## Run the checks

Use Python 3.12 and Docker Desktop with Linux containers. From the repository
root on Windows, install dependencies into backend/venv if needed:

~~~powershell
backend/venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt -r services/document-processing/requirements.txt
~~~

Then run:

~~~powershell
backend/venv/Scripts/python.exe -B scripts/check.py --component backend
backend/venv/Scripts/python.exe -B scripts/check_processing_live.py
~~~

The backend command creates a disposable PostgreSQL/pgvector database, runs
Django checks and migrations, then the full backend suite. The last verified
result was 640 passed, 462 subtests passed. The live command creates a
separate disposable Compose project with PostgreSQL/pgvector and Redis, plus
separate Django and service databases. Expect its final line to say:

~~~text
[live] PASS: ['PENDING', 'READY'], 1 persisted chunk(s), real Redis worker, source GET, and callback POST
~~~

The live test is opt-in; the normal backend suite does not start Redis or a
Celery worker. In backend tests, AI calls are fake and the integration test
calls the service task directly with an in-process HTTP bridge. In the live
smoke test, the Gemini SDK embedding response, Pandu answer, and notes AI
response are fake. The Redis broker, Celery solo worker, Django HTTP server,
authenticated source GET, result POST, PDF extraction, chunking, PostgreSQL
persistence, retrieval, Pandu citation checks, and notes creation are real.

## Check the nine acceptance criteria

| # | What to check |
| --- | --- |
| 1 | The integration test and live output assert that HTTP upload returns PENDING without waiting for processing. |
| 2 | test_worker_integration.py checks READY after success and FAILED after empty extraction; the live test reaches READY through the worker. |
| 3 | Confirm backend/apps/processing/ is absent and the backend command's Django system checks pass. |
| 4 | The success integration test and live smoke both ask Pandu about a processed chunk and generate notes from that document. |
| 5 | In test_worker_integration.py, read the successful PDF, failed scanned PDF, and retrieve_chunks assertions. |
| 6 | Run the full backend command above and check the final pytest summary. |
| 7 | Check imports in backend/apps/knowledge/: retrieval uses query_embeddings.py, and services catches QueryEmbeddingError. No runtime import points to apps.processing. |
| 8 | Check backend/config/ and backend/apps/documents/dispatch.py: there is no old backend Celery app or task registration; dispatch still names processing_service.tasks.process_document_task and document-processing. |
| 9 | Run the live smoke command. It verifies Redis delivery, the standalone worker, real source/callback HTTP, persisted chunks, retrieval, Pandu citation, and notes without the old worker. |

For a quick legacy-reference check, run:

~~~powershell
rg -n --glob "*.py" "apps\.processing|backend\.apps\.processing|processing\.tasks|celery -A config" backend/apps backend/config scripts
~~~

It should find no Python runtime references. Older AI development reports may
still describe the architecture as it was when those reports were written.

## Manual checks and limits

- Check that the worker's source GET and callback POST use the shared service
  token, and that callback validation checks job, document, digest, and attempt
  before writing chunks.
- Check that the live test creates disposable databases and removes its Compose
  project, and that no backend Celery worker is started.
- The live smoke tests one successful text PDF. The FAILED path is covered
  by backend integration tests, not a second live worker run. AI provider
  availability and answer quality are outside these deterministic tests.

## Reviewer results

- Reviewer: Aashish Dhital
- Date: November 16, 2026, 4:12 PM CT
- Branch: `feature/SCRUM-101-adapt-integration-tests-remove-processing`

### What I ran

I checked out this branch and ran the review checks from this guide:

1. Full backend suite:
   `backend/venv/bin/python -B scripts/check.py --component backend`
2. Live processing smoke test:
   `backend/venv/bin/python -B scripts/check_processing_live.py`
3. Legacy reference search for the old processing app / Celery wiring

### Results

All automated checks passed.

- Backend tests: **690 passed**, **469 subtests passed**
- Live smoke: **PASS** — upload returned `PENDING`, then became `READY` through
  the real Redis worker, with source GET, callback POST, stored chunks, Pandu,
  and notes
- Legacy search: **no Python runtime references** to the old
  `apps.processing` / backend Celery app

The SCRUM-101 flow looks correct: Django no longer owns document processing,
jobs go to the standalone document-processing worker, and the integration and
live tests cover that boundary.

### Requested change

Please remove the leftover `backend/apps/processing/` folder from the local
tree if it is no longer needed.

On this machine, `ls backend/apps/processing` still showed a folder with only
`__pycache__` and `tests` cache files. The real processing source code is
already gone, and nothing useful is left there. If those leftovers are not
used by the project, they should be deleted so reviewers do not think the old
processing app is still part of the branch.

Suggested cleanup:

~~~bash
rm -rf backend/apps/processing
~~~

After that, `ls backend/apps/processing` should report that the path does not
exist.

### Recommendation

**Request changes** for the leftover `backend/apps/processing/` cleanup above.
Once that is cleaned up (or confirmed as local-only cache that will not be
committed), the branch is otherwise ready to approve and squash into
`development`.

### Follow-up

Removed the ignored cache-only `backend/apps/processing/` directory. Git tracks
no files under that path, and the directory no longer exists in the local tree.
