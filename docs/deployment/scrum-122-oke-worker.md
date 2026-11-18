# SCRUM-122: OKE document-processing worker

**Status on 2026-11-17.** Authorized VM access is verified, and the official
SCRUM-122 feature branch is the local source of truth. Live service inspection
confirmed that the Django API, PostgreSQL, Redis, and storage need a coordinated
cutover before the worker can run. SCRUM-122 is complete after a real document
is processed by the OKE worker and the result appears in StudyForge.

## Verified production baseline after SSH authorization

Aashish Dhital authorized the dedicated local key
`~/.ssh/studyforge-api-vm`. The connection verified the pinned Ed25519 host
fingerprint `SHA256:+ba6rJO8D/Xlt7YGyYJyLaZbZjqIJ/s3iA8YkdxYVv4` using strict
checking. It authenticated as `ubuntu` to `studyforge-api` at public IP
`132.226.88.147`. Interface `enp0s6` reports `10.0.0.234/24` and the host
has no global IPv6 address. `sudo -n -l` confirmed `(ALL) NOPASSWD: ALL`.
All VM commands in this checkpoint were read-only. Config values were
classified in memory and no credential values were displayed.

| Area | Verified live evidence | Required before OKE worker rollout |
|---|---|---|
| Docker and host firewall | Compose project `studyforge` runs `studyforge-db-1` and `studyforge-redis-1`. Both ports 5432/6379 are published on IPv4 and IPv6 wildcards. IPv4 INPUT allows 22/80/443 and rejects other traffic, but Docker DNAT sends the two ports through FORWARD. `DOCKER-USER` is empty and the Docker chain accepts both container destinations. `netfilter-persistent` is active. | Replace wildcard mappings with scoped bindings and add an ingress guard in the Docker forwarding path before authorizing OCI ingress. A host INPUT rule alone does not secure the published container ports. |
| PostgreSQL 16.16 | `ssl=off`, `listen_addresses=*`, port 5432. HBA trusts local sockets/loopback and uses SCRAM for other hosts. A read-only TCP query inside Docker authenticated with the existing container configuration and reported no TLS. Application DB `studyforge` has pgvector and its login is a superuser. The processing DB and role `studyforge_processing` are absent. | Enable verified TLS, scope remote HBA, provision the dedicated restricted processing database and role, then apply and verify the two processing migrations. Keep the existing application database and role out of the worker Secret. |
| Redis 7.4.12 | Port 6379, `tls-port=0`, `protected-mode=no`, ACL default user `on nopass` and no other user. The running build links TLS libraries. Persistence uses RDB snapshots with AOF disabled, and changes since the last snapshot were observed. Django uses unauthenticated loopback `redis://` on database 0. | Configure an authenticated native TLS listener for the same broker and database index. Preserve its current data volume and verify persistence before any Redis restart. Migrate all producers and consumers before removing the old path. |
| Django and Celery deployment | Gunicorn was active as `ubuntu` from `/home/ubuntu/studyforge/backend`. The checkout is at `6c3922fac11f063b1cda14e2d685757c6c262345` on `deploy/SCRUM-125-backend-postgres-redis`; it has an unrelated untracked `backend/staticfiles/` directory. This checkout lacks SCRUM-127 settings and the S3 job locator. `studyforge-celery.service` is active with `-A config` and no explicit queue flag. Its active queue is `celery`; the application publishes document work to `document-processing`. The observed counts for `document-processing`, `celery`, and Kombu's `unacked` hash were zero. | Approve and stage a current Django API release. Confirm the legacy service's full responsibilities and drain/recheck work at cutover. Retire only the obsolete consumer after the new route is ready. A zero snapshot is not proof that a later cutover is idle. |
| HTTPS, callback and auth | Nginx serves `studyforge-rodians.duckdns.org` with a Let's Encrypt certificate matching that DNS name. HTTPS returned 200 for liveness and 404 for readiness and the job locator. The legacy callback route returned 405 for GET, consistent with its POST contract. The loaded Gunicorn env lacks `PROCESSING_SERVICE_TOKEN`. | Update the API to provide readiness and the job locator, then supply a matching token to Django and worker. Prove the authorized GET locator and POST callback through a controlled fixture or approved end-to-end job. |
| Source storage | Deployed settings use filesystem storage. No `DOCUMENT_STORAGE_*` settings or cloud workload identity were loaded. The default media directory was absent and a read-only query found zero document rows and no file references at the snapshot. | Select an approved private S3-compatible bucket, endpoint, region, and separate Django and worker identities. Recheck uploads and references when writes are paused. If documents appear, back up existing media and verify a SHA-256 copy before switching storage. |
| Certificates and credentials | The working HTTPS certificate covers Django only. PostgreSQL and Redis have no active TLS configuration or demonstrated CA for worker traffic. Gunicorn and legacy Celery use `/etc/studyforge.env` (root:ubuntu, 0640). It declares a Gemini key and existing Django DB settings. The dedicated processing env file is absent. The Compose `/home/ubuntu/studyforge/.env` is currently 0664 and declares the existing PostgreSQL password. | Approve endpoint names and CA trust, the credential store and delivery method, and Gemini reuse if its scope is suitable. Create separate worker DB, Redis, Django secret, shared service token, and scoped object-storage credentials or identity. Include restricted permissions for the Compose env file in the host change and evaluate any rotation separately. Verify Compose still reads its settings as the authorized user and record pre-change ownership/mode for rollback while keeping credential access restricted. |

The old OCI inventory showed no processing OCIR repository and no suitable
Vault entry. The local OCI profile currently fails validation because its user
OCID is missing, so current cloud inventory could not be refreshed. Restore an
authorized read-only profile before any storage or registry resource creation.
The last verified OKE state had one Ready ARM64 node and the frontend only.

## Proposed production approval checkpoints

The candidate preserves both existing data stores. Database port
`5432` and Redis TLS port `6380` are proposed targets. The latter has no
active listener in the verified snapshot. Confirm a maintenance window,
approved CA and secret store, concrete certificate SANs and the approved
bucket/identities before executing any service configuration.

| Checkpoint | Proposed change and impact | Validation and rollback |
|---|---|---|
| Private bindings and host firewall | On `studyforge-api` retain the verified local address for Django. Bind PostgreSQL's private 5432 and Redis's private TLS 6380 to `10.0.0.234` and remove wildcard publishes. During transition keep legacy Redis 6379 loopback-only if needed. In IPv4 `DOCKER-USER` match ingress on `enp0s6` and original destination `10.0.0.234` and published ports after DNAT. Permit the verified pod subnet with source match `-s 10.0.1.0/24`, reject other ingress to those ports, and preserve existing established and local flows. Use Docker-aware persistence with ordering and leave IPv6 service publishes off. Container replacement can briefly interrupt clients. | Review effective NAT and filter order, verify bindings and tests from permitted and denied sources, and prove persistence after an approved controlled restart. On failure keep OCI ingress closed, remove only the new policy and restore the recorded Compose and firewall configuration. [Docker iptables and original destination matching](https://docs.docker.com/engine/network/firewall-iptables/) |
| PostgreSQL TLS, role and migrations | Use native TLS on the existing PostgreSQL instance, with a privately routed certificate name and approved CA. Ahead of the broad HBA entry, allow `hostssl` SCRAM only for `studyforge_processing` DB/role from the verified worker source, and reject other or plaintext pod connections. Keep Django on its existing database and test its TLS client configuration before enabling secure mode. Create `studyforge_processing` with a restricted runtime login and apply `executions.0001_initial` and `0002_callback_delivery` under a separately approved migration identity or explicit owner workflow. The app may briefly reconnect on a DB restart. | Verify `verify-full`, `pg_stat_ssl`, `SELECT 1`, HBA order, runtime privileges, application DB isolation and both migration records. If cutover fails, close new ingress, restore HBA/TLS/Compose and Django config, and preserve both databases. Revoke newly issued access if necessary. Database deletion or a restore requires a separate decision. [PostgreSQL HBA rule order](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html) |
| Redis TLS, auth and queue | Use the running broker with native TLS on proposed port 6380, approved server cert/CA, and separate authenticated Django producer and worker ACL accounts tested for their Celery command/key/channel needs. Keep DB 0 and the same `document-processing` queue. Stage any client-auth certificate requirement if mandated by the approved policy. Migrate clients before removing anonymous access and closing plaintext 6379. Keep the existing Redis volume attached, confirm a fresh durable backup, and drain or record in-flight jobs. Changes to ACLs are shared across both listeners and a restart can affect uploads and pending tasks. | Validate correct hostname and CA, authenticated `PING`, rejected anonymous/invalid trust, and Celery publish, delivery, retry and ack in staging. During a rollback close new ingress first, restore Redis listener/ACL and Django broker settings together, recheck queue state, and keep existing volume/data. Never flush or blindly replay jobs. [Redis TLS](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/) |
| Django, storage and callback | Separately approve the backend upgrade from the verified VM baseline to a tested revision containing SCRUM-127, a private encrypted S3-compatible bucket with distinct Django write and worker read identities, and the shared service token. Set Django S3, `POSTGRES_SSLMODE=verify-full` with CA and a named authenticated `rediss://` broker, then enable the secure-connections flag. The current branch also includes SCRUM-130. Set `AI_FALLBACK_ENABLED=0` during this separate API release unless fallback and its credentials are approved. Pause writes for a final copy/diff if media appears. Drain and disable the legacy consumer only after its scope and outstanding jobs are accounted for. Expect a brief API/upload maintenance window. | Stage on a protected clone. Recheck the migration plan and fresh backups, run checks, validate readiness, existing file access, authenticated locator and callback, and verify the worker can read and hash an approved object. Restore the known-good release, settings, and service states if needed. Reconcile writes made during any approved storage cutover before returning traffic. Preserve objects, media, migration state and broker data. [SCRUM-127 storage cutover](production-document-storage.md) |
| OCI ingress | After VM-side TLS/auth and forwarding controls pass, create `studyforge-api-processing-ingress-nsg` on the existing API VNIC. Add only stateful TCP ingress from `studyforge-oke-pods-nsg` to the verified TLS ports (proposed 5432/6380). The pod subnet already permits egress. Existing public and frontend access should be unaffected. | From an authorized OKE probe verify authenticated DB/Redis TLS, CA/name checking and absence of public access. Capture the exact NSG before/after state. Rollback detaches only the new NSG and removes its rules/resources, preserving other VNIC groups. See the [revised network proposal](#revised-network-proposal) for VCN and VNIC IDs. |
| Registry and Git | Obtain separate approval to push the reviewed official feature commit to Bitbucket and mirror the exact same ref/SHA to `Sanish25/studyforge-arm64-build`. If absent, create private OCIR repository `studyforge/document-processing`. After publication approval dispatch the reviewed workflow on the official ref, verify unique tag, `linux/arm64` and recorded digest. No VM impact. | Compare both refs and verify the built and pulled digest. On failure, leave deployment pinned to its previous image state. Record the failed tag/digest and handle any remote ref or registry cleanup as a separate change. |
| Kubernetes and application check | Create the approved worker ConfigMaps, CA trust, Secret and ServiceAccount in `studyforge`. Use the approved digest and existing pull Secret. Verify dependencies with the exact image before starting one ARM64 worker on `document-processing`. Once explicitly approved, submit one non-sensitive document through Django. The worker does not need a Service, Ingress or frontend change. | Verify the pod Ready, hostname/architecture and image ID, task receipt by OKE, persisted execution, callback status and final application result. Rollback stops the worker and removes only its newly introduced workload and configuration while preserving the existing frontend and all data. |

The application migration snapshot compared with `ee4c054` indicates
`conversations.0002_conversation_message` and `0003_message_tool_trace`,
`notes.0003_note_options_and_sources`, and
`quizzes.0004_survival_sessions` are pending. Verify `migrate --plan` on
the recovered staging database before approving application migrations.

### Credential and certificate handoff

| Input | Source for the approved rollout |
|---|---|
| `PROCESSING_DB_PASSWORD` | New scoped processing login credential in the approved store. Existing Django DB credentials are for the current application role. |
| `PROCESSING_REDIS_URL` | New named worker ACL credential in the approved store. Use `rediss://` with `ssl_cert_reqs=required` and the verified host/DB 0. Give Django its own producer credential. |
| `PROCESSING_SECRET_KEY` and `PROCESSING_SERVICE_TOKEN` | Approved new, distinct secrets. Share only the service token between Django and worker through the store. |
| `GEMINI_API_KEY` | Existing Gunicorn setting is present in `/etc/studyforge.env`. Confirm approved reuse and embedding scope, or issue a separate scoped key. |
| S3 access | Use separate approved identities for Django and worker through the provider's secret or workload identity mechanism. Worker needs `HeadBucket` and scoped `GetObject`, plus any required decryption access. If no approved bucket exists, choose a private S3-compatible provider and scope before creating anything. [OCI S3 compatibility](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm) |
| TLS trust | Approve the private endpoint names/SANs and CA first. Only public CA chains enter the trust ConfigMap. Service private keys remain on the VM or in the authorized key store. Django HTTPS already has public trust. |

## Replacement session and live evidence (2026-11-17)

- One session was approved and created on `studyforge-oke-local-access`
  (`ocid1.bastion.oc1.phx.amaaaaaatvvdeaaaorfihlhxphysx2lvxhd2zgndiggnxtmetn7zheyemllq`).
  Session OCID
  `ocid1.bastionsession.oc1.phx.amaaaaaatvvdeaaaxeyty4fyit7ex5tu52wt7ku3fa5jnsrtnc6h4rqg4lfa`
  became ACTIVE with a 3,600-second TTL and target `10.0.1.9:6443`. The
  workstation egress IP matched the existing `24.155.68.96/32` allowlist.
  The existing key and pinned host file matched the recorded fingerprints.
  The helper opened only `127.0.0.1:16443`. Kubernetes TLS verified using
  the configured CA and server name `10.0.1.9`. No Bastion or network rule
  was created or edited.
- `kubectl cluster-info` and `get nodes` verified the control plane through
  that tunnel and Ready node `10.0.1.63` on `arm64`, Kubernetes `v1.35.2`.
  Namespace `studyforge` is Active. The frontend Deployment was 1/1 Ready.
  The namespace had the frontend pod and ClusterIP Service, the default
  ServiceAccount, ConfigMap `kube-root-ca.crt` (`ca.crt`), and Secret
  `ocir-pull-secret` (`.dockerconfigjson`). No processing worker, processing
  Secret, or NetworkPolicy was returned in that namespace. Secret inventory
  output contained names, types, and key names only.
- From the existing frontend pod, the TCP checks to `10.0.0.234:5432`
  and `10.0.0.234:6379` both failed again. The existing Django private HTTPS
  path returned HTTP 200 with TLS verification successful at
  `https://studyforge-rodians.duckdns.org/api/v1/health/` using `curl --resolve`
  to `10.0.0.234`. The Gemini API endpoint returned HTTP 404 at its public
  root with TLS verification successful. These checks establish basic
  reachability and certificate trust from the frontend pod. Authenticated
  Django source/locator and callback routes, the Gemini key, and S3 access
  remain unverified.
- OCI Run Command is RUNNING and the VM Bastion plugin is STOPPED. No
  existing OCI console connection was returned. The production repository
  documents SSH as `ubuntu` and deployment through systemd. Aashish Dhital's
  SCRUM-125 deployment record makes him the first historical contact.
  Current VM access is unconfirmed. The checked local project env files
  were absent, there was no local `~/.ssh/config`, the SSH agent listed zero
  identities, and the earlier tenancy
  Vault inventory returned no suitable entries. The repository documents
  `/etc/studyforge.env` for the API and a separate worker credential contract.
- One read-only Instance Agent diagnostic completed successfully using
  inline `source.sourceType=TEXT` and `output.outputType=TEXT`. Command OCID
  `ocid1.instanceagentcommand.oc1.phx.amaaaaaatvvdeaaa4zdh654pxpqctd2usgeewct2jdnfcxz6leyarbbim45q`.
  It ran as `ocarun` and found the Gunicorn service active as `ubuntu`
  with working directory `/home/ubuntu/studyforge/backend`. The root-owned
  env file was unreadable to the agent. A PostgreSQL SSLRequest to localhost
  port 5432 returned `N`, so the listener declined TLS. A plaintext
  unauthenticated Redis `PING` to localhost port 6379 returned `PONG`.
  These results describe the listeners on loopback. Confirm any distinct
  private TLS listeners with the operator before proposing access from OKE.
  The agent can provide nonprivileged diagnostics and cannot establish
  live firewall, authenticated DB, or credential evidence. No sudo or
  privilege change was attempted. [Oracle Run Command](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/runningcommands.htm)

## Updated local worker manifest

`services/document-processing/oke-worker.yaml` now targets an ARM64 node and
enforces SCRUM-127's direct storage and secure transport contract. It sets the
standalone Django settings module for probes, reuses the service's readiness
check for DB, Redis and bucket access, and keeps one worker replica, the
existing queue, the 150-second termination grace and the private Django
HTTPS route. The draft intentionally has an unresolved image digest and
requires the separately supplied runtime and trust ConfigMaps. The official
feature branch includes the SCRUM-127 worker source after consolidation.
The command checks the named Redis credential and dependency readiness
before starting Celery. It replaces the shell with Celery as PID 1 after
the check succeeds.

| Source | Required data and conditional dependencies |
|---|---|
| Checked-in ConfigMap `studyforge-processing-worker` | `DJANGO_SETTINGS_MODULE=processing_service.settings`, `PROCESSING_SOURCE_MODE=s3`, `PROCESSING_REQUIRE_DIRECT_STORAGE=1`, `STUDYFORGE_REQUIRE_SECURE_CONNECTIONS=1`, `PROCESSING_DB_SSLMODE=verify-full`, `PROCESSING_DB_SSLROOTCERT=/etc/studyforge/trust/postgres-ca.pem` and the pod-verified Django HTTPS base URL. Retains application defaults for allowed hosts, visibility timeout, Gemini embedding model, 768 dimensions and batch size. Disables AWS EC2 metadata credential lookup. |
| Runtime ConfigMap `studyforge-processing-runtime` | Supply the verified TLS settings `PROCESSING_DB_HOST` and `PROCESSING_DB_PORT`, `PROCESSING_DB_NAME` and `PROCESSING_DB_USER`, and the actual `PROCESSING_STORAGE_BUCKET` and `PROCESSING_STORAGE_REGION`. Provide `PROCESSING_STORAGE_ENDPOINT_URL` for a custom HTTPS endpoint, `PROCESSING_STORAGE_ADDRESSING_STYLE` if it differs from defaults, and `PROCESSING_STORAGE_CA_BUNDLE` as a mounted path if the endpoint uses a private CA. Storage connect/read timeouts default to 3/10 seconds. |
| Secret `studyforge-processing-secrets` | `PROCESSING_SECRET_KEY`, scoped `PROCESSING_DB_PASSWORD`, authenticated `PROCESSING_REDIS_URL` using `rediss://` with `ssl_cert_reqs=required` and the certificate's endpoint name, matching Django `PROCESSING_SERVICE_TOKEN`, and authorized `GEMINI_API_KEY`. Inject the storage access key ID and secret access key together if that is the approved identity, plus `PROCESSING_STORAGE_SESSION_TOKEN` if credentials are temporary. An alternative workload identity needs a verified provider and an explicit credential projection. Service account token automount is disabled. |
| Trust ConfigMap `studyforge-processing-trust` | Verified public CA certificates only. Supply `postgres-ca.pem`, an optional Redis CA file referenced by the URL's `ssl_ca_certs` parameter, and an optional S3 CA file referenced by `PROCESSING_STORAGE_CA_BUNDLE`. The pinned Redis client uses hostname verification by default. If a service needs client certificates, handle the client private keys through a separately approved secret mount and review the required application settings. |
| Existing Secret `ocir-pull-secret` | Confirmed type `kubernetes.io/dockerconfigjson` and key `.dockerconfigjson`. Actual pull of the exact approved digest will verify its repository access. |

The newer worker includes `boto3`. Its read-only storage principal needs the
provider's permissions for `HeadBucket` and `GetObject` for authorized
document keys and any required decryption access. Direct retrieval needs the
authenticated Django `/object/` job locator and matching token. The
installed Redis client's constructor defaults to `ssl_check_hostname=True`.
Gemini embeddings remain unchanged and the worker has no OpenAI configuration.
The separate SCRUM-130 Django release remains outside this rollout.

`kubeconform -strict -kubernetes-version 1.35.2` validated all three draft
resources. The exact Kubernetes probe was run in the local `linux/arm64`
candidate, with networking disabled and disposable settings. It passed on
healthy mocked dependencies and returned failure for each independent DB,
Redis, and bucket outage. `actionlint` passed. Before applying the worker,
verify its dependency path using the exact image and authorized credentials.
The dependency gate blocks the initial subscription. After startup a
readiness failure does not itself pause a running Celery consumer.

## SCRUM-127 compatibility matrix before VM access (2026-11-17)

The requirements come from `development` commit `c9c8936` and its
[SCRUM-127 production runbook](https://bitbucket.org/mth115_super/studyforge/src/c9c8936b9df01cdc9179d8da63d61f871ad00bec/docs/deployment/production-document-storage.md).
This records the pre-SSH evidence. The verified live baseline above
supersedes the earlier unknowns about the inspected services.

| Dependency | Required for the OKE worker | Verified production evidence | Compatibility and proof needed |
|---|---|---|---|
| PostgreSQL transport | Private `PROCESSING_DB_HOST` and port, `PROCESSING_DB_SSLMODE=verify-full`, `PROCESSING_DB_SSLROOTCERT`, and a certificate matching the endpoint name or IP SAN. | Pod TCP to `10.0.0.234:5432` failed. VM loopback 5432 declined TLS. | Blocked. Confirm the OKE-facing endpoint, SAN, CA, firewall path, and verified TLS on an authenticated connection. |
| PostgreSQL auth and schema | Dedicated `PROCESSING_DB_NAME`, restricted `PROCESSING_DB_USER` and `PROCESSING_DB_PASSWORD`. Connection, schema usage, execution table read/write and sequence access as applicable. Both `executions` migrations applied. | A listener responded locally. Authenticated access, role and migrations remain unverified. | Validate privileges and schema with read-only queries. If migration is needed, use a separately approved identity and operation. |
| Redis transport and auth | Authenticated `PROCESSING_REDIS_URL` over `rediss://`, `ssl_cert_reqs=required`, valid hostname, and `ssl_ca_certs` for private trust as needed. Scoped ACL access. | Pod TCP to `10.0.0.234:6379` failed. VM loopback 6379 answered plaintext `PING` without credentials. | Blocked. Confirm the intended listener and prove authenticated TLS succeeds and unauthenticated or untrusted access fails there. |
| Redis broker continuity | Django `CELERY_BROKER_URL` and worker `PROCESSING_REDIS_URL` use the same Redis instance, DB index, and any key namespace. Preserve the `document-processing` queue and ACK/redelivery semantics. | Live broker identity, ACLs, persistence, and pending messages were not inspected. | Compare the secret-backed settings in place. Validate publish, consume, ACK and retry in staging with the planned identities. |
| Django locator and callback | `PROCESSING_DJANGO_API_URL` uses trusted HTTPS. Matching `PROCESSING_SERVICE_TOKEN` authorizes `GET /internal/v1/jobs/{job_id}/object/` and `POST /internal/v1/jobs/{job_id}/result/`. Keep `PROCESSING_REQUIRE_DIRECT_STORAGE=1`. | Pod reached private Django HTTPS and liveness returned 200. Gunicorn was active. | HTTPS reachability verified. Deployed SHA, token match, locator and callback remain unverified. |
| S3 source and trust | `PROCESSING_SOURCE_MODE=s3` and matching Django `DOCUMENT_STORAGE_BACKEND=s3`. Same private bucket, region, addressing style and HTTPS endpoint with trusted CA as applicable. | Live storage mode, provider, bucket, region, and CA are unconfirmed. | Confirm service settings and an approved fixture's locator. Verify hash and bytes with the worker identity. |
| S3 access | Separate read-only identity with `HeadBucket` and scoped `GetObject`. Use approved workload identity or the storage credential pair, plus a session token if temporary. Include decryption access where required. | No approved storage identity or credential source was found. | Review policy and prove read access to one approved object. Check write/delete denial through policy review or isolated staging. |
| Safety switches and secrets | Keep `STUDYFORGE_REQUIRE_SECURE_CONNECTIONS=1` and `PROCESSING_REQUIRE_DIRECT_STORAGE=1`. Inject the five worker keys through the approved store or handoff. Keep Gemini embeddings. | Only the registry pull Secret was observed. The Gemini public endpoint was reachable over TLS. | Worker credentials and a real embedding call remain unverified. The switches enforce client settings but cannot prove server auth. |

The local ARM64 candidate accepted a disposable `rediss://` URL with
`ssl_cert_reqs=required` and `ssl_ca_certs` in redis-py 6.4.0 and
Kombu 5.7.0. Redis-py defaults to hostname verification. This offline
check tested URL parsing only.

## Authorized VM access and credential sources

The dedicated SSH key and administrative access are verified as recorded
above. Use `ubuntu@132.226.88.147` with `~/.ssh/studyforge-api-vm`, identity
agent and password authentication disabled, and strict verification against
the pinned host key. Aashish Dhital authorized this access. The earlier
OCI inventory found no existing console connection or suitable Vault secret.

The root-owned VM file `/etc/studyforge.env` is the documented source for
Django's settings. The `ocarun` agent cannot read it. The operator should
compare the broker configuration, S3 settings, and service-token match in
place and report redacted results. Confirm the approved sources for the new
worker credentials and CA certificates using the handoff table above.

## Contingency plan for secure VM endpoints

Reuse authenticated TLS endpoints if the operator verifies them. Where they
are absent, stage the following against the existing data stores and preserve
the current Django path until a coordinated cutover.

1. **Snapshot the live setup.** Record the deployed Django revision, service and
   Compose settings, current network and listener isolation, HBA order, Redis
   ACLs and persistence, queue depth, and API baseline. Take protected backups
   of the relevant configuration and data using the operator's approved
   procedure. Confirm endpoint names, certificate issuer, and credential sources.
2. **PostgreSQL.** Use native TLS on the existing instance where supported.
   Install a certificate for the private endpoint and keep the server key
   restricted. Before broad HBA rules, scope a `hostssl` SCRAM rule to the
   processing database, worker role and verified source. Reject plaintext and
   other database or role access from that source. Confirm which source
   address PostgreSQL actually sees through Docker. Preserve identified Django
   clients and verify the supported reload or restart procedure.
   [PostgreSQL TLS](https://www.postgresql.org/docs/16/ssl-tcp.html), [HBA rules](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html)
3. **Redis.** Prefer native TLS on the same broker instance and database index.
   If a local consumer needs the current port during staging, select a distinct
   private TLS port with the operator and restrict any retained plaintext path
   to existing verified local clients. Stage tested, named producer and worker
   ACLs, then migrate affected clients before removing unauthenticated access.
   Redis ACLs are instance wide. A separate TLS listener still uses the same
   ACLs. Verify denial of unauthenticated commands on the exact private TLS
   listener. Keep the same queue keys and durable state. A build without native
   TLS or a broker move needs separate review.
   [Redis TLS](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/), [Redis ACLs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
4. **Storage and private path.** Reuse the SCRUM-127 bucket with a separate
   worker identity if live settings confirm that cutover. If Django remains
   on local files, use a separate release and storage plan. Inventory and
   verify existing objects before changing the upload path. Only after
   host-side TLS, auth, and firewall validation, prepare a distinct approval
   for ingress from the OKE pod NSG to the actual verified TLS ports. If the
   ports differ from 5432 and 6379, revise the manifest and network proposal
   together. Pod egress already permits the path.

### Validation, expected impact, and rollback

| Step | Validation and application impact | Rollback |
|---|---|---|
| PostgreSQL TLS and HBA | Run read-only `SELECT 1` with `verify-full`. Check the session in `pg_stat_ssl`, privileges, and migration records. Verify rejected plaintext, invalid trust, and unauthorized roles. A restart or HBA error can interrupt sign-ins and document operations. | Keep the OKE path closed or remove newly approved ingress first. Restore the known-good HBA, TLS, and listener files with the approved service procedure. Verify Django and DB health. Preserve database data and volumes. |
| Redis TLS and ACLs | Verify trusted hostname, authenticated `PING`, and denial without auth. Check both clients use the same broker and index. Exercise delivery, ACK and retry in an isolated staging queue. ACL changes or restarts can stop new jobs or interrupt in-flight work. Schedule the transition and reconcile pending and unacked jobs. | Remove new OKE access first. Restore prior listener and ACL configuration in coordination with the saved Django broker setting. Confirm API health and queue state. Preserve persistent Redis data and reconcile jobs before any replay. |
| Storage and Django | Check trusted S3 HTTPS, `HeadBucket`, authorized locator and `GetObject` for an approved fixture. Compare SHA-256, then verify readiness and existing upload/read behavior. A cutover can briefly pause uploads. | Restore the known-good release and prior storage configuration if needed. Keep original files, copied objects, and DB keys. Reconcile writes made during the approved cutover before routing uploads back. |
| Private path and worker | After separate network approval, verify authenticated TLS from OKE and confirm public access stays closed. Validate dependencies before starting Celery. After separate approval, match one real document's OKE job, execution row, callback and final result. | Stop the new worker and remove its rollout resources if applicable. Detach and remove only the new NSG based on current membership. Verify frontend and Django baseline. |

This checkpoint updates the runbook only. Production ports, VM settings,
registry and workloads remain at the observed baseline.

## Earlier operator handoff checklist

The read-only SSH inspection above covers these original requests. Use this
checklist to revalidate the live settings after approved changes. Use the
approved secret store or on-host handoff for values.

1. The deployed Django commit, whether the authenticated S3 job locator is
   served, and the configured storage mode, private bucket/region, HTTPS
   endpoint/CA, and read-only worker identity source.
2. Host firewall and container-forwarding verdicts for OKE pod sources to
   ports 5432 and 6379, including the relevant nftables/iptables and Docker
   rules, listener bindings, and any separately configured private TLS
   endpoints. State the certificate names, issuing CA sources and expected
   broker transport and auth. If TLS or authentication must be added,
   describe the exact configuration and restart impact for separate approval.
3. Redacted success/failure for authenticated PostgreSQL `SELECT 1`,
   processing role access and permissions, `executions_execution`, and
   `executions.0001_initial` / `0002_callback_delivery` in
   `django_migrations`. Provide authenticated Redis `PING` and confirm the
   worker and Django use the same broker and database index.
4. The approved sources for the five runtime keys, the worker storage
   identity or credential set, and the certificate trust material. Confirm
   the token matches Django without exposing its value.

**Resume from this milestone.** Collect the existing operator's evidence
and confirm TLS/authenticated endpoints before approving ingress. If current
listeners are the only ones, review a separately authorized service TLS and
Redis authentication change before exposing them even to OKE. Keep image
publication, ConfigMaps and Secret creation, database migration, deployment
and the production document test as explicit approval gates.

## Resume checkpoint

Use `/Users/sanishshrestha/Documents/studyforge` on the official branch
`feature/SCRUM-122-deploy-kubernetes-to-processing` for all new work.
The official branch was fast-forwarded to `origin/development` at
`ee4c054271abcb511d7863a92906efb04f79748a` before the five artifacts were
consolidated. The original `chore/scrum-122-arm64-pipeline` worktree at
`/Users/sanishshrestha/Documents/studyforge-scrum-122` is retained as a
recovery reference at `bd7cb9cbebd790106913b967b1294de3724b45fe`.
The five deployment files are in local consolidation commit
`b62bcec14b4821bec0b2d451cebf8355d1c006ca`.
The current Bitbucket pipeline was preserved. The Cloud Shell preflight is
legacy and exits without contacting infrastructure. Use this runbook and
the dedicated reconnect helper for current validation.

**Next action.** Confirm the approved CA, credential store, bucket/identities
and maintenance window. Review the staged service/API cutover and backend
regression failures before seeking production approval.

## SCRUM-130 review and worker integration

- The Bitbucket branch `feature/SCRUM-130-automatic-OPENAI-backup` resolves to
  `a7ffc4bb39bd237d97920fe899697df3abe94295`. The last implementation commit
  is `080b9eb6b6a82a75ee38d2e3093aa4b3464acfb8`. The completion report is
  `docs/ai-dev-reports/curiosity-report-Shrestha-SCRUM-130-2026-11-17.md` at the
  branch tip. The later Bitbucket audit verified squash merge
  `ee4c054271abcb511d7863a92906efb04f79748a` on `development`
  with the same tree as the feature tip. This is the parent of the official
  consolidation. The deployed Django checkout still predates SCRUM-130.
- SCRUM-130 changes Django notes, quizzes, and Pandu answer generation. Each
  request starts on Gemini and can invoke the OpenAI fallback once for a
  qualifying provider failure. The worker tree is identical between
  `development` and the SCRUM-130 tip. Worker and retrieval embeddings remain
  Gemini. Django already includes the OpenAI SDK, and the worker needs no
  OpenAI dependency or key. With fallback enabled by default, the Django
  Gemini routes require `OPENAI_API_KEY`. Set approved
  `OPENAI_NOTES_MODEL`, `OPENAI_QUIZ_MODEL`, and `OPENAI_RAG_MODEL` if the
  existing feature model variables contain Gemini model names. The fallback
  release belongs in the separate Django release process.
- An isolated archive of the committed SCRUM-130 code passed all 16 targeted
  tests with `PYTHONPATH=backend python3 -m unittest discover -s backend/apps/tests -p 'test_scrum130_*.py' -v`.
  The tests use mocks and establish local behavior. Production fallback is
  unverified.
- The recovery branch predates SCRUM-127. The consolidated official branch
  contains SCRUM-127 and SCRUM-130 via the fast-forward and adds only the
  five reviewed deployment files. Worker code remains independent of the
  Django OpenAI settings. Remote updates and publication remain approval gates.
- The current `development` candidate passed
  `python3 services/document-processing/check.py` from a complete Git archive.
  Docker reported `linux/arm64`. Both workers registered the document task
  and consumed the isolated queue, 68 service tests passed in each of three
  contexts, 23 persistence tests passed, and both processing migrations ran
  in the disposable database. The local tag was
  `studyforge-document-processing-check:local` with image index digest
  `sha256:b2fc086de959bf453f814859bbae8ac80b194547e2243f61380425babe0c3cf4`.
  The harness cleaned up its test stack. No OCIR image was published.

### Production storage and transport contract

The current `development` runbook for SCRUM-127
(`docs/deployment/production-document-storage.md`) calls for direct S3 source
retrieval on production workers. Its code has separate Django-stream and S3
modes, and the production configuration calls for `PROCESSING_SOURCE_MODE=s3`,
`PROCESSING_REQUIRE_DIRECT_STORAGE=1`, and
`STUDYFORGE_REQUIRE_SECURE_CONNECTIONS=1`. The old manifest and findings below
describe the original Django-stream configuration.

- Confirm live Django source mode, shared bucket and region, internal HTTPS
  endpoint, and token configuration. Production direct mode needs a read-only
  storage identity or credential source, bucket/region, and the provider
  endpoint and trust bundle if applicable. The job locator is
  `GET /internal/v1/jobs/{job_id}/object/`, while the result callback remains
  unchanged. Confirm the deployed backend supports the locator before rollout.
- Verify PostgreSQL certificate trust and a matching TLS name for
  `PROCESSING_DB_SSLMODE=verify-full`. Confirm the broker supports authenticated
  `rediss://` with `ssl_cert_reqs=required`. Service bind and TCP reachability
  alone do not prove either. Use matching certificate names for private routes.
- Confirm the worker identity can read an approved object and perform the
  bucket readiness check. If live services do not meet the production
  contract, record the exact gaps and obtain separate approval for the
  necessary backend, storage, TLS, or credential changes.

## Initial production evidence before SSH access

- OCI browser authentication succeeded for `studyforge-scrum122-local`.
  `oci iam tenancy get` and `oci os ns get` confirmed the expected tenancy
  and registry namespace `axcyydnoof5f`. In `us-phoenix-1`, `oci ce cluster get`
  confirmed `studyforge-oke` was ACTIVE on `v1.35.2` at `10.0.1.9:6443`.
  `oci ce node-pool list` showed `studyforge-arm-workers` ACTIVE on
  `VM.Standard.A1.Flex`. Live node readiness and namespace objects still
  need to be reread over the tunnel.
- `oci bastion session list` returned only the former session in `DELETED`
  state. The Bastion itself is ACTIVE and still allows `24.155.68.96/32`.
  The current public egress IP matched. Request approval for one 3,600-second
  session on the existing Bastion to `10.0.1.9:6443` using the existing
  dedicated key and `127.0.0.1:16443` with TLS verification.
- OCIR still has only the private `studyforge/frontend` repository.
  `gh api` confirmed push permission on the build mirror, the workflow's
  default branch, the two OCIR secret names, and an empty environments list.
  Actual registry authentication will be proven by authorized publication
  and pull of the exact digest.
- The production VM runbook documents the authorized `ubuntu` SSH route,
  Gunicorn's root-only `/etc/studyforge.env`, and separate Compose PostgreSQL
  and Redis. Its ownership or operator assignment is unverified. The current
  OCI console connection list and tenancy Vault secret inventory returned no
  entries. Existing team access is the least invasive option. OCI Run Command
  still has only the established unprivileged evidence. Bastion TCP forwarding
  by itself requires valid VM login, and console recovery would require its
  own approval. See Oracle's [Run Command permissions](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/runningcommands.htm)
  and [instance console access](https://docs.oracle.com/en-us/iaas/Content/Compute/References/serialconsole.htm).

### Evidence needed from the existing VM operator

Ask for the deployed backend Git revision, active firewall and Docker
forwarding policy for pod sources, and the effective behavior for TCP 5432 and
6379. The operator can inspect with `sudo iptables-save` and
`sudo nft list ruleset` as applicable. Report only relevant rules and verdicts.
Check PostgreSQL login, `SELECT 1`, `executions_execution` permissions and
`django_migrations` for both processing migrations using an authorized
credential and read-only queries. Verify Redis authentication and `PING` using
the authorized URL, and compare broker identity and database index to Django's
`CELERY_BROKER_URL` without displaying either URL. Confirm TLS mode and
certificate names, storage mode, and sources for the runtime keys. The VM env
file may cover Django-side values. The worker has a separate credential
contract. Share key names and redacted outcomes through the team procedure.

### Revised network proposal

The OCI inventory returned VM VNIC
`ocid1.vnic.oc1.phx.abyhqljsh2jf5fomi5wwmsyyiqr3hq7yt2p22js35zqlxksheflvp4sf557q`
with no NSG. The source pod NSG is
`ocid1.networksecuritygroup.oc1.phx.aaaaaaaaoyklcloxyrtx6na4c6lwpe32c2pxxcxqwrbeglkuydxm3qf5zrga`.
The NSG member VNIC
`ocid1.vnic.oc1.phx.abyhqljrrfij7gefgo56i7pty3qnk7ta6hvetuzjrv4zti7kflhe4z2tqgcq`
is on the private `10.0.1.0/24` subnet and owns the existing frontend pod
IP `10.0.1.32`. Its subnet
security list already permits stateful IPv4 egress to all destinations. OCI
applies the union of security-list and NSG permissions for VCN-native pods.
The missing OCI permission is VM ingress. Both are in the same VCN, with
public default routing through the internet gateway, private default routing
through NAT, and no conflicting intra-VCN route in the inspected tables.
Both VNICs and both checked private IP entries had no route-table override.
[Oracle OKE security rule configuration](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfig.htm)

After confirming the operator evidence, an authenticated TLS service path on
both ports, and explicit network approval, create a dedicated
`studyforge-api-processing-ingress-nsg` in `studyforge-vcn` with two
stateful ingress rules. Use protocol `6`, `sourceType=NETWORK_SECURITY_GROUP`,
the existing pod NSG OCID as `source`, and
`tcpOptions.destinationPortRange` proposed as `5432..5432` and `6380..6380`
respectively. Apply using `oci network nsg rules add`, then attach only the new
group to the API VNIC with `oci network vnic update --vnic-id ... --nsg-ids ...`
using a fresh snapshot of current membership. The previously proposed
`10.0.1.0/24` CIDR also covers the path, but the NSG source limits access to
members of the verified pod group. No pod egress change is proposed.
Reinspect the rules and VNIC with `oci network nsg rules list` and
`oci network vnic get`. Run the recorded pod TCP checks and then the
credentialed TLS probes without logging secrets. If rollback is needed,
remove only this new NSG from the VNIC's current memberships and delete it.
Preserve the VM's existing public rules and unrelated memberships.

## Original checkpoint and task contract

- OCIR image: `phx.ocir.io/axcyydnoof5f/studyforge/document-processing`
- The saved checkpoint referenced historical tag
  `arm64-46d02f8a5edc998768c9f19e716a3d6019a869c1`; it is not present in the
  current OCIR inventory and must be replaced with the approved build digest.
- Cluster: `studyforge-oke`, `us-phoenix-1`, Kubernetes `v1.35.2`
- Namespace: `studyforge`. Proposed Deployment: `processing-worker`, one replica.
- Celery app: `processing_service.celery:app`; queue: `document-processing`
- API VM: `10.0.0.234`; OKE node subnet: `10.0.1.0/24`

OCI read-only inventory verified the signed-in user has the tenancy's
`Administrators` group membership. The cluster OCID is
`ocid1.cluster.oc1.phx.aaaaaaaazuokzxkbuwoqgz3ctjvqxww4d3vrwwhvpyrkbth55cmidganrxna`,
private API endpoint `10.0.1.9:6443`; VCN
`ocid1.vcn.oc1.phx.amaaaaaatvvdeaaaxwizqjrvvtgwyna6nm3so5fezrmz43ze2344ujwrabga`.

The task uses PostgreSQL for execution and callback staging, Redis as the
Celery broker, and Gemini for embeddings. Django sends
`processing_service.tasks.process_document_task` with the job ID, document ID,
and source SHA-256. The worker authenticates with `PROCESSING_SERVICE_TOKEN`
to fetch `GET /internal/v1/jobs/{job_id}/document/` and send
`POST /internal/v1/jobs/{job_id}/result/`. Django streaming remains available
in the original configuration. Use the production direct-storage contract
above when preparing the current worker.

The local `python3 services/document-processing/check.py` run passed on
ARM64 with queue registration, 60 service tests across three contexts,
23 persistence tests, migrations `executions.0001_initial` and
`executions.0002_callback_delivery`, and cleanup of disposable containers.
The local image `studyforge-document-processing-check:local` was
`linux/arm64` with digest
`sha256:5210b6f813dffc86be2eea86c320064d577f258987080c29a8c254ec8cc313d9`.
`actionlint` passed for `.github/workflows/processing-arm64.yml`. These are local
results. The production image digest, schema, and worker remain unverified.

## Publishing workflow

`.github/workflows/processing-arm64.yml` is manual-only, uses the native ARM64
runner, and publishes only the unique tag
`arm64-${GITHUB_SHA}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`. It checks the
published image by pulling that tag for `linux/arm64` and records the image
digest in the workflow summary.
GitHub repository-level secrets `OCIR_USERNAME` and `OCIR_AUTH_TOKEN` exist by
name. The referenced `ocir-publish` environment did not exist, so the workflow
no longer references it or creates it implicitly. Do not dispatch until the
explicit publication approval.

The live OCI repository inventory contains `studyforge/frontend`, but no
`studyforge/document-processing` repository or image. The OCI auth-token value
is not retrievable, and GitHub secret values were not read. Existing secret
names are verified; do not replace credentials unless authentication proves
they are invalid.

## Kubernetes settings at the saved checkpoint

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
| `ocir-pull-secret` (`kubernetes.io/dockerconfigjson`) | `phx.ocir.io` login; reuse only if read-only inspection confirms the registry host and Secret type |
| `studyforge-processing-secrets` | `PROCESSING_REDIS_URL`, `PROCESSING_SECRET_KEY`, `PROCESSING_DB_PASSWORD`, `PROCESSING_SERVICE_TOKEN`, `GEMINI_API_KEY` |

The previous ConfigMap pointed the processing DB to `studyforge_processing` at
`10.0.0.234:5432`. It reads Redis URL from the Secret. Django URL is
`https://studyforge-rodians.duckdns.org`, with a Pod host-alias to private IP
`10.0.0.234` so TLS keeps its hostname while traffic stays on the VCN.

The production processing DB must already exist and have the service migrations
applied. This deployment does not create or migrate a DB. Current task code
writes an `Execution` before processing, so missing schema blocks the worker.

## Verified network and VM findings

OKE and API VM share VCN `studyforge-vcn` (`10.0.0.0/16`). The API VNIC is
`10.0.0.234` in `10.0.0.0/24` and has no NSG. The OKE worker and pod subnet is
`10.0.1.0/24`; CNI is `OCI_VCN_IP_NATIVE`, with one active A1 Flex node.

`studyforge-api` was RUNNING (`VM.Standard.A1.Flex`, 2 OCPUs, 12 GB),
public IP `132.226.88.147`, instance OCID
`ocid1.instance.oc1.phx.anyhqljstvvdeaackb5amcldekrif64ajcmbzrbmoz6xiffiu5q54mt22pnq`.
The public subnet security list allows ingress on TCP 22, 80, and 443 from
`0.0.0.0/0` and has no ingress rule for 5432 or 6379. The OKE pod NSG has a
VM-specific egress rule for TCP 80 and none for 5432 or 6379. The private
API NSG allows TCP 6443 and 12250 from `10.0.1.0/24`. The approved Bastion
private endpoint already fits that rule. Frontend pod `10.0.1.32` could not
connect to `10.0.0.234:5432` or `10.0.0.234:6379`. The worker's private HTTPS
path to Django and outbound Gemini path still need validation. The recorded
pod TCP check was:

```sh
kubectl --kubeconfig "$HOME/.kube/studyforge-oke-bastion" -n studyforge \
  exec deploy/studyforge-frontend -- sh -c '
    for port in 5432 6379; do
      if nc -z -w 3 10.0.0.234 "$port"; then
        echo "10.0.0.234:$port reachable"
      else
        echo "10.0.0.234:$port failed"
      fi
    done'
```

Read-only Instance Agent Run Command confirmed listeners on `0.0.0.0:5432`
and `0.0.0.0:6379`, with IPv6 listeners also present. The agent was RUNNING,
executed as `ocarun`, and `sudo -n` required a password. Previous SSH
authentication failed and no working VM private key was verified. The
console connection list returned no entries. The two additional commands
yielded no service readiness evidence:

| Run Command ID | Outcome |
|---|---|
| `ocid1.instanceagentcommand.oc1.phx.amaaaaaatvvdeaaack7hkacxbecjfr6rmoen7vkorfspzj4vgek3lqmgnvoa` | `pg_isready` and `redis-cli` unavailable (exit 127). |
| `ocid1.instanceagentcommand.oc1.phx.amaaaaaatvvdeaaawglyhea5fgdcz7aplaq3orjjnitv4xzunkiv2mvlts7q` | Agent wrapper attempted a malformed executable path and the Python probe did not run (exit 127). |

Retrieve either recorded result with `oci instance-agent command-execution get`
using the profile flags below, `--instance-id` set to the VM OCID above, and
`--command-id` set to the recorded ID. Repeating these commands will only
retrieve their existing results.

### Remaining access and credentials

- An authorized VM administrator or existing sudo-capable access is needed to
  verify host firewall policy from `10.0.1.0/24`. Ask the administrator for
  read-only evidence first. VM access recovery or any host firewall change
  requires its own approval.
- An authorized PostgreSQL credential is needed for `SELECT 1`, checking
  `executions_execution`, and checking `django_migrations` for both processing
  migrations in `studyforge_processing`. An authorized Redis URL is needed for
  `PING` and to confirm the worker and Django producer share a broker and queue.
- An approved source is needed for the five proposed worker Secret keys above.
  Confirm `PROCESSING_SERVICE_TOKEN` matches Django's configuration and that the
  Gemini credential is authorized for the configured model. No suitable Vault
  secret was surfaced in the audit. Keep values out of logs, Git, and chat.

## Verified Bastion and cluster inventory

| Resource | Verified configuration |
|---|---|
| Bastion `studyforge-oke-local-access` | `STANDARD`, observed `ACTIVE`, private endpoint `10.0.1.235`, client `24.155.68.96/32`, OCID `ocid1.bastion.oc1.phx.amaaaaaatvvdeaaaorfihlhxphysx2lvxhd2zgndiggnxtmetn7zheyemllq` |
| Target subnet | Private `10.0.1.0/24`, OCID `ocid1.subnet.oc1.phx.aaaaaaaauoqusfcekjzjhofsj3h7bzqhei5abz2kifjuyavhgr7oxbpts5la` |
| Approved session | `PORT_FORWARDING`, observed `ACTIVE` during verification, target `10.0.1.9:6443`, TTL `3600` seconds, OCID `ocid1.bastionsession.oc1.phx.amaaaaaatvvdeaaaq54p3lvzrnavrectihwgsoabbwcokklm4trwdzivr2kq` |
| Local listener | `127.0.0.1:16443`. Stopped at pause and verified closed with `lsof -nP -iTCP:16443 -sTCP:LISTEN`. |

Before creation, subnet `10.0.1.0/24` egress was verified as allowing all
destinations, 25 private IP addresses were assigned with 228 usable addresses
available, the workstation egress address was rechecked as `24.155.68.96`, and
the Bastion inventory returned no suitable existing resource.

The dedicated tunnel kubeconfig is `~/.kube/studyforge-oke-bastion`; the
existing `~/.kube/config` current context remains untouched. `kubectl get
nodes` verified one Ready Oracle Linux 8.10 `arm64` A1 node (`10.0.1.63`,
Kubernetes v1.35.2). Namespace `studyforge` is Active. Its only Deployment is
`studyforge-frontend` (1/1 ready); no processing worker exists. The only
ConfigMap is `kube-root-ca.crt` (`ca.crt`). The frontend image was
`phx.ocir.io/axcyydnoof5f/studyforge/frontend:scrum122-patched`.
`ocir-pull-secret` is the only
namespace Secret and its only key is `.dockerconfigjson`. Its decoded registry
host list includes `phx.ocir.io`; values were not printed. There is no
`studyforge-processing-secrets` yet. The OCI user can list nodes, get secrets,
and create deployments. No Kubernetes resource was changed.

The local kubeconfig uses `https://127.0.0.1:16443`, TLS server name `10.0.1.9`,
embedded CA data, and verification enabled. `~/.kube/studyforge-oke` retains
the direct private endpoint. Preserve both files and the OCI profile below.
The dedicated Ed25519 key and public key are `~/.ssh/studyforge-oke-bastion`
and `~/.ssh/studyforge-oke-bastion.pub`. The private key is mode 600 and the
key fingerprint is `SHA256:/PWmKBRWlo9xOrrQ5wSAmE/Uk1+elIVBwiDPwdnz1fc`.
The SSH host is `host.bastion.us-phoenix-1.oci.oraclecloud.com`.
Its key was pinned on first use in `~/.ssh/known_hosts.studyforge-bastion`
with fingerprint `SHA256:hk4ZIr8TKKIs14X2Lz082CrMS5s3zE5IdeeYlMMl498`.
OCI session metadata supplied no independent host key for comparison.

## Local VS Code access on resume

1. From the SCRUM-122 worktree, check the existing OCI profile:

```sh
cd /Users/sanishshrestha/Documents/studyforge
oci --profile studyforge-scrum122-local --auth security_token \
  --region us-phoenix-1 iam region list --output table
```

2. If OCI reports an expired token, run the following command and complete
   the Oracle login in the opened browser. Wait for `Completed browser
   authentication process!` and repeat the region check. The command rewrites
   the dedicated profile under `~/.oci`, which requires a sandbox override if
   the managed terminal denies the local write.

```sh
oci session authenticate --region us-phoenix-1 \
  --profile-name studyforge-scrum122-local
```

3. Open the tunnel when access is needed. `start` and `reconnect` require an
   existing `ACTIVE` session. Use `reconnect` to restart a managed listener in
   place.

```sh
bash scripts/scrum122-oke-connect.sh start
bash scripts/scrum122-oke-connect.sh status
kubectl --kubeconfig "$HOME/.kube/studyforge-oke-bastion" get nodes -o wide
```

The helper uses only the dedicated kubeconfig, SSH key, and pinned host file.
Its transient session ID, PID, and SSH log live under
`/private/tmp/studyforge-scrum122-oke`. The initial tunnel and Kubernetes CA
verification succeeded with Ready=1/1. The pause revision changed session
selection and local shutdown behavior. Its offline checks ran with the tunnel
closed.

4. If the recorded session has expired or its OCID is gone, recheck the Bastion
   and its client allowlist. Compare the current public egress IP to the
   verified `24.155.68.96/32`. Any allowlist change or replacement session
   requires explicit approval. Once authorized, run the following command to
   create one 3600-second session on the existing Bastion:

```sh
session_id=$(oci --profile studyforge-scrum122-local --auth security_token \
  --region us-phoenix-1 bastion session create-port-forwarding \
  --bastion-id ocid1.bastion.oc1.phx.amaaaaaatvvdeaaaorfihlhxphysx2lvxhd2zgndiggnxtmetn7zheyemllq \
  --display-name studyforgeokeapifwd --key-type PUB \
  --ssh-public-key-file "$HOME/.ssh/studyforge-oke-bastion.pub" \
  --session-ttl 3600 --target-private-ip 10.0.1.9 --target-port 6443 \
  --query 'data.id' --raw-output)
oci --profile studyforge-scrum122-local --auth security_token \
  --region us-phoenix-1 bastion session get --session-id "$session_id" \
  --query 'data."lifecycle-state"' --raw-output
```

Once the read-only state check returns `ACTIVE`, run
`bash scripts/scrum122-oke-connect.sh start "$session_id"` and verify the
Ready node. The helper records that session ID for later reuse. If the create
call fails or the state lookup is inconclusive, check the Bastion session
inventory before retrying creation.

5. To stop local access, run `bash scripts/scrum122-oke-connect.sh stop`, then
   `lsof -nP -iTCP:16443 -sTCP:LISTEN`. The latter should have no listener.
   If the managed sandbox rejects the signal, verify the SSH listener's PID
   and loopback endpoint and use the permitted terminal or sandbox override to
   signal that PID. Stopping the local listener leaves the OCI resources in
   place and the session expires automatically.

## Evidence tracker (2026-11-17)

| Component | Current evidence | Status | Remaining work / proposed action | Approval required |
|---|---|---|---|---|
| Local source of truth | `/Users/sanishshrestha/Documents/studyforge` on `feature/SCRUM-122-deploy-kubernetes-to-processing`. See [Resume checkpoint](#resume-checkpoint) for the consolidation commit lookup. | VERIFIED | Request approval before pushing to Bitbucket or GitHub | Yes for remote writes |
| Local OCI authentication | Browser session previously verified. Local validation now reports expired. | EXPIRED | Reauthenticate before OCI inventory or changes | No cloud change |
| Private OKE connectivity | Approved replacement session and TLS-verified `kubectl get nodes` succeeded | VERIFIED | Reuse session while active | Yes, for a future session or allowlist change |
| Kubernetes authorization | `get nodes`, namespace and RBAC checks succeeded | VERIFIED | None | No |
| VM administration | Dedicated SSH key verified for `ubuntu`, pinned host key matches, and `sudo -n -l` shows `NOPASSWD: ALL`. | VERIFIED | Use verified access for approved staged changes | Yes for production writes |
| Registry availability | `studyforge/frontend` exists; processing repository and image absent | MISSING | Create private repository if still absent, then publish approved image | Yes |
| ARM64 image | Fresh local worker harness passed. Docker reports `linux/arm64` at local image ID `sha256:e3c94ebfffc7e4c7e09b75765442c0bfa761e008ed6f22ee3686bee52ffbb761`. | LOCAL VERIFIED | Publish the reviewed commit with unique tag and capture registry digest | Yes, remote push/publication |
| PostgreSQL | Live TLS off and processing DB/role absent. | BLOCKED | Stage verified TLS, restricted database/role and migrations before OCI ingress. | Yes |
| Redis | Live TLS off and default ACL user has no password. Existing Django broker is loopback DB 0. | BLOCKED | Stage authenticated private TLS and move producer/worker to the same DB with named ACLs. | Yes |
| Network security | Existing OCI ingress absent and pod egress permits the path. Docker publishes wildcards with empty DOCKER-USER. | BLOCKED | Restrict publishes and forwarding first. Then add only VM NSG ingress from the pod NSG to verified TLS ports. | Yes |
| Django and storage | Live SCRUM-125 checkout has no S3 locator, no service token loaded and uses filesystem storage. | BLOCKED | Prepare a separately approved API/secure storage cutover. Verify the backend release test results first. | Yes |
| Secrets and ConfigMaps | Last live namespace had only `kube-root-ca.crt` and `ocir-pull-secret`. VM does not hold dedicated worker credentials. | BLOCKED | Approve new scoped worker credentials, storage identities, runtime configuration and CA trust. | Yes |
| Migrations | Local isolated DB applied both processing migrations. No production processing DB exists. Application migration history differs from the candidate as noted above. | BLOCKED | Verify application migration plan on a protected clone, then approve both database plans. | Yes |
| Worker deployment | Updated local manifest schema and dependency probes passed. Live namespace has only the frontend Deployment. | PARTIAL | Confirm production inputs, pin approved digest, and validate dependency access before rollout. | Yes |
| Task submission and callbacks | Live callback path exists, but token and new locator are missing. | BLOCKED | Submit a non-sensitive real document after approved upgrade and worker rollout, then verify callback. | Yes, production deployment/test |
| End-to-end document processing | No production task has been submitted | MISSING | Complete the full API → queue → OKE worker → DB/callback/result test | Yes, production deployment/test |

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
kubectl --kubeconfig "$HOME/.kube/studyforge-oke-bastion" -n studyforge delete deployment processing-worker
kubectl --kubeconfig "$HOME/.kube/studyforge-oke-bastion" -n studyforge delete configmap studyforge-processing-worker
kubectl --kubeconfig "$HOME/.kube/studyforge-oke-bastion" -n studyforge delete serviceaccount processing-worker
```

Record the pre-deploy image and resource state first. If a Deployment already
exists, do not overwrite it; use a revision rollback only after confirming it
belongs to SCRUM-122. Do not touch other workloads, the production VM, API,
frontend, Redis, or database.

## Approval-specific execution notes

The following work remains gated and has not been performed:

1. **VM endpoint readiness.** Verify the existing private endpoints with
   the operator. If either lacks TLS or authentication, separately approve
   the specific host or service changes, impact and rollback from the
   contingency plan above. Confirm the approved credential sources.
2. **Network path.** Confirm the host firewall, TLS, and current membership,
   then use the revised VM-only ingress proposal above. Scope is one new NSG
   in VCN `ocid1.vcn.oc1.phx.amaaaaaatvvdeaaaxwizqjrvvtgwyna6nm3so5fezrmz43ze2344ujwrabga`,
   two stateful TCP rules from the verified pod NSG, and attachment to the API
   VNIC only. Expected impact is private pod access to the confirmed
   authenticated TLS listeners. Verify both ports from OKE, then validate
   PostgreSQL certificate name, authenticated `SELECT 1` and schema, and Redis
   verified TLS/authenticated `PING`. On rollback, detach and delete only the
   new group using the current VNIC membership snapshot.
3. **Image publication.** Create private OCIR repository
   `studyforge/document-processing` if still absent. Push the reviewed branch
   `feature/SCRUM-122-deploy-kubernetes-to-processing` to
   `Sanish25/studyforge-arm64-build` only after approval, dispatch
   `processing-arm64.yml` explicitly for that ref after publication approval,
   and record its unique tag and immutable digest. Repository secrets exist by
   name, but their values have not been read. The repository creation command
   after approval is:

   ```sh
   oci --profile studyforge-scrum122-local --auth security_token \
     --region us-phoenix-1 artifacts container repository create \
     --compartment-id ocid1.tenancy.oc1..aaaaaaaamic5qhkdlchwwn7ht3jflgtlmeqktb5l3uufwbtzn5nx5b4b47ia \
     --display-name studyforge/document-processing --is-public false
   ```

4. **Runtime credentials and workload.** In namespace `studyforge` use the
   published digest. Scope is ConfigMaps `studyforge-processing-worker`,
   `studyforge-processing-runtime` and `studyforge-processing-trust`, Secret
   `studyforge-processing-secrets`, ServiceAccount `processing-worker` and
   Deployment `processing-worker`. Reuse `ocir-pull-secret`. If no existing
   authorized worker environment can verify dependency access, include a
   disposable probe Pod with the exact image and the same Secret references
   in this approval. Verify DB, Redis, bucket, and private Django HTTPS
   before letting Celery consume jobs. Confirm no name collisions. After
   rollout report image ID, Ready node and pod, task registration, and queue.
   Rollback removes the new workload, probe Pod, and only resources created
   for this rollout. Credential provisioning is a separate approval.
5. **Database and task.** Verify database access, `Execution` table,
   and migration state with read-only requests before rollout. If a migration is missing, pause for a
   separate explicit database-change approval. After the worker is healthy,
   process one user-approved non-sensitive real document and verify the result
   and callback. Roll back only the new worker resources and newly created
   Secret if validation fails.

The `ocir-publish` GitHub environment did not exist in the repository's
environment inventory; it had no configured reviewers or protection rules.
The workflow is manual `workflow_dispatch`, uses `contents: read` token
permission, and relies on repository write access to dispatch plus the
existing repository secrets. GitHub's private-repository branch-protection and
ruleset API returned 403 on the current plan, so those rules could not be
independently inventoried. Removing the absent environment reference therefore
did not bypass an active configured approval gate, although publication still
remains explicitly approval-gated for this task. Establish a real protected
publishing environment or equivalent repository policy if GitHub itself must
enforce reviewer approval before a future dispatch.

## Local validation on the consolidated branch

- Workflow lint, Kubernetes v1.35.2 schema validation (3 resources),
  `bash -n` and ShellCheck passed. The legacy Cloud Shell script is
  syntactically valid and refuses direct execution.
- The fresh local ARM64 worker build passed worker registration and queue
  consumption, 68 service tests in each of three contexts, 23 persistence
  tests, both processing migrations and the Redis outage check.
- The manifest's exact startup wrapper blocked a failed check and preserved
  the command arguments on success. The probe passed with healthy mocked
  dependencies in the ARM64 image and rejected missing Redis authentication
  and independent DB, Redis and storage failures.
- The full backend regression including the isolated S3 integration ran
  against disposable PostgreSQL. It reported 791 passed and 529 subtests
  passed, including SCRUM-127 S3 integration and all 16 SCRUM-130 tests.
  Two tests in the inherited application baseline failed. The question API
  test references an undefined `RetryableProcessingError`, and the
  Gemini factory test omits the OpenAI key with fallback enabled. No backend
  application files were changed by consolidation. Resolve or explicitly
  disposition these before approving the production Django upgrade.

## CodeForge production deployment preflight (preparation only)

This section supersedes older “resume” paragraphs below that say VM access or
the production worker prerequisites are still unverified. No production
configuration, service, database, credential, firewall, OCI, registry, or
Kubernetes state was changed for this preflight. No push or image publication
was performed.

### Repository and worker image readiness

The current official branch is
`feature/SCRUM-122-deploy-kubernetes-to-processing`, at `2a4bdd8`, four commits
ahead of its Bitbucket tracking ref. The four local commits are:

| Commit | Purpose |
|---|---|
| `ee4c054` | Development baseline including merged SCRUM-130. |
| `b62bcec` | Consolidates the five expected SCRUM-122 files. |
| `8194d0a` | Records the verified VM baseline and cutover plan. |
| `2a4bdd8` | Corrects the OCI and VM evidence wording. |

The five consolidated files are:

1. `.github/workflows/processing-arm64.yml`
2. `services/document-processing/oke-worker.yaml`
3. `scripts/scrum122-oke-connect.sh`
4. `scripts/scrum122-cloudshell-preflight.py` (retired legacy entry point)
5. `docs/deployment/scrum-122-oke-worker.md`

The workflow uses manual `workflow_dispatch`, a native ARM64 GitHub runner,
and builds `services/document-processing` for `linux/arm64`. Its destination is
`phx.ocir.io/axcyydnoof5f/studyforge/document-processing`. The tag includes
GitHub SHA, run ID and attempt, and the build digest is recorded. Unique tags
are not registry-enforced immutability: the Deployment must use the recorded
`image@sha256:<digest>`, never a tag. The workflow currently verifies the
pulled tag's platform but does not compare the pulled repository digest with
the Buildx output digest; compare both explicitly during the approved publish
stage. `provenance: false` means this workflow does not produce BuildKit
provenance attestations. The prior OCI inventory found no processing image
repository. The existing pull Secret is not proof that this repository can be
pulled.

The intended source candidate is the current official branch tip, `2a4bdd8`,
because it contains the SCRUM-127 worker source and the reviewed manifest. The
workflow runs in the GitHub mirror and checks out its dispatch ref. The
available `github/chore/scrum-122-arm64-pipeline` ref is `27fc947`; compared
with the candidate it lacks the SCRUM-127 direct-storage worker changes across
13 processing-service paths. Do not dispatch from that old ref. After separate
Bitbucket push and mirror approvals, publish only when the mirror ref resolves
to the approved source SHA. If the worker logging hardening below changes
service code, publish from the resulting reviewed SHA instead of `2a4bdd8`.

Local checks completed for the current files: actionlint, ShellCheck, Bash and
Python syntax, YAML syntax parsing, and a scan for common embedded private keys,
access tokens and credential-bearing Redis/PostgreSQL URLs. Kubeconform parsed
the manifest but could not download Kubernetes v1.35.2 schemas because this
environment cannot resolve its schema host. Earlier validation of this draft
is recorded above; a fresh strict schema result remains pending. No dependency
was installed to bypass the network restriction.

### Django release candidate and worker contract

SCRUM-127 first entered the integrated development tree at `71be6f5`
(`0615867`, `981c842`, and `3304583` are its storage/source implementation
commits). The current API candidate is `2a4bdd8`, whose backend tree contains
that work. The current VM runs `6c3922fac11f063b1cda14e2d685757c6c262345`.
A hash-only Git tree comparison (file names, modes and object hashes; no source
or secrets exported) found 104 changed tracked backend paths. In addition to
SCRUM-127 documents/storage/auth changes, the candidate includes SCRUM-130
LLM fallback changes, SCRUM-101 removal of the in-process processing app,
conversation/message changes, knowledge retrieval and citation changes, note
options/source changes, quiz/survival-session changes, and shared settings and
dependency updates. This is a broad application upgrade. Stage and regression
review the complete release; do not treat it as a storage-only configuration
change.

The candidate integration contract is:

| Contract | Candidate behavior | Current production state |
|---|---|---|
| Job object locator | `GET /internal/v1/jobs/<job_id>/object/`; requires `Authorization: Bearer <PROCESSING_SERVICE_TOKEN>` and S3 mode. Returns document ID, source SHA-256, object key and MIME type. | Route returned 404. |
| Source retrieval | Worker in `PROCESSING_SOURCE_MODE=s3` calls the locator, then S3 `GetObject`, bounds input to 20 MiB and verifies document ID, MIME and SHA-256. | Django uses filesystem storage; no bucket or worker identity was configured. |
| Callback | `POST /internal/v1/jobs/<job_id>/result/`; same bearer token, JSON schema validation and idempotent `applied`/`duplicate` outcomes. RUNNING and terminal callbacks update Django job/document state. | GET returned 405, confirming the POST-only route shape; its auth and POST behavior were not exercised because that would mutate state. No service token was loaded. |
| Task publication | Django sends `processing_service.tasks.process_document_task(job_id, document_id, source_sha256)` to `document-processing`. | The current Django code already publishes this queue; active VM Celery consumes only `celery`. OKE must consume the exact `document-processing` queue. |
| Worker service state | Standalone `processing_service.settings`, `studyforge_processing` DB, `Execution` table and callback-delivery state. Worker probes DB, authenticated Redis and bucket access before subscribing. | Processing database/role and both processing migrations are absent. |

Required Django release configuration includes `DJANGO_DEBUG=0`,
`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_PASSWORD`,
`POSTGRES_SSLMODE=verify-full`, `POSTGRES_SSLROOTCERT`, authenticated TLS
`CELERY_BROKER_URL=rediss://...` with `ssl_cert_reqs=required`,
`PROCESSING_SERVICE_TOKEN`, `DOCUMENT_STORAGE_BACKEND=s3`, bucket/region,
storage endpoint/addressing/CA and approved credentials, and
`STUDYFORGE_REQUIRE_SECURE_CONNECTIONS=1`. Keep these values in approved secret
stores. The API and worker share only the service token; storage identities
are separate. Do not place values in Git, process arguments, transcripts or
worker logs.

SCRUM-130 makes `AI_FALLBACK_ENABLED` default to true and requires an
`OPENAI_API_KEY` when enabled. OpenAI fallback can send feature input to that
provider and has cost/privacy implications. For this release set
`AI_FALLBACK_ENABLED=0` unless the application owner separately approves the
provider, data handling and key. Gemini remains the worker embedding provider.

The live application migration table confirms these candidate migrations are
pending on `studyforge`: `conversations.0002_conversation_message`,
`conversations.0003_message_tool_trace`, `notes.0003_note_options_and_sources`,
and `quizzes.0004_survival_sessions`. Existing `documents.0001` through
`documents.0003` are applied. The notes migration copies source links before
changing the relation; inspect row counts and rehearse on a protected database
copy. Django application migrations belong to the Django release owner and
the `studyforge` database. Do not apply them as part of worker provisioning.

On the approved release and a protected copy, the plan/execute commands are:

~~~sh
cd /home/ubuntu/studyforge/backend
.venv/bin/python manage.py migrate --plan
# Only after a separate API-migration approval and protected backup:
.venv/bin/python manage.py migrate --noinput
~~~

The final live plan must contain only the four pending migrations listed
above. Stop if it differs or the notes data migration has not been reviewed
against live row counts. The second command is a gated mutation and was not
run.

The worker database is separate. It does not exist and has no migration rows.
Its migrations are `executions.0001_initial` and
`executions.0002_callback_delivery`, owned by the document-processing service
release. The checked-in `provision_database.py` creates a database and one
login role that also owns it. That role is used by the worker settings. This is
not a strict runtime/migration role split. Before production provisioning,
either approve that database-scoped ownership risk explicitly or extend the
provisioning plan to use a non-login owner/migrator and a runtime login with
only CONNECT, schema USAGE, table SELECT/INSERT/UPDATE, and sequence USAGE/
SELECT. The runtime task store does not require DELETE. Do not reuse the
existing Django superuser as the worker identity.

The intended worker DB sequence is:

~~~sh
cd /home/ubuntu/studyforge/services/document-processing
# One-shot provisioning only after its role model and secure admin input are approved.
python provision_database.py
python manage.py migrate --plan
# Only after a dedicated DB recovery point and separate approval:
python manage.py migrate --noinput
~~~

The current provisioning helper takes administrator credentials through its
environment, refuses to take over unmarked databases/roles, creates the
processing database/role, and does not migrate it. It does not implement the
owner/migrator/runtime split described above. Adapt and review that helper
before use if that split is selected. Never place its administrator password
on a command line or in a saved env file. The migration plan must be exactly
`executions.0001_initial` and `executions.0002_callback_delivery`; stop on any
other migration or existing unmarked name. Neither command was run.

#### Required worker logging hardening

The pinned worker Celery version is 5.6.3. The task decorator currently sets
`ignore_result=False`, and `process_document_task` returns the terminal
callback payload containing extracted text and embeddings. Celery's default
`resultrepr_maxsize` is 1024 characters and the worker emits task results in
logs/events. A successful task can therefore place document text in pod logs.
This is a pre-publication and pre-acceptance blocker. Before any real document
job, change the task to return a metadata-only receipt (job ID, terminal
status, delivery status), keep the payload in its existing durable callback
store only as long as required for retries, and set task result storage off
where compatible. Add a test that verifies a unique synthetic content marker
never appears in worker logs or task events. Verify the pinned Celery version's
behavior in the local image. [Celery task result representation](https://docs.celeryq.dev/en/v5.6.3/reference/celery.app.task.html)

The execution table also stores the full callback payload for redelivery, and
the current code does not clear that payload after delivery. It contains
document text and embeddings. Before production acceptance, the data owner
must approve its access, backup and retention policy, or the implementation
must retain only a safe receipt/fingerprint after confirmed delivery. Do not
delete existing execution rows or payloads as a rollback operation.

### OCI profile recovery and network evidence

The primary `studyforge-scrum122` profile now has the supplied authorized user
OCID; its tenancy and Phoenix region matched. Its existing security-token
session is expired and OCI reports that it can no longer be refreshed. The
owner must complete browser authentication to renew the session using the
existing public/private key pair. Do not create a user, API key or IAM policy,
or switch authentication modes. After session renewal, the principal needs
read-only access to the cluster, VNICs, subnets, route tables, security lists
and NSGs. [OCI configuration fields](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm),
[OCI authentication methods](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm)

The previous OCI inventory recorded the VM VNIC at `10.0.0.234` on subnet
`10.0.0.0/24`, no VM NSG, OKE pod subnet `10.0.1.0/24`,
`OCI_VCN_IP_NATIVE`, frontend pod `10.0.1.32`, and worker node
`10.0.1.63`. The VCN is `10.0.0.0/16`; earlier route-table inspection showed
no VNIC route-table override. The OKE pod NSG is
`studyforge-oke-pods-nsg`; the API VNIC and source NSG OCIDs are recorded in
the earlier Revised network proposal. These are prior observations, not a
current OCI inventory: refresh them before approval. OCI rules on a VNIC are
the union of the subnet security lists and every attached NSG; any permissive
rule can allow traffic. [OCI OKE pod network requirements](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfig.htm),
[NSG rule management](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/manage-nsg-security-rules.htm)

Before a network approval, refresh and record:

1. VM VNIC private/public IPv4 and any IPv6 addresses, subnet, every NSG
   membership, subnet security lists and effective ingress rules.
2. OKE cluster CNI, worker-node and pod subnets, pod and node VNIC/NSG
   membership, route tables, security lists, and effective egress.
3. Whether the source is a VCN-native pod IP or a node/NAT IP. Confirm with a
   controlled OKE probe and server-side connection metadata; do not guess the
   PostgreSQL/HBA or Docker firewall source.
4. VCN routes between `10.0.1.0/24` and `10.0.0.0/24`; public subnet IGW
   routing; NAT/service gateway routes; any IPv6 route or prefix.
5. Host IPv4 and IPv6 addresses, `iptables`/nftables INPUT and FORWARD,
   Docker DNAT and `DOCKER-USER`, and listening sockets after the proposed
   Compose binds.
6. After the host is TLS/auth ready, allow only stateful TCP 5432 and 6380
   from the verified OKE pod NSG to the VM VNIC through a new dedicated NSG.
   Preserve all existing VNIC memberships. Add no public CIDR rule and no
   IPv6 database/broker rule. The exact port 6380 is contingent on the Redis
   TLS listener being approved and validated.

Do not infer public reachability from `0.0.0.0` listeners alone. Prior OCI
inventory found public-subnet ingress on 22/80/443 only and no 5432/6379
rule, but the current profile cannot refresh the union of VM rules or IPv6
state. Docker DNAT sends published container ports through FORWARD, so an
INPUT-only host reject does not prove they are blocked. Use the fresh OCI
rules, IPv4/IPv6 routes, host forwarding policy and a controlled external
reachability check to decide actual exposure. Keep the ports unpublished on
public interfaces regardless.

### Redacted proposed configuration

These are templates only. Replace the bracketed values only after the
endpoint, source address, certificate name, CA and secret store are approved.

Compose host publication, preserving the current host-local Django path while
limiting the remote service to the VM private IPv4 interface:

~~~yaml
services:
  db:
    ports:
      - "127.0.0.1:5432:5432"
      - "10.0.0.234:5432:5432"
  redis:
    ports:
      - "127.0.0.1:6379:6379" # temporary legacy host-only path
      - "10.0.0.234:6380:6380" # only after Redis TLS config listens on 6380
~~~

The Redis container would listen on 6379 for the host-local transition and
6380 for authenticated TLS. Remove its 6379 publication and disable its
plaintext listener only after all verified producers and consumers use TLS.
Do not add a wildcard bind. Current host apps connect to 127.0.0.1; verify
every other consumer before changing mappings.

Illustrative IPv4 Docker forwarding policy (not executable until the exact
pod source, host interface, Docker chain behavior, order and persistence are
verified):

~~~sh
iptables -I DOCKER-USER 1 -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
iptables -I DOCKER-USER 2 -i enp0s6 -s <verified-pod-cidr> -p tcp \
  -m conntrack --ctorigdst 10.0.0.234 --ctorigdstport 5432 -j ACCEPT
iptables -I DOCKER-USER 3 -i enp0s6 -p tcp \
  -m conntrack --ctorigdst 10.0.0.234 --ctorigdstport 5432 -j DROP
iptables -I DOCKER-USER 4 -i enp0s6 -s <verified-pod-cidr> -p tcp \
  -m conntrack --ctorigdst 10.0.0.234 --ctorigdstport 6380 -j ACCEPT
iptables -I DOCKER-USER 5 -i enp0s6 -p tcp \
  -m conntrack --ctorigdst 10.0.0.234 --ctorigdstport 6380 -j DROP
~~~

Keep host-loopback and Docker bridge traffic working; test rule order and
return packets in a protected clone. Persist only with an approved Docker-aware
mechanism. Verify IPv6 has no bound listener or permitting NSG/security-list
path; do not assume an IPv4 rule covers IPv6.

Redis server configuration template for a server-certificate TLS listener
with Redis ACL authentication (use `tls-auth-clients no` only if the approved
design is TLS server authentication plus ACL credentials; if mutual TLS is
required, add client-certificate mounts and corresponding worker/Django client
settings instead):

~~~conf
port 6379
tls-port 6380
tls-cert-file /run/redis/tls/server.crt
tls-key-file /run/redis/tls/server.key
tls-auth-clients no
aclfile /run/redis/acl/users.acl
protected-mode yes
# Preserve the currently observed RDB save policy during the TLS change.
# Do not change appendonly/maxmemory policy in the same unreviewed edit.
~~~

Both application broker URLs must use the approved ACL identity on DB 0 and
the trusted Redis name/IP, for example
`rediss://<named-user>:<url-encoded-secret>@10.0.0.234:6380/0?ssl_cert_reqs=required&ssl_ca_certs=/etc/studyforge/trust/redis-ca.pem`.
The exact Redis ACL command, key-pattern and Pub/Sub-channel grants are not
known. Derive and test them with the pinned Celery/Kombu/redis-py versions in
isolated Redis before production; do not use `+@all`, `~*`, or guessed
permissions. Preserve the existing queue names and Celery key namespace so
messages are not stranded. [Docker original-destination filtering](https://docs.docker.com/engine/network/firewall-iptables/),
[PostgreSQL TLS](https://www.postgresql.org/docs/16/ssl-tcp.html),
[Redis TLS](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/)

PostgreSQL server TLS configuration and HBA order template:

~~~conf
ssl = on
ssl_min_protocol_version = 'TLSv1.2'
ssl_cert_file = '/run/postgresql/tls/server.crt'
ssl_key_file = '/run/postgresql/tls/server.key'

# Insert before the existing broad host SCRAM rule. Use the source actually
# observed from OKE and preserve separately verified Django host entries.
hostssl    studyforge_processing studyforge_processing <verified-OKE-source-CIDR> scram-sha-256
hostnossl  all                  all                  <verified-OKE-source-CIDR> reject
host       all                  all                  <verified-OKE-source-CIDR> reject
~~~

The server certificate must include the actual verified-full client hostname
or IP SANs for Django and OKE. If both connect by IP, include 127.0.0.1 and
10.0.0.234, or choose an approved private DNS name and route both clients to
it. Mount the server private key read-only with owner/mode readable by the
container's PostgreSQL process only; verify numeric UID, effective file mode
and restart behavior. Keep existing application DB access until TLS has been
validated from Django and OKE. Do not alter the existing `studyforge` role.

For OCI Object Storage S3 compatibility, a candidate endpoint format is
`https://<namespace>.compat.objectstorage.us-phoenix-1.oci.customer-oci.com`
with path-style addressing, region `us-phoenix-1`, and a private bucket. Confirm
namespace, supported endpoint and region against the tenancy before use. The
worker's boto3 code uses AWS-style access-key/secret-key credentials and the
manifest disables EC2 metadata. It has no OCI-native resource-principal
adapter. An OCI S3-compatible deployment therefore needs an approved Customer
Secret Key identity or a separately reviewed workload-identity code change.
Do not create that identity/key during this preparation. OCI policy templates
should separate worker bucket inspection/GetObject from Django write/read/delete
on the approved document prefix; add required bucket inspection for the
worker's `HeadBucket` readiness probe. Scope policies to the selected bucket
and `documents/` objects where supported. [OCI S3 compatibility](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm),
[Customer Secret Keys](https://docs.oracle.com/en-us/iaas/Content/Identity/access/working-with-customer-secret-keys.htm),
[OCI Object Storage least privilege](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm)

For an OCI Object Storage provider, these are policy-review templates only:

~~~text
Allow group <worker-read-group> to inspect buckets in compartment <compartment> where target.bucket.name='<bucket>'
Allow group <worker-read-group> to read objects in compartment <compartment> where target.bucket.name='<bucket>'
Allow group <django-storage-group> to inspect buckets in compartment <compartment> where target.bucket.name='<bucket>'
Allow group <django-storage-group> to manage objects in compartment <compartment> where all {target.bucket.name='<bucket>', target.object.name='documents/*', any {request.permission='OBJECT_CREATE', request.permission='OBJECT_READ', request.permission='OBJECT_DELETE', request.permission='OBJECT_INSPECT'}}
~~~

Have the OCI IAM owner validate the exact permissions required by the S3
compatibility API and Django's upload/read/delete calls; do not grant bucket
management to either application identity. The worker identity must not receive
object create, overwrite or delete permission. No group, user or key is created
by this preflight.

The worker runtime configuration in `oke-worker.yaml` expects:

| ConfigMap/runtime value | Secret/trust value |
|---|---|
| `PROCESSING_DB_HOST`, `PROCESSING_DB_PORT`, `PROCESSING_DB_NAME`, `PROCESSING_DB_USER`; `PROCESSING_DB_SSLMODE=verify-full`, `PROCESSING_DB_SSLROOTCERT` | `PROCESSING_DB_PASSWORD`; trusted `postgres-ca.pem` |
| `PROCESSING_SOURCE_MODE=s3`, `PROCESSING_STORAGE_BUCKET`, `PROCESSING_STORAGE_REGION`, optional HTTPS endpoint/addressing/CA | Optional storage access/secret pair and session token; worker identity limited to bucket inspection and object reads |
| `PROCESSING_DJANGO_API_URL=https://studyforge-rodians.duckdns.org`, `PROCESSING_REQUIRE_DIRECT_STORAGE=1`, `STUDYFORGE_REQUIRE_SECURE_CONNECTIONS=1`, `AWS_EC2_METADATA_DISABLED=true` | Matching `PROCESSING_SERVICE_TOKEN`; `PROCESSING_SECRET_KEY`; `GEMINI_API_KEY`; authenticated `PROCESSING_REDIS_URL` with `rediss://` and `ssl_cert_reqs=required` |
| `DJANGO_SETTINGS_MODULE=processing_service.settings`, queue `document-processing`, visibility timeout 3600, Gemini embedding model/dimension/batch | Optional Redis and S3 public CA files only; never place private keys in a ConfigMap |

Use the approved Kubernetes Secret integration. Do not use `kubectl
create secret --from-literal` or print Secret YAML. The existing
`studyforge-processing-secrets` object must be provisioned from the approved
secret store after a separate approval. Keep `ocir-pull-secret` unchanged.
Before storing worker credentials, the OKE owner must confirm namespace RBAC,
who can read Secrets, and the cluster's at-rest encryption/key-management
configuration; these were not verified in the previous inventory.

### Staged production plan and approval gates

Every stage below remains unapproved and unexecuted. Stage owners are role
assignments; Aashish's explicit SSH/sudo authorization did not authorize these
changes. Expected impact and rollback are conditional on rehearsal in staging.

| Stage / owner | Scope and proposal | Backup, validation, stop conditions and rollback | Approval |
|---|---|---|---|
| 0. Revalidate and stage / OCI read-only operator, VM operator, release owners | Owner completes browser renewal of the existing security-token session. Then refresh VNIC/NSG/route/IPv6 inventory, Compose consumers, backup status, current Django baseline, queue consumers and job/document counts. Agree on provider, bucket, CA/SANs, secrets path, change window and owners. | No outage. Stop if authentication fails, effective OCI exposure is unknown, backup/restore cannot be proven, or owner/secret sources are missing. No rollback required. | Read-only OCI auth is required; no mutation approval. |
| 1. Restrict Compose env file / VM security owner | Change only `/home/ubuntu/studyforge/.env` from observed mode 0664 to owner-only 0600, preserving ubuntu ownership, after confirming Compose is operated as ubuntu. If another service identity needs access, choose a dedicated restricted group and 0640 instead. Do not edit values or rotate credentials here. | No service restart expected because running containers already have their environment. Record current owner/mode; verify ubuntu can read it and run quiet Compose config validation without printing output. Stop if the runtime/deploy user is unclear. Roll back only to a non-world-readable mode and the documented owner/group; never restore 0664 as a general rollback. | Separate host/security approval for this file's mode only. |
| 2. Storage identity and CA preparation / OCI storage-IAM owner, security owner | Select/create a private encrypted bucket, region and S3 endpoint; provision separate Django write and worker inspect/read identities; approve CA and SANs for PostgreSQL/Redis; deliver public roots and private server keys through approved stores. The worker S3 identity must support HeadBucket and GetObject and must not write/delete. | No application outage. Validate in staging: TLS name/CA, bucket privacy, Django upload/read/delete permissions, worker HeadBucket/GetObject, denied worker write/delete, and SHA-256 equality. Stop on unknown bucket owner, broad IAM policy, untrusted cert, absent secure secret delivery or unsupported identity adapter. Roll back by revoking only newly issued access and retaining any test object until verified cleanup is separately approved. | Separate cloud/IAM, bucket, certificate and credential approvals. |
| 3. PostgreSQL endpoint and processing DB / VM DBA, Django DB owner | Back up current `studyforge`; add PostgreSQL TLS without changing existing application data. Restrict Docker publication to loopback plus VM private IPv4, not public wildcard. Add ordered OKE-source `hostssl` SCRAM rule and plaintext/other-DB rejects after verifying packet source. Provision `studyforge_processing` and separate runtime/migration roles; apply only `executions.0001_initial` and `0002_callback_delivery` to that DB. | A PostgreSQL restart is expected and may briefly interrupt Django sign-in/uploads. Backup the app DB and current Compose/HBA/cert files first; the new processing DB has no data yet. Validate Django and worker `SELECT 1` with verify-full, `pg_stat_ssl`, allowed/denied HBA paths, database isolation and exact schema. Stop on SAN mismatch, unexpected client source, role mismatch, failed restore/backup or unexpected migration plan. Rollback closes OKE ingress first, restores prior PostgreSQL TLS/HBA/Compose configuration while retaining both DB volumes; never drop either DB or restore over newer application data. | Separate VM/DB change and migration approvals; maintenance window. |
| 4. Redis TLS, ACL and durability / VM Redis owner, Celery owner | Add private TLS listener 6380 with approved server trust, named producer/legacy-consumer/OKE-worker ACL users, and URL `rediss://` on database 0. Preserve queue names and key namespace. Keep legacy port 6379 loopback-only only during a tightly scoped transition; remove it after every verified client uses TLS. Do not stop the current `celery` consumer until its non-document responsibilities are mapped. | Redis restart can interrupt uploads and pending tasks. First quiesce producers/workers in the approved window; take and verify a fresh protected RDB/volume backup (`rdb_changes_since_last_save=0`, successful BGSAVE) because AOF is off and current data had 38 unsaved changes. Reconcile queue/unacked counts. Validate auth/TLS hostname/CA, anonymous and plaintext rejection at the final listener, publish/receive/retry/ack in staging, and legacy consumer compatibility. Stop on unknown consumers, failed backup, ACL denials or queue drift. Roll back listener/client configuration together while preserving the volume and queue contents; never FLUSH, delete, or blindly replay messages. Review AOF separately for disk/latency impact; do not enable it implicitly in this change. | Separate Redis, ACL and persistence approval; maintenance window. |
| 5. Django application release / Django release owner, DBA, storage owner | Deploy the approved API candidate with S3, secure PostgreSQL/Redis, service token, readiness, locator and callback. Apply pending Django migrations on `studyforge` only after plan/backup approval. Keep `AI_FALLBACK_ENABLED=0` unless OpenAI use is approved. Preserve the VM Celery consumer for other queues; it currently consumes `celery`, not `document-processing`. | Brief API restart/maintenance may interrupt uploads/auth. Take a consistent protected database backup and rehearse candidate and migrations on a production-like copy. At the live window pause new uploads, re-count documents/media, verify exact migration plan, run checks, apply approved migrations, start API, then verify health/readiness, existing auth and upload/read/delete, S3, TLS broker and authenticated locator/callback on a controlled fixture. Stop on any unexpected migration, missing storage objects, upload failure, DB/Redis TLS failure or callback auth failure. Roll back API code/config only if backward-compatible with already-applied schema and S3 writes; preserve migration state and both storage copies. Never reverse data migrations automatically; reconcile writes before routing back. | Separate API release, application DB migration, storage cutover and downtime approval. |
| 6. Private network path / OCI network owner, VM security owner | After PostgreSQL/Redis TLS/auth and host DOCKER-USER controls pass, attach a new dedicated API-VNIC NSG permitting only stateful TCP 5432 and 6380 from the refreshed OKE pod NSG. Preserve all current VNIC NSGs and public web rules. Host forwarding separately permits only verified pod sources. | No planned app interruption; new path only. Validate exact effective rule union, private route, OKE source, successful TLS/auth from OKE and denied public/other-source access for IPv4 and IPv6. Stop if any wildcard/pubic exposure, unexpected VNIC membership, source translation or unverified TLS. Roll back by detaching only the new NSG using a fresh membership snapshot and removing only its rules; retain all existing groups. | Separate OCI network and host-firewall approval. |
| 7. Publish and prepare OKE / repo maintainer, GitHub/OCIR owner, OKE namespace owner | After worker logging fix and successful local validation, approve Bitbucket push and mirror exact candidate SHA. Create the private OCIR repository only if a fresh inventory confirms it is absent. Dispatch workflow manually on the exact mirror SHA; compare Buildx digest with registry-pulled digest and verify `linux/arm64`. Create approved ConfigMaps, trust, Secret, ServiceAccount and one worker Deployment pinned by digest. | No Django/VM interruption expected from a worker probe. Verify pull secret type/host, no name collisions, exact source SHA/image digest, ARM64 placement, startup/readiness checks for DB/Redis/bucket, and no public Service/Ingress. Stop on a mismatched SHA/digest, pull failure, secret/trust error, non-ARM node or dependency not ready. Rollback removes only this rollout's worker/probe/config resources; leave frontend and data unchanged. Do not delete registry artifacts as rollback. | Separate Git push, OCIR repository/publication and Kubernetes mutation approvals. Secret provisioning is a separate approval. |
| 8. End-to-end acceptance / product owner, Django owner, worker owner | With one user-approved non-sensitive document, submit through StudyForge and let one ARM64 OKE worker consume the exact task. | Validate every criterion in the acceptance section below; stop on any mismatch, duplicate/unknown job, content in logs, unhealthy existing service, or unexpected public path. Rollback stops only the new worker and removes only its newly created configuration; retain the document/job/results for investigation. | Explicit approval for one real production document and any task-event observation. |

### End-to-end acceptance evidence

Do not use a document until its owner approves it as non-sensitive. Keep the
test's application-visible effects and retention period approved. Do not log
document text, object key, bearer token, Redis URL, DB password or S3 key.

1. Record document ID, job ID and source SHA-256 from the authorized
   application/DB view. Do not expose the object key. Confirm the locator
   response has matching document ID/hash/MIME and an internal key, then verify
   the worker's read-only S3 identity can fetch and hash the same bytes.
2. Record Django's task name, `document-processing` queue and task arguments
   (job ID, document ID, SHA-256). Enable a short-lived, access-controlled
   Celery event observer only if approved. Correlate Celery task UUID to the
   received message and worker pod UID/name. Do not persist event payloads
   beyond the approved evidence window.
3. Capture the worker pod UID, Ready ARM64 node, image ID/digest, start/end
   timestamps and task UUID. Confirm worker readiness before queue consumption.
4. Confirm the processing `Execution` row matches job ID, document ID and
   SHA-256, reaches SUCCEEDED, and callback delivery reaches DELIVERED. Confirm
   Django's job is SUCCEEDED and document is READY with expected page count and
   persisted chunks. Keep IDs/hash in the restricted change record only.
5. Confirm the application exposes the successful document result to its owner,
   existing frontend and Django health/readiness remain healthy, the legacy
   Celery queue remains healthy, and no unrelated task was consumed.
6. Confirm public IPv4/IPv6 ports 5432, 6379 and 6380 remain unreachable and
   only the verified OKE source can establish authenticated TLS. Preserve
   sanitized command outputs, DB status metadata, pod/image metadata and
   callback outcome; exclude payloads and credentials.

The application does not persist a Celery task UUID in `Job` or `Execution`.
For one-time correlation, collect the task-received event/worker UUID together
with its three identity arguments and pod UID. The logging hardening above is a
precondition so task results/events contain only a metadata receipt.

### External owners, unresolved assumptions and go/no-go

Required external inputs are: browser renewal of the existing OCI session and
read-only access; fresh OCI route/NSG/VNIC and IPv6 inventory; named VM DBA and Redis/Celery
owners; approved database/Redis certificate names and CA; approved secret
store; storage provider, compartment, namespace, bucket and least-privilege
identities; review of production migration plans; GitHub mirror synchronization
and OCIR repository/push approval; product owner for the test document; and an
approved maintenance window. No storage bucket, worker credential, private CA,
new OCIR repository or workload secret has been verified as available.

**Current recommendation: NO-GO for publish, Django release, migration, network
opening or worker deployment.** Preparation may advance once the expired OCI
session is renewed and other owners supply required inputs. The hard stop conditions
are unresolved TLS/auth for PostgreSQL and Redis, missing processing DB and
migrations, missing storage and service credentials, absent S3 locator in the
live API, outstanding full-backend release regression, unverified OCI effective
exposure, and a stale GitHub mirror. The
smallest safe first production mutation is the separately approved mode-only
change in Stage 1; it does not deploy SCRUM-122. The first SCRUM-122 service
change must wait for fresh backups and the full Stage 3/4 maintenance approvals.

## OCI access recovery and local security hardening (updated 2026-11-18)

This section supersedes the 2026-11-17 note that the authorized user OCID was
missing. Aashish supplied the user, tenancy and root-compartment identifiers;
the tenancy equals the root compartment. The existing primary profile's
tenancy and `us-phoenix-1` region matched. Before editing, a mode-0600 backup
was made at `~/.oci/config.scrum122.pre-repair.20261118T060830Z`. Only the
`user` field in profile `studyforge-scrum122` was added. Its authentication
mode, signing key, fingerprint, and token-file path were preserved; the
secondary `studyforge-scrum122-local` profile was not edited. Local verification
confirmed the configured public key matches the private key and fingerprint;
key and token contents were not printed.

`oci session validate --profile studyforge-scrum122 --auth security_token
--local` reports `Session has expired`. A read-only `oci iam user get` attempt
was refused by the CLI because the session expired. The authorized
`oci session refresh --profile studyforge-scrum122 --auth security_token`
returned: “Your session is no longer valid and cannot be refreshed. Please use
`oci session authenticate` to create a new session.” Authentication and remote
identity validation therefore remain incomplete; this is an expired session,
not an observed IAM permission denial.

On November 18, the session was renewed by Oracle browser sign-in
using the existing key pair. The installed CLI 3.96.2 uses the supplied
public-key flag only in its non-browser path. Its standard browser path
generates a key and rewrites the profile, so the browser helper was invoked
with the existing key in memory and a loopback-only callback. The configured
public key and fingerprint matched before login. After login, the session
principal and tenancy matched the profile and signed read-only `GetUser`
and `GetTenancy` succeeded. Only the expired token was replaced. The existing
key files and profile configuration were preserved. The CLI reported a valid
session through November 18, 2026 at 11:31:47 a.m. Central.

### OCI inventory and exposure status

**Refreshed read-only on 2026-11-18 in `us-phoenix-1`.** The VM, cluster,
node pool, VCN, and OCIR repository are in the root compartment
`dhitalaashish20`. The authorized principal's accessible compartment listing
returned no active child compartments.

| Resource | Verified OCI state |
|---|---|
| API VM and VNIC | `studyforge-api` RUNNING. One VNIC on `10.0.0.0/24`, private IPv4 `10.0.0.234`, public IPv4 `132.226.88.147`, no secondary IPv4, IPv6 address, or attached NSG. |
| API routes and security list | The default public route points to an enabled Internet Gateway. The VNIC uses its subnet route table, with no private-IP route override. The subnet's sole security list allows public IPv4 TCP 22, 80 and 443, plus ICMP, with stateful unrestricted IPv4 egress. It has no TCP ingress to 5432, 6379 or 6380 from any source. |
| OKE | `studyforge-oke` ACTIVE, Kubernetes `v1.35.2`, private API `10.0.1.9:6443`. `studyforge-arm-workers` ACTIVE with one A1 Flex node at `10.0.1.63` and an Oracle Linux aarch64 image. Kubernetes readiness was not re-probed. |
| Worker and pod networking | Both use private subnet `10.0.1.0/24`, OCI VCN-native pod networking and no public or IPv6 addresses. The primary VNIC uses `studyforge-oke-workers-nsg`. The secondary pod VNIC at `10.0.1.172` uses `studyforge-oke-pods-nsg` and has the previously observed frontend pod address `10.0.1.32` allocated. Endpoint, worker and pod NSG membership and rules were read. This verifies the expected pod NSG source; actual packets from a future worker remain unobserved. |
| Pod effective egress and routes | The private subnet security list permits stateful unrestricted IPv4 egress, so the pod NSG does not need an extra egress rule to reach the future VM listener. The private subnet uses NAT for default IPv4 egress and a service gateway for Oracle services. No VNIC or private-IP route override or VCN/subnet IPv6 prefix was found. |
| Registry and storage | The only OCIR repository in the verified scope is private `studyforge/frontend` with one image. `studyforge/document-processing` is absent. Object Storage namespace `axcyydnoof5f` returned zero buckets, and Vault returned zero secret metadata entries in the accessible scope. This does not establish the absence of an external approved store. |

Exposure is separated into the following evidence:

| Layer | Existing evidence | Conclusion |
|---|---|---|
| Service binding | PostgreSQL listened on `0.0.0.0:5432` and IPv6 wildcard; Redis listened on `0.0.0.0:6379` and IPv6 wildcard. | Both were wildcard-bound. |
| Docker publication | Compose published host ports 5432 and 6379 on IPv4 and IPv6 wildcards. | Both were externally addressable at the Docker host-port layer. |
| Host firewall | IPv4 INPUT allowed 22/80/443 and rejected other inbound traffic; Docker DNAT traversed FORWARD. `DOCKER-USER` was empty and Docker accepted the container destinations. | INPUT policy alone does not block these forwarded ports; effective host forwarding protection was not present in the captured rules. IPv6 forwarding policy was not confirmed. |
| OCI network permission | The current API VNIC has no attached NSGs. Its only subnet security list contains no TCP ingress for 5432, 6379 or 6380. The API VNIC has public IPv4 and no assigned IPv6. | The verified direct OCI network path does not permit these ports from any source. No public rule removal is required by this snapshot. |
| External reachability | No controlled public IPv4/IPv6 connection test was performed. Host firewall and Docker evidence is from the prior VM inspection. | The OCI policy denies direct ingress. Public reachability was not measured. Wildcard Docker publishes remain a host hardening concern. |

Keep the wildcard publication as a separate host-security finding. Recheck
the OCI rules and host forwarding immediately before any approved change.
If the rules later allow public database or broker traffic, propose removing
only that public ingress rule after recording its resource and dependencies, while
keeping SSH/HTTP/HTTPS and all existing NSG memberships intact. Do not execute
that change without a separate approval. Regardless, the target design must
bind PostgreSQL only to loopback and the VM private IPv4 address, and Redis
TLS only to the VM private IPv4 address; do not publish either service on a
wildcard or IPv6 address.

The verified OCI minimum is one new `studyforge-api-processing-ingress-nsg`
on the API VNIC, with two stateful TCP ingress rules from the existing
`studyforge-oke-pods-nsg` for PostgreSQL 5432 and proposed Redis TLS 6380.
The [revised network proposal](#revised-network-proposal) records the exact
VCN, target VNIC and source NSG IDs. Existing pod egress already permits the
path. Before opening it, validate TLS and credentials, restrict the service
publishes and Docker forwarding, and confirm the actual pod connection source
with an authorized probe. Rollback detaches and removes only the new NSG
after checking VNIC membership. Keep public and IPv6 ingress closed.

The smallest proposed VM change remains restricting
`/home/ubuntu/studyforge/.env` from observed 0664 to 0600 after confirming
that the Compose operator is `ubuntu` and that no authorized group needs
read access. Recheck current file metadata, validate quiet Compose config
access, and record the previous owner and mode. This requires separate
host/security approval. It is independent of the worker rollout.

No database/broker TLS, authentication, role, storage, OCI, firewall, route,
Kubernetes, or production service setting was changed.

### Worker telemetry hardening and validation

The task has no repository consumer of its Python return value; Django consumes
the authenticated HTTP callback. The task now returns only `job_id`,
`document_id`, `attempt`, and terminal `status`, and sets `ignore_result=True`.
The successful callback still carries the same chunks and embeddings through
the same authenticated/idempotent callback path, and the retry budget and
delivery state transitions remain unchanged. Generic document-processing
failures now retain a permanent task failure and FAILED callback while using a
constant message without the original exception or chained traceback. Gemini
provider failures and PDF/Office parser failures also suppress unsafe
exception details/chains. No second processing path was added. Existing
page-count logging records only aggregate counts, not text.

Focused regression coverage uses a unique synthetic document marker and
synthetic embedding value. It confirms callback content is unchanged while
Celery's returned representation contains neither marker nor vector, task
result storage is ignored, provider exception details are not returned or
chained, and generic task failures do not reveal the source exception. Full
worker validation ran with the built image and Docker engine reporting
`linux/arm64` / `aarch64`: the 70 service tests passed in the API container and
both ARM64 worker containers; all 23 execution-store and callback-delivery
tests passed; worker registration/queue checks, migrations/drift, isolation,
restart persistence and Redis-outage checks passed. The disposable Compose
containers, network and database volume were removed. This is local worker
runtime and test evidence, not a real production document job or end-to-end
OKE acceptance. `actionlint`, ShellCheck, Python compilation, YAML syntax and
`git diff --check` passed. Kubeconform could not retrieve Kubernetes schemas
because DNS/network access to `raw.githubusercontent.com` is unavailable; no
schema verdict is claimed.

The durable callback payload is still retained in `Execution.callback_payload`
after delivery. Before delivery, it is required to replay exactly the same
terminal callback after a worker retry/crash; the job-unique execution record
prevents duplicate processing, and staging keeps the first terminal payload.
The HTTP callback is idempotent. If Django accepts the callback but the worker
crashes before local `mark_delivered`, local state remains PENDING and a retry
resends the saved payload; Django answers `duplicate`, after which local state
can be marked DELIVERED. No other repository consumer was found for the stored
payload. The safe follow-up retention design is to keep the complete payload
until DELIVERED, then in one transaction replace it with a minimal receipt and
retain a SHA-256 fingerprint plus delivery status/timestamp. A repeated task
for a delivered execution must return that receipt without reprocessing or
resending. This needs execution-store changes, a fingerprint migration if
retained in a dedicated field, tests for the callback-success/local-crash
window, and execution-data-owner approval. It was not implemented; no
production or local database rows were changed.

### Test failures, publication, and Django release

Two previously reported failures are outside SCRUM-122 and were not changed:

1. `backend/apps/knowledge/tests/test_questions_api.py` uses undefined
   `RetryableProcessingError` in `test_failed_search_raises_without_a_trace`;
   the module already imports `RetryableQueryEmbeddingError`, the expected
   knowledge embedding exception. This is a test defect, owned by the
   Knowledge/RAG feature maintainer. Proposed change: use the imported
   `RetryableQueryEmbeddingError` at that line and run the focused Knowledge
   suite. No weakening of the assertion is needed.
2. `backend/tests/test_gemini.py::GeminiTests.test_factories_use_gemini_key_and_native_client`
   called the Gemini factory while SCRUM-130 fallback defaults to enabled but
   did not configure an OpenAI key. The code correctly requires that key when
   fallback is enabled. This was a test environment/configuration defect, not
   an application regression. The test now explicitly sets
   `AI_FALLBACK_ENABLED=false` for its Gemini-only factory assertion; separate
   enabled-fallback tests remain. The owner-approved local test correction is
   isolated in `backend/tests/test_gemini.py` for SCRUM-130 review.

The focused Gemini and SCRUM-130 fallback suite passed in an isolated Python
3.12/PostgreSQL test environment: 25 tests and 13 subtests passed. The
Knowledge/RAG undefined `RetryableProcessingError` remains unchanged for its
feature owner to review.

The manual ARM64 workflow remains the only publisher and retains its unique
SHA/run/attempt tag, protected GitHub secrets, explicit `linux/arm64` build,
and source-revision labels. It now compares the pulled OCIR repository digest
with Buildx's output digest, fails on mismatch, and records the immutable
`image@sha256:<digest>` reference in the run summary. The Kubernetes Deployment
continues to require a digest reference. `actionlint` passed. The workflow was
not dispatched, no credentials were used, and nothing was published. The
worker source candidate is this reviewed working tree based on branch HEAD
`2a4bdd8`, including the local telemetry hardening. Until a review commit is
approved and mirrored to GitHub at that exact SHA, there is no publishable
candidate SHA.

The currently integrated development ref is `origin/development` at
`ee4c054`; SCRUM-127 integration revision `71be6f5` is its ancestor. The API
tree comparison to the production checkout was previously recorded as 104
changed backend paths for the feature candidate, including SCRUM-127,
SCRUM-130, SCRUM-101 and other application work. The 2a4bdd8 branch is not a
production Django release recommendation. Select and review the backend
release separately from the worker image; require Django/backend owner
approval, migration plan and full backend regression on a protected copy. The
processing database's two migrations remain separately owned by the worker
service release.

### Current readiness after local preservation and OCI renewal

The ten changes are preserved in four local commits on the official feature
branch. The four earlier commits are still reachable.

| Local commit | Scope |
|---|---|
| `3d03a4fbecaed16c3e122f39afec8e25e0b65b57` | Worker logging and exception hardening plus tests |
| `98fcdca6008a080386064bfa273edcebdc298196` | Native ARM64 workflow digest verification |
| `add37bae4c877ac990a2f1dc1bf9dd4e69ea3c86` | Deployment preflight and readiness evidence |
| `edd6d4d220eb74364dd9c243875f7a4410f0f72c` | SCRUM-130 Gemini-only factory test isolation |

The refreshed OCI inventory resolves the prior effective-rule uncertainty.
Production remains **NO-GO**. The VM-side TLS and ACL setup, processing
database and migrations, private bucket and scoped identities, approved secret
and CA delivery, reviewed Django release and migration plan, protected
backups, and assigned owners and maintenance window still require approval
or verification. Git pushes, OCIR repository creation and publish, OKE
resources, and real document acceptance require separate approvals.
