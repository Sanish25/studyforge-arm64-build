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
| Django and Celery deployment | Gunicorn was active as `ubuntu` from `/home/ubuntu/studyforge/backend`. The clean disk checkout is `6c3922fac11f063b1cda14e2d685757c6c262345` on `deploy/SCRUM-125-backend-postgres-redis`. This checkout lacks SCRUM-127 settings and the S3 job locator. `studyforge-celery.service` is active with `-A config` and no explicit queue flag. Snapshot counts for `document-processing`, `celery`, and Kombu's `unacked` hash were zero. | Approve and stage a current Django API release. Confirm the legacy service's full responsibilities and drain/recheck work at cutover. Retire only the obsolete consumer after the new route is ready. A zero snapshot is not proof that a later cutover is idle. |
| HTTPS, callback and auth | Nginx serves `studyforge-rodians.duckdns.org` with a Let's Encrypt certificate matching that DNS name. HTTPS returned 200 for liveness and 404 for readiness and the job locator. The legacy callback route returned 405 for GET, consistent with its POST contract. The loaded Gunicorn env lacks `PROCESSING_SERVICE_TOKEN`. | Update the API to provide readiness and the job locator, then supply a matching token to Django and worker. Prove the authorized GET locator and POST callback through a controlled fixture or approved end-to-end job. |
| Source storage | Deployed settings use filesystem storage. No `DOCUMENT_STORAGE_*` settings or cloud workload identity were loaded. The default media directory was absent and a read-only query found zero document rows and no file references at the snapshot. | Select an approved private S3-compatible bucket, endpoint, region, and separate Django and worker identities. Recheck uploads and references when writes are paused. If documents appear, back up existing media and verify a SHA-256 copy before switching storage. |
| Certificates and credentials | The working HTTPS certificate covers Django only. PostgreSQL and Redis have no active TLS configuration or demonstrated CA for worker traffic. Gunicorn and legacy Celery use `/etc/studyforge.env` (root:ubuntu, 0640). It declares a Gemini key and existing Django DB settings. The dedicated processing env file is absent. The Compose `/home/ubuntu/studyforge/.env` is currently 0664 and declares the existing PostgreSQL password. | Approve endpoint names and CA trust, the credential store and delivery method, and Gemini reuse if its scope is suitable. Create separate worker DB, Redis, Django secret, shared service token, and scoped object-storage credentials or identity. Include restricted permissions for the Compose env file in the host change and evaluate any rotation separately. Verify Compose still reads its settings as the authorized user and record pre-change ownership/mode for rollback while keeping credential access restricted. |

The old OCI inventory showed no processing OCIR repository and no suitable
Vault entry. The local OCI security token is expired. Reauthenticate and
refresh inventory before proposing any storage or registry resource creation.
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
