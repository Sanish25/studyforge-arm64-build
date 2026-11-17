# SCRUM-122: OKE document-processing worker

**Status:** Preparation only. No image has been published and no live OCI
network rule or Kubernetes resource has been changed.

## Target and task contract

- OCIR image: `phx.ocir.io/axcyydnoof5f/studyforge/document-processing`
- Current source image tag: `arm64-46d02f8a5edc998768c9f19e716a3d6019a869c1`
- Cluster: `studyforge-oke`, `us-phoenix-1`, Kubernetes `v1.35.2`
- Namespace: `studyforge`; Deployment: `processing-worker`, one replica
- Celery app: `processing_service.celery:app`; queue: `document-processing`
- API VM: `10.0.0.234`; OKE node subnet: `10.0.1.0/24`

OCI read-only inventory identified tenancy `dhitalaashish20` (OCID
`ocid1.tenancy.oc1..aaaaaaaamic5qhkdlchwwn7ht3jflgtlmeqktb5l3uufwbtzn5nx5b4b47ia`),
authenticated user `SSanishshrestha@gmail.com` (OCID
`ocid1.user.oc1..aaaaaaaasplpxviglb7alml4ffmxbcljhjzpm7tj5shxnz6v7z6p75tgjyja`),
and root compartment. The cluster OCID is
`ocid1.cluster.oc1.phx.aaaaaaaazuokzxkbuwoqgz3ctjvqxww4d3vrwwhvpyrkbth55cmidganrxna`,
private API endpoint `10.0.1.9:6443`; VCN
`ocid1.vcn.oc1.phx.amaaaaaatvvdeaaaxwizqjrvvtgwyna6nm3so5fezrmz43ze2344ujwrabga`.

The task uses PostgreSQL for execution/callback staging, Redis as Celery broker,
Django's authenticated internal source and callback endpoints, and Gemini for
embeddings. Django streams files from its private storage; the worker needs no
direct object-storage credentials.

## Publishing workflow

`.github/workflows/processing-arm64.yml` is manual-only, uses the native ARM64
runner, and publishes immutable `arm64-${GITHUB_SHA}` plus `arm64-latest` tags.
It checks the published image by pulling its immutable tag for `linux/arm64`.
GitHub repository secrets: `OCIR_USERNAME`, `OCIR_AUTH_TOKEN`; environment:
`ocir-publish`. Do not dispatch until the consolidated deployment approval.

The OCI auth-token inventory has a token named `studyforge-ocir-scrum122` for
the authenticated user, but OCI does not return its value after creation. Check
GitHub secret metadata before creating a replacement. The OCI repository list
returned no rows; verify target-repository visibility/existence before push.

## Kubernetes resources and secrets

`services/document-processing/oke-worker.yaml` creates a ServiceAccount,
ConfigMap, and one-replica Deployment. It runs as UID 10001, drops all Linux
capabilities, uses RuntimeDefault seccomp and a read-only root filesystem, and
sets CPU/memory requests and limits. Startup/readiness check the migrated
processing `Execution` table and Redis. Liveness checks the Celery process. The
150-second termination grace lets Celery warm-shutdown. No Service or Ingress
is created.

Required namespace secrets (create only after deployment approval):

| Secret | Required keys |
|---|---|
| `ocir-auth` (`kubernetes.io/dockerconfigjson`) | `phx.ocir.io` login, unless read-only inspection confirms existing `ocir-pull-secret` is reusable |
| `studyforge-processing-secrets` | `PROCESSING_REDIS_URL`, `PROCESSING_SECRET_KEY`, `PROCESSING_DB_PASSWORD`, `PROCESSING_SERVICE_TOKEN`, `GEMINI_API_KEY` |

ConfigMap points the processing DB to `studyforge_processing` at
`10.0.0.234:5432`. It reads Redis URL from the Secret. Django URL is
`https://studyforge-rodians.duckdns.org`, with a Pod host-alias to private IP
`10.0.0.234` so TLS keeps its hostname while traffic stays on the VCN.

The production processing DB must already exist and have the service migrations
applied. This deployment does not create or migrate a DB. Current task code
writes an `Execution` before processing, so missing schema blocks the worker.

## Network findings and remaining access checks

OKE and API VM share a VCN. API subnet is `10.0.0.0/24`; OKE subnet is
`10.0.1.0/24`. Read-only OCI security-list inspection found API ingress only
for TCP 22, 80, and 443. Private PostgreSQL 5432 and Redis 6379 are not allowed.
If required, add ingress only from `10.0.1.0/24` to `10.0.0.234` on those two
ports; never open them to `0.0.0.0/0`. The OKE subnet has unrestricted egress.
The API HTTPS rule exists; Pod host-alias bypasses public DNS for private API
traffic.

The OKE kubeconfig is at `~/.kube/studyforge-oke`; its private endpoint timed
out from this Mac. No OCI Bastion was found. An existing VCN route/VPN or
approved private access path is required before kubectl checks. Actual listener,
host firewall, Redis authentication, processing DB existence/schema, and
production secret retrieval still require authorized runtime access.

The Cloud Shell PostgreSQL timeout describes only Cloud Shell's network path;
it does not prove OKE Pod reachability. Previously inspected API subnet ingress
rules include TCP 22/80/443 only, with no VM NSG observed. This makes PostgreSQL
and Redis access from OKE unlikely, but the Pod path remains unverified. The
read-only preflight now inspects `ocir-pull-secret` type and registry hostnames
without printing credentials. Reuse it only if it is a Docker config Secret
with a `phx.ocir.io` entry.

The preflight reports matching OCI Vault secret names without reading values.
The namespace Secret is missing worker keys, and no complete authorized source
has yet been verified. The backend runbook identifies `/etc/studyforge.env` on
the API VM as the authorized source for `CELERY_BROKER_URL`,
`PROCESSING_SERVICE_TOKEN`, and `GEMINI_API_KEY`; the Compose `.env` is the
documented source for PostgreSQL credentials. Neither file was accessed, and
they do not establish a `studyforge_processing` database/user password or
`PROCESSING_SECRET_KEY`. The processing database and migration state remain
unverified because Cloud Shell could not reach PostgreSQL and the worker
database password is absent from the Kubernetes Secret.

## Cloud Shell execution option

OCI Cloud Shell can use private VCN networking for private resources. OKE's
cluster-access guidance also documents a Bastion path for private API endpoints.
Use Cloud Shell only if the existing Phoenix Cloud Shell session already has an
active Private Network attached to the StudyForge VCN/subnet and `kubectl get
nodes` succeeds; do not create a network definition, Bastion, or IAM policy as
part of preparation. Cloud Shell's OCI CLI is preauthenticated for the signed-in
user, so create a new kubeconfig inside that shell rather than transferring the
local kubeconfig or its OCI session data.

The reviewed files and the preflight script contain no credentials. They are bundled as
`/private/tmp/scrum122-deployment-preparation.zip` for one Cloud Shell upload.
Cloud Shell supports uploading an archive, not a directory; after upload,
verify its SHA-256 against the supplied hash and extract it under the shell home
directory. File upload does not preserve permissions, which is fine for these
YAML/Markdown/Python files. The bundle filename contains no PII.

The bundle includes `scrum122-cloudshell-preflight.py`. Once uploaded and
extracted, run it with `python3 scrum122-cloudshell-preflight.py`.
It performs only OCI/Kubernetes list/get calls, TCP/HTTPS checks, Redis `PING`,
and PostgreSQL read-only queries. It reads existing K8s Secret values in memory
only when needed for Redis/DB checks; it prints only Secret names and key names.

Before approval, Cloud Shell checks should remain read-only: verify the private
OKE endpoint and namespace, list only the names of the current worker-related
Secrets, and inspect existing Deployments without printing Secret data. TCP
checks to `10.0.0.234:5432` and `:6379` from Cloud Shell only describe that
Cloud Shell subnet's route; they do not prove the OKE Pod route. Do not create
a test Pod before approval. To confirm the processing database itself, use an
authorized secure credential source and a read-only `psql` check; do not retrieve
credentials into chat or an artifact.

## Validation and rollback plan

After approval: verify OKE namespace and baseline Deployment; check private
Redis `PING`, processing DB `SELECT 1` and migrated `Execution` table, and the
authenticated Django endpoint from a temporary Pod; configure secrets without
displaying values; dispatch publishing; verify OCIR architecture; apply the
manifest; confirm Pod readiness, logs, registered task and queue; upload a small
valid PDF and verify Django returns `READY` with a successful callback.

If the Deployment is newly created and validation fails, remove only these
new resources (and Secrets created for this rollout) from namespace
`studyforge`:

```sh
kubectl --kubeconfig "$HOME/.kube/studyforge-oke" -n studyforge delete deployment processing-worker
kubectl --kubeconfig "$HOME/.kube/studyforge-oke" -n studyforge delete configmap studyforge-processing-worker
kubectl --kubeconfig "$HOME/.kube/studyforge-oke" -n studyforge delete serviceaccount processing-worker
```

Record the pre-deploy image and resource state first. If a Deployment already
exists, do not overwrite it; use a revision rollback only after confirming it
belongs to SCRUM-122. Do not touch other workloads, the production VM, API,
frontend, Redis, or database.

## Approved publish and deployment sequence

1. Verify an authorized secret source and confirm the processing database,
   `executions_execution` table, and migration `0002_callback_delivery` with a
   read-only query. Do not rotate credentials.
2. If the OCIR repository is still absent, create it privately in the root
   compartment:

   ```sh
   oci artifacts container repository create \
     --compartment-id ocid1.tenancy.oc1..aaaaaaaamic5qhkdlchwwn7ht3jflgtlmeqktb5l3uufwbtzn5nx5b4b47ia \
     --display-name studyforge/document-processing \
     --is-public false
   ```

3. Push the reviewed branch to the GitHub mirror and manually dispatch
   `processing-arm64.yml`. The existing GitHub secrets `OCIR_USERNAME` and
   `OCIR_AUTH_TOKEN` authenticate the workflow. It publishes
   `arm64-<commit-sha>` and `arm64-latest`, then checks `linux/arm64`.
4. Verify the private OCIR tag. After checking listeners and host firewall,
   allow TCP 5432 and 6379 only from `10.0.1.0/24` to `10.0.0.234`; never add
   public ingress. Django HTTPS already passed and needs no new rule.
5. Reuse `ocir-pull-secret` only if its metadata check confirms type
   `kubernetes.io/dockerconfigjson` and registry host `phx.ocir.io`; otherwise
   create `ocir-auth`. Create `studyforge-processing-secrets` from the
   authorized secret source without printing values. Apply only
   `oke-worker.yaml`, then validate startup, queue/task registration, and one
   representative task.

Rollback removes only the new `processing-worker` Deployment, its
`studyforge-processing-worker` ConfigMap, the `processing-worker` ServiceAccount,
and Secrets created specifically for this rollout. If a Deployment with that
name exists before rollout, stop and confirm ownership before any overwrite or
rollback.
