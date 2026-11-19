# SCRUM-122 execution status

**Overall: INCOMPLETE.** Updated 2026-11-18. Detailed staged production plan
and evidence are in [the OKE worker deployment record](deployment/scrum-122-oke-worker.md).

| Phase | Status | Evidence / remaining work |
|---|---|---|
| 1. OKE access | VERIFIED COMPLETE | Existing branch `feature/SCRUM-122-deploy-kubernetes-to-processing`, HEAD `6db5c95`. Reauthenticated the kubeconfig's `studyforge-scrum122-local` OCI profile using its existing signing key. Existing Bastion was ACTIVE; all prior sessions were DELETED. With user approval, created one 3,600-second port-forward session to `10.0.1.9:6443`; no allowlist/network changes. Dedicated kubeconfig verified TLS/API access; node `10.0.1.63` is Ready and `kubernetes.io/arch=arm64` (Kubernetes `v1.35.2`). Then stopped the local tunnel, verified port `16443` closed, and deleted the temporary Bastion session; OCI status reached `DELETED`. |
| 2. ARM64 image | VERIFIED COMPLETE | Source SHA `6db5c95eb415d5407061140903998a4f8ec56be3` synced to the GitHub mirror after approval. Workflow run `44434934736` passed on `ubuntu-24.04-arm`; runner check reported `aarch64`, required secret-name checks and OCIR login passed, and published platform verified as `linux/arm64`. Tag `arm64-6db5c95eb415d5407061140903998a4f8ec56be3-44434934736-1`; Buildx and pulled registry digest matched `sha256:c07d7b5d5fd4b089f65617733e100f0f062cd76122fe10366c3496b0f14858f6`. Immutable reference: `phx.ocir.io/axcyydnoof5f/studyforge/document-processing@sha256:c07d7b5d5fd4b089f65617733e100f0f062cd76122fe10366c3496b0f14858f6`. Prior worker tests and local smoke/build evidence passed. |
| 3. Backend dependencies | BLOCKED | SCRUM-127 has the Django S3 locator, shared token, and worker read-only storage contract on its separate branch, but the verified VM checkout did not include it and production was still filesystem-backed. SCRUM-125's live snapshot showed PostgreSQL TLS off, no processing DB/role/migrations, Redis without TLS/auth, and no OKE network path. No later live cutover evidence is recorded. |
| 4. Network/Kubernetes configuration | SAFE CHECKS VERIFIED; DEPLOYMENT BLOCKED ON DEPENDENCIES | Local parsing and strict v1.35.2 schema validation passed. With approval, created one 3,600-second Bastion forward to `10.0.1.9:6443`; verified node `10.0.1.63` Ready/arm64, namespace and pull-secret, and strict server-side dry-run of all three manifest objects. Confirmed dry-run persisted nothing, stopped the tunnel, and deleted the session (OCI state `DELETED`). No worker runtime ConfigMaps/Secret/ServiceAccount exist yet. Backend and network dependencies remain incomplete. |
| 5. Deploy and end-to-end test | NOT STARTED | No Kubernetes resources applied, worker pod created, or real-document test run. Explicit user approval and completion/verification of the backend and network prerequisites remain required. |

## Phase 1 evidence and root cause

- Both OCI profiles initially reported expired sessions. The kubeconfig uses
  `studyforge-scrum122-local`; earlier authentication had refreshed only the
  primary profile. This caused the initial kubectl exec-credential failure.
- Read-only Bastion inventory found three sessions, all `DELETED`. There was
  no active local tunnel/listener. This caused the subsequent connection
  refusal at `127.0.0.1:16443` after credentials were restored.
- Bastion allowlist was `24.155.68.96/32`; user confirmed current egress matched.
  The pinned SSH host key and dedicated public-key fingerprints matched the
  recorded values. Tunnel establishment succeeded, confirming allowed source
  access without third-party IP discovery.
- After the approved temporary session, `kubectl get nodes -o wide -L
  kubernetes.io/arch` reported node `10.0.1.63` Ready, `arm64`.
- No OKE resources, services, NSGs, routes, or allowlists were modified.

No worker has been deployed. See the detailed runbook for approval gates and
rollback steps for remaining phases.

## Phase 2 release preparation

- Current source: existing branch `feature/SCRUM-122-deploy-kubernetes-to-processing`, HEAD `6db5c95`.
- Target: `phx.ocir.io/axcyydnoof5f/studyforge/document-processing` (per user instruction; current OCI inventory was not refreshed).
- Workflow: `.github/workflows/processing-arm64.yml`, `workflow_dispatch`, runner `ubuntu-24.04-arm`, `platforms: linux/arm64`, `push: true`. GitHub runner selection, secret-name checks, and OCIR authentication all passed in run `44434934736`.
- Tag: `arm64-6db5c95eb415d5407061140903998a4f8ec56be3-44434934736-1`.
- Published immutable image: `phx.ocir.io/axcyydnoof5f/studyforge/document-processing@sha256:c07d7b5d5fd4b089f65617733e100f0f062cd76122fe10366c3496b0f14858f6`.
- Verification: workflow reported `linux/arm64`; Buildx digest and pulled OCIR RepoDigest both equal `sha256:c07d7b5d5fd4b089f65617733e100f0f062cd76122fe10366c3496b0f14858f6`. Workflow run conclusion was success. The current local Docker Desktop is unavailable, so the prior successful local worker suite/build evidence is retained from the preceding checkpoint.
- Approval: user approved syncing the missing GitHub mirror branch at this exact SHA and dispatching the publisher. The branch was created with a non-force push. No OKE deploy or other cloud resource changes were made.

## Phase 3 safe preparation (2026-11-18)

- Inspected `services/document-processing/oke-worker.yaml`. It defines only a
  ServiceAccount, ConfigMap, and single-replica Deployment. The pod selects
  `kubernetes.io/arch: arm64`, references existing `ocir-pull-secret`, disables
  service-account token mounting, and runs non-root with a read-only root FS,
  dropped capabilities and a bounded `/tmp` volume.
- Updated only the Deployment image field to the immutable Phase 2 reference:
  `phx.ocir.io/axcyydnoof5f/studyforge/document-processing@sha256:c07d7b5d5fd4b089f65617733e100f0f062cd76122fe10366c3496b0f14858f6`.
  This is a local manifest preparation; it has not been applied.
- Runtime config requires PostgreSQL `verify-full` and the trust ConfigMap,
  authenticated Redis URL, Django HTTPS locator URL and shared service token,
  direct S3 retrieval, private bucket settings, optional worker storage keys,
  and Gemini key. Secrets are references only; no secret values are stored in
  this manifest. Required DB/Redis/Django values are not optional; optional
  storage credential references support workload identity. Image pull secret
  was found in the earlier Phase 1 namespace snapshot, but its current existence
  and ability to pull were not rechecked.
- Startup/readiness execute the worker dependency check (authenticated Redis,
  Django setup, database and direct-storage readiness); liveness checks the
  Celery worker process. Requests are 250m CPU/512Mi memory and limits are 1 CPU
  / 1Gi. These were manifest inspections, not live probe observations.
- Coordination evidence: Sudin Katuwal's `origin/feature/SCRUM-127-production-file-storage-service-connections`
  branch contains the documented S3 storage, authenticated object locator,
  service-token and read-only worker identity contract. The production VM
  baseline in this runbook predates that release and was still filesystem-backed;
  the approved bucket and live Django release are not evidenced here. Nischal
  Rimal's `origin/deploy/SCRUM-125-backend-postgres-redis` changes settings to
  be environment-driven, but the recorded live state still lacked PostgreSQL
  TLS and the restricted processing DB/role/migrations, and Redis TLS/auth.
  These code branches do not establish that production dependencies have been
  cut over. There is no connected teammate messaging tool in this environment;
  coordination here is based on their checked-in contracts and recorded live
  evidence.
- On 2026-11-18, `oci session validate --profile studyforge-scrum122-local
  --local` reported valid until `2026-11-18 20:25:05`. Authenticated read-only
  Bastion inventory returned four old sessions, all `DELETED`, targeting
  `10.0.1.9:6443`; the Bastion remained `ACTIVE` with allowlist
  `24.155.68.96/32`. After the user's explicit approval, created one temporary
  3,600-second session, verified it `ACTIVE` with the intended target, then
  stopped the tunnel and deleted the session. OCI confirmed final state
  `DELETED`. No allowlist or network rule changed.
- `yq eval-all -o=json` parsed all three manifest documents.
  `kubeconform -strict -summary -kubernetes-version 1.35.2` passed all three
  resources (Valid 3, Invalid 0, Errors 0); schema retrieval succeeded outside
  the network-restricted sandbox. Strict server-side dry-run against OKE also
  passed for all three resources. Follow-up reads confirmed none were persisted.
- Static checks confirmed the immutable Phase 2 digest, ARM64 selector,
  `processing-worker` ServiceAccount with token automount disabled,
  `ocir-pull-secret`, worker ConfigMap reference, required Secret keys and
  optional storage credential keys, all three probes, requests `250m` CPU/
  `512Mi`, and limits `1` CPU/`1Gi`. Secret values were not read. Live inventory
  confirmed the pull secret is type `kubernetes.io/dockerconfigjson` with key
  `.dockerconfigjson` and registry host `phx.ocir.io`.
- Live node inventory returned `10.0.1.63 Ready=True arm64 v1.35.2`. Namespace
  `studyforge` is `Active`. It contains only frontend pod/deployment/service,
  `kube-root-ca.crt`, `ocir-pull-secret`, and default ServiceAccount. Worker
  ConfigMaps `studyforge-processing-worker`, `studyforge-processing-runtime`,
  `studyforge-processing-trust`, Secret `studyforge-processing-secrets`, and
  ServiceAccount `processing-worker` are absent. Thus dry-run validates API
  acceptance, not dependency readiness.
- No Kubernetes object, VM service, NSG, network rule, Secret, ConfigMap, or
  production setting was changed. No pod or end-to-end processing test ran.

### Exact pending deployment change and approvals

The sole prepared manifest delta is the worker image field changed from the
placeholder to the immutable digest above. The manifest already references the
existing pull secret; it proposes the three worker resource definitions listed
above. Live namespace and pull-secret checks plus server-side dry-run are
complete. The worker runtime objects remain absent. Before any apply, complete
and verify the separately approved Django/S3, PostgreSQL, Redis and network
prerequisites, then show the final rendered diff and request explicit approval.
After approval, verify the pod is Ready
on the Ready ARM64 node with the expected `imageID`, check authenticated Celery
connectivity and queue consumption, then submit an approved test document and
verify its job, callback, and final result. Phase 3 is not complete until those
checks pass.

### Phase 3 read-only checks completed

With user approval, the live reads and strict server-side dry-run were
completed. Post-dry-run inventory verified that none of the worker objects
were persisted. The local tunnel was stopped, port 16443 was confirmed closed,
and the temporary session was verified `DELETED`. No resources were applied.
