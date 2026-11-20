# SCRUM-66 Test Review Guide

SCRUM-66 verifies the existing course, to-do, and document rename/edit/delete
behavior, ownership protection, and chunk cleanup. “Edit” for documents means
renaming their display name; there is no separate general document edit API.

## Test coverage

| Acceptance criterion | Test file(s) | Expected behavior |
| --- | --- | --- |
| Successful rename, edit, and delete | `backend/apps/courses/tests.py`; `backend/tests/documents/test_material_management.py`; `backend/tests/documents/test_scrum79_cleanup.py` | Course and document rename return success and persist the new name; to-do edit persists submitted fields; owned deletes return 204 and remove the target. |
| Course/document deletion removes chunks | `backend/tests/documents/test_material_deletion.py`; `backend/tests/documents/test_scrum79_cleanup.py` | The deleted course/document and its chunk rows are absent afterward. |
| Actions reject another user's data | The files above | Mutations of foreign resources return 404; assertions check the protected resource remains unchanged. |
| Invalid input is rejected | `backend/apps/courses/tests.py`; `backend/tests/documents/test_material_management.py` | Empty/whitespace and other invalid names or titles return 400 and do not alter saved data. |

## Run the normal checks

From the repository root, with the existing Python 3.12 environment (including
pytest), Node 24 >=24.15.0 and frontend dependencies, and Docker available. On
this Mac, select the already-installed Homebrew Node 24 for the command:

```bash
PATH="$(brew --prefix node@24)/bin:$PATH" backend/venv/bin/python scripts/check.py
```

If Node 24 is already first on `PATH`, the command can be run without the
`PATH=...` prefix.

This is the repository's full backend and frontend check run. It performs Django
system and migration-drift checks, applies migrations to a fresh disposable
database, runs the backend pytest suite, then runs frontend lint, tests, and
build. It does not run the separate document-processing service suite.

Expected result: exit code `0`, with every `[check] ...: PASS` line. Pytest's
test count can change as the suite evolves; the run is successful when pytest
reports no failures and the runner finishes successfully.

## Interpreting failures

- A failed assertion in one of the listed tests means the observed API or
  database result differed from that test's expected behavior. For example,
  failing chunk-absence assertions point to deletion cleanup not matching the
  test's expectation.
- A failure in Django checks, migration drift, or migration setup points to a
  configuration/schema/setup issue; it does not by itself show that a rename,
  ownership, or deletion behavior is broken.
- A Docker, database connection, missing dependency, lint, or build failure is
  an environment or separate check failure. Read the first failing `[check]`
  section and its output to identify which check needs investigation.

A test failure identifies a mismatch, not necessarily its root cause. Inspect
the failing test and traceback before deciding what code or environment change
is needed.

### Node startup failure on macOS

If the runner prints a `dyld` error saying Node cannot load
`libsimdjson.36.dylib`, then `[check] Setup/cleanup failed` before frontend
checks, the selected Homebrew Node executable is broken or its linked library
is unavailable. This happened here with Node 26.13.0; the frontend tests had
not started, so it was not a test failure.

Check the selected version with `node --version`. This Mac already had Node 24
installed, and putting its Homebrew bin directory first on `PATH` resolved the
problem without replacing Node 26:

```bash
PATH="$(brew --prefix node@24)/bin:$PATH" node --version
PATH="$(brew --prefix node@24)/bin:$PATH" backend/venv/bin/python scripts/check.py
```

The first command should print Node 24. If Node 24 is not installed, install
the project-supported Node 24 version, then rerun the full check. The exact
`simdjson` linkage issue is specific to the affected local installation, but
other machines can also fail if their selected Node version or installation
does not meet the project requirements.

## Latest run

On November 19, 2026, the command above completed successfully. Django checks,
migration drift, fresh database migrations, backend tests (**807 passed, 1
optional S3 test skipped, 549 subtests passed**), frontend lint, frontend tests
(**58 files and 629 tests passed**), and TypeScript/production build all passed.
Oxlint reported warnings, but exited successfully. The earlier Node 26 attempt
failed because that Homebrew binary could not load its `simdjson` dynamic
library; selecting the already-installed Node 24 resolved the failure without
replacing Node 26.
