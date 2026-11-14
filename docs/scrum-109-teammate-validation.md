# SCRUM-109 Teammate Validation Report

## Report purpose

This report records an independent teammate's experience running and reviewing
the SCRUM-109 branch, which implements horizontal autoscaling and worker failure
recovery for PDF processing.

The teammate's feedback is the most important result. Record every problem they
encounter, including setup failures, unclear instructions, unexpected output,
slow behavior, missing prerequisites, and concerns about the design. Do not mark
the report complete only because automated tests pass.

## Review status

- Reviewer: `Aashish Dhital`
- Report status: `complete`
- Overall result: `satisfactory with changes`
- Final recommendation: `approve with changes`

## Branch under review

```text
feature/SCRUM-109-horizontal-auto-scaling-failure-handling-worker
```

## What this branch does

- Runs two baseline Celery worker Pods in Kubernetes.
- Uses Redis as the Celery broker and `document-processing` queue.
- Acknowledges tasks late so an unacknowledged task can be redelivered after a
  worker process dies.
- Preserves the existing maximum of three application retries.
- Uses the backend database callback contract to reject stale work and make
  terminal PDF results idempotent.
- Installs KEDA and scales the worker Deployment from the Redis queue length.
- Keeps at least 2 workers and allows up to 10 workers.
- Targets 5 queued PDFs per worker.
- Checks queue demand every 15 seconds.
- Holds scale-down for 150 seconds before returning to 2 workers.
- Replaces failed Kubernetes worker Pods through the Deployment controller.

Expected scaling examples:

```text
0 queued PDFs   -> 2 workers
15 queued PDFs  -> 3 workers
50+ queued PDFs -> up to 10 workers
empty queue     -> 2 workers after 150 seconds
```

## Main files touched

- `services/document-processing/processing_service/settings.py`
  - Celery late acknowledgement, worker-loss rejection, one-task prefetch, and
    Redis visibility timeout.
- `services/document-processing/processing_service/tasks.py`
  - Existing PDF task and unchanged three-retry policy.
- `services/document-processing/processing_service/requirements.txt`
  - Runtime `packaging` dependency required by Celery's Redis transport.
- `services/document-processing/kind-worker.yaml`
  - Two worker replicas, rolling updates, one PDF per worker process, and the
    shared Redis queue configuration.
- `services/document-processing/keda-worker-scaledobject.yaml`
  - KEDA Redis scaler with the 2-to-10 replica range and queue target of 5.
- `services/document-processing/tests/test_scrum109_validation.py`
  - Static and live KEDA scale and worker replacement checks.
- `services/document-processing/live_crash_check.py`
  - Two-worker Redis redelivery probe.
- `backend/tests/documents/test_worker_integration.py`
  - PDF replay and duplicate terminal result coverage.

## Prerequisites

- Docker Desktop running Linux containers.
- `kind`, `kubectl`, and Python 3.12.
- The repository's `backend/venv` created and dependencies installed.
- Access to the repository's local Docker images and Redis service.

The live tests use only local resources. The scaling test inserts synthetic
values into a temporary Redis list and removes them in cleanup. It does not call
the paid embedding provider.

## Local setup

From the repository root:

```bash
kind create cluster --name studyforge
kind export kubeconfig --name studyforge --kubeconfig /tmp/studyforge-kubeconfig
export KUBECONFIG=/tmp/studyforge-kubeconfig

docker compose up -d redis

kubectl apply --server-side \
  -f https://github.com/kedacore/keda/releases/download/v2.21.0/keda-2.21.0.yaml
kubectl wait --for=condition=Available deployment/keda-operator -n keda --timeout=120s

docker build -t studyforge-document-processing:kind ./services/document-processing
kind load docker-image studyforge-document-processing:kind --name studyforge

kubectl create secret generic studyforge-processing-secrets \
  --from-literal=PROCESSING_SECRET_KEY='local-processing-secret' \
  --from-literal=PROCESSING_DB_PASSWORD='processing_local_dev' \
  --from-literal=PROCESSING_SERVICE_TOKEN='replace-with-shared-local-token' \
  --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f services/document-processing/kind-worker.yaml
kubectl apply -f services/document-processing/keda-worker-scaledobject.yaml
kubectl rollout status deployment/processing-worker --timeout=120s
```

The service token must match the token used by the local Django backend if you
run an actual PDF through the application. The placeholder above is sufficient
only for worker startup and scaler checks.

## Validation commands

Run the configuration check:

```bash
backend/venv/bin/python -m pytest \
  services/document-processing/tests/test_scrum109_validation.py -q
```

Run the live KEDA and Pod replacement checks:

```bash
SCRUM109_LIVE=1 \
KUBECONFIG=/tmp/studyforge-kubeconfig \
backend/venv/bin/python -m pytest \
  services/document-processing/tests/test_scrum109_validation.py -s -q
```

Before the live suite, confirm there are exactly 2 Running worker pods. If there
are more (for example after a scale test), reset first:

```bash
kubectl scale deployment/processing-worker --replicas=2
kubectl wait --for=jsonpath='{.status.availableReplicas}'=2 \
  deployment/processing-worker --timeout=120s
```

Run the database PDF and duplicate-result suite:

```bash
backend/venv/bin/python scripts/check.py \
  --component backend --suite documents
```

Run the two-worker Redis redelivery probe:

```bash
backend/venv/bin/python services/document-processing/live_crash_check.py
```

Inspect the live state manually if a test fails:

```bash
kubectl get scaledobject processing-worker-scaler
kubectl get hpa
kubectl get pods -l app=processing-worker
kubectl describe scaledobject processing-worker-scaler
docker exec studyforge-redis-1 redis-cli -n 0 LLEN document-processing
```

## Expected results

- Static validation: `1 passed, 3 skipped` unless `SCRUM109_LIVE=1` is set.
- Live validation: 4 tests pass.
- Database document suite: all document tests pass.
- Redis crash probe: reports that Redis redelivered the task to the surviving
  worker.
- Deleting one worker Pod results in a replacement and two healthy Pods.
- A repeated terminal PDF callback is reported as a duplicate and does not
  create duplicate stored chunks.

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

- Name / reviewer: `Aashish Dhital`
- Date: `2026-11-14`
- Operating system: `macOS 14.5`
- Docker version: `29.7.2`
- Kubernetes/kind version: `kind v0.30.0`
- Branch/commit tested: `feature/SCRUM-109-horizontal-auto-scaling-failure-handling-worker @ 7cf279e`

### Results

- Static validation: `PASS` (`1 passed, 3 skipped`)
- Live KEDA validation: `PASS` (`4 passed` after resetting to 2 workers)
- Database PDF validation: `PASS` (`279 passed`)
- Redis crash redelivery: `PASS`
- Duplicate prevention: `PASS` (covered by documents suite)

### Teammate feedback summarized

Branch works. Static checks, live KEDA scale, pod replacement, Redis redelivery,
and the documents suite all passed. One live test failed when 3 worker pods were
still running after scale-up; scaling back to 2 fixed it. Suggest documenting
that the live suite expects exactly 2 Running workers first. No other product
issues found.

## Problems encountered

| # | Problem or unexpected behavior | Where it occurred | Evidence | Impact | Resolved? | Recommended action |
|---|---|---|---|---|---|---|
| 1 | Live pod-replace test failed because 3 workers were still up (`assert 3 == 2`) | `tests` | `test_failed_worker_pod_is_replaced` AssertionError; later fixed by `kubectl scale ... --replicas=2` then `4 passed` | `low` | `yes` | Tell reviewers to wait until 2 Running workers (or scale to 2) before live pytest |

## Positive observations

- Setup and validation commands were clear enough to run.
- KEDA ScaledObject/HPA showed min 2 / max 10 as expected.
- Redis crash probe reported redelivery to the surviving worker.
- Manual pod delete brought the Deployment back to 2 healthy pods.
- Documents suite passed cleanly, including duplicate/terminal result coverage.

## Suggested improvements

| # | Suggested improvement | Reason given by teammate | Priority | Planned action |
|---|---|---|---|---|
| 1 | Note in the validation docs that live tests need exactly 2 Running workers first | Live replace test assumes 2 pods; leftover scaled pods cause a false fail | `low` | Added the reset steps under Validation commands in this report; no code change required for merge |

## Evidence collected

Paste concise evidence from the teammate's run. Never include secrets, API keys,
tokens, passwords, or private connection strings.

```text
Commands run:

backend/venv/bin/python -m pytest \
  services/document-processing/tests/test_scrum109_validation.py -q
-> 1 passed, 3 skipped

SCRUM109_LIVE=1 KUBECONFIG=/tmp/studyforge-kubeconfig \
backend/venv/bin/python -m pytest \
  services/document-processing/tests/test_scrum109_validation.py -s -q
-> first run failed on pod replace with 3 pods present
-> kubectl scale deployment/processing-worker --replicas=2
-> rerun: 4 passed in 172.05s

backend/venv/bin/python scripts/check.py \
  --component backend --suite documents
-> 279 passed

backend/venv/bin/python services/document-processing/live_crash_check.py
-> PASS: Redis redelivered the unacknowledged task to the surviving worker

Manual pod replace:
kubectl delete pod <one-worker>
-> two Running pods again

Test results:
Static: PASS
Live KEDA: PASS (after scale to 2)
Documents: PASS
Redis crash: PASS

KEDA/HPA observations:
ScaledObject Ready True, MIN 2 MAX 10
HPA keda-hpa-processing-worker-scaler TARGETS 0/5 (avg), REPLICAS 2
document-processing queue length: 0

Worker and Redis observations:
Baseline settled at 2 Running workers
Deleted pod was replaced; still 2 healthy pods

Error messages or logs:
AssertionError: assert 3 == 2 on test_failed_worker_pod_is_replaced
(resolved by scaling Deployment back to 2)
```

### Evidence and suggestions

```text
Teammate result: satisfactory with one low-priority docs note

What worked:
Static config check, live KEDA scale to 3 and back to 2, pod replacement,
Redis redelivery, and documents suite.

What failed:
Live pod-replace once, only because 3 workers were still present.

What was confusing:
Nothing major. Easy to miss that live tests need baseline of 2 workers.

Suggested changes:
Document the “scale/wait until 2 workers” step before live pytest.

Final recommendation: approve with changes
```

### Facilitator conclusion

Validation is complete. All required checks passed after one easy recovery step.
Accepted suggestion: document that live validation expects 2 Running workers
first (already added above). No product code fix is required before merge.
Next action: merge when the team is ready; optional follow-up only if someone
wants the live test to auto-wait for 2 pods.

## Final decision

- Problems requiring fixes before merge: `none`
- Accepted improvements: `document “ensure 2 workers before live pytest”`
- Deferred improvements: `auto-wait/assert baseline of 2 pods inside the live test (optional)`
- Follow-up owner: `Aashish Dhital`
- Follow-up issue or task: `none (docs note only)`
- Final recommendation: `approve with changes`
