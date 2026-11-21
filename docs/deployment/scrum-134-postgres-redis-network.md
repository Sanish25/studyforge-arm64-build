# SCRUM-134: PostgreSQL, Redis and private networking

Subtask of SCRUM-122 (OKE document-processing worker). Owner: Gaurav.

**Status, 2026-11-21:** code and local rehearsal kit merged; **no production
change has been made**, so the OKE worker (SCRUM-122 phase 3) is still blocked
on this subtask. ACL fixes from source review (below) are committed but not yet
rehearsed. Production follows the
[run-sheet](./scrum-134-production-runsheet.md) once its gates pass.

## Source review findings (2026-11-21, not yet rehearsed)

1. **kombu was unpinned.** `celery==5.6.3` only requires `kombu>=5.6.0`, so
   the worker image resolved kombu 5.7.0 (released 2026-11-03; the published
   image was built 2026-11-18), while the local probe venv had 5.6.2. The ACL
   already contained 5.7.0's `_kombu.binding_deadlines` key, so measurements
   mixed the two versions. `kombu==5.7.0` is now pinned in both requirements
   files, and `rehearse.sh` fails if the image or probe Python differs.
2. **Missing `RPOP`/`PEXPIRE`.** kombu 5.7.0 uses `RPOP` when it polls a
   queue and `PEXPIRE` when it writes or reads a queue with `x-expires`.
   Celery's pidbox reply queues have `x-expires`, so startup mingle and
   `inspect`/control replies need both commands whenever two workers share
   the broker. That never happened in the rehearsal (workers ran one at a
   time), but it is the production topology: the VM's legacy worker and the
   OKE worker. Both app users now have `+rpop +pexpire`, with key patterns
   unchanged. The rehearsal now runs the legacy consumer while the OKE worker
   is up and checks mingle and a control ping.
3. **Password reset would have broken.** With `DEBUG` off, the SCRUM-135
   `password_reset` cache is a Django `RedisCache` on the broker URL
   (`SET NX EX`, `EXISTS`, `INCRBY`, `DEL` on `studyforge_password_reset:*`).
   The Django user had neither the key pattern nor `INCRBY`, so every reset
   request would have failed after the cutover. These are now granted to
   `studyforge_django` only, and `broker_probe.py reset-cache` checks them.

## Open issue: intermittent Redis ACL denial (blocks production)

**What happened.** The full rehearsal (`rehearse.sh`) passed 46/46 with zero
Redis ACL denials, and every manual run before it also logged zero. A later
run, made to prove the harness catches regressions (the PostgreSQL HBA rule
was deliberately weakened; nothing on the Redis side was changed), correctly
reported the two expected PostgreSQL failures and one unexpected one:

```
FAIL  no Redis ACL denials during Celery traffic (got: 1)
```

So some Celery/kombu operation sometimes needs a command, key or channel that
`redis-users.acl.template` does not grant. That run printed only the count, so
the denied command and key are not known yet.

**Likely cause (still unconfirmed).** The earlier guess was kombu's
binding-deadline Lua cleanup. In kombu 5.7.0, though, `REFRESH_BINDING` and
`SWEEP_BINDINGS` only touch `_kombu.binding*`, `_kombu.binding_permanent.*`
and `_kombu.binding_deadlines` for the `celery.pidbox`, `reply.celery.pidbox`
and `celeryev` exchanges, which the worker patterns already cover. Binding
TTLs are at least one hour, so a three-minute run never sweeps anything. The
missing `RPOP`/`PEXPIRE` (finding 2) is the best remaining candidate: any
stray pidbox reply hits it. The rule below still applies: the denial counts
as closed only when the log names it, or after five clean runs with the fixes.

**How to diagnose.** `rehearse.sh` now prints the `ACL LOG` metadata
(`reason`, `context`, `object`, `username`; never payloads) whenever a denial
occurs. Run it until the denial recurs:

```sh
for i in 1 2 3 4 5; do infrastructure/secure-transport/rehearse.sh | grep -vE '^PASS|^== |^$'; done
```

or keep the stack with `KEEP=1` and query `ACL LOG` as `studyforge_ops`.

**Fix and exit criteria.** Grant only the specific command/key/channel the log
names, on the user that needed it, in `redis-users.acl.template`. Then require
five consecutive clean runs. If the denial would break Celery (rather than
being cosmetic cleanup), record which. Do not load these ACLs on production
Redis until this is closed. After the production cutover, `ACL LOG` stays part
of the verification checklist.

## Approved decisions (Aashish, 2026-11-20)

1. One private CA (openssl) signs the PostgreSQL and Redis server certificates.
   The CA key stays encrypted off the server; clients get only `ca.crt`.
2. Certificate SANs are IPs: `10.0.0.234` (OKE path) and `127.0.0.1` (host-local).
3. Secrets: root-only files under `/etc/studyforge/` on the VM; Kubernetes
   Secret `studyforge-processing-secrets`, created from a temporary file. OCI
   Vault is deferred.
4. Processing database `studyforge_processing` with split roles: NOLOGIN owner,
   migration-only login, runtime login. The `studyforge` database is untouched.
5. Redis: named users with passwords for every client and the default user
   disabled. Django and the legacy Celery service stay on loopback `6379` (with a
   password); OKE uses TLS on `6380`. Same DB 0 and queue names.
6. PostgreSQL `ssl=on`; Django settings unchanged for now (it negotiates TLS by
   default, verified below); the processing database requires TLS.
7. Ports bound to `127.0.0.1` and `10.0.0.234` only, a `DOCKER-USER` allow-list
   for the OKE pod subnet, and one new NSG on the API VNIC (5432/6380 from
   `studyforge-oke-pods-nsg`). No public exposure.
8. Final OKE test from OCI Cloud Shell on the private subnet with one temporary pod.
9. One ~45-minute evening window, after a `pg_dump` and a Redis snapshot.

## What is in the repository

| Path | Purpose |
|---|---|
| `docker-compose.secure.yml` | Override for the base Compose file: TLS entrypoints, HBA policy, ACL file, loopback/private-only ports (`!override`), `restart: unless-stopped`. Rollback is starting with the base file alone. |
| `infrastructure/secure-transport/generate-certs.sh` | Private CA plus PostgreSQL/Redis server certs (EC P-256, SAN list as argument, `--encrypt-ca-key`). Refuses to overwrite a CA. |
| `infrastructure/secure-transport/pg_hba.conf.template` | HBA policy: OKE range may reach only `studyforge_processing` as the runtime role over TLS; the processing DB never accepts plaintext; everything else behaves as before. |
| `infrastructure/secure-transport/postgres-entrypoint.sh` | Copies key material with PostgreSQL ownership, renders HBA with `PG_REMOTE_TLS_CIDR`, starts the stock image with `ssl=on`. The data-directory `pg_hba.conf` is untouched. |
| `infrastructure/secure-transport/redis.conf`, `redis-entrypoint.sh` | Plaintext 6379 plus TLS 6380, ACL file, production save policy unchanged (RDB, AOF off). |
| `infrastructure/secure-transport/redis-users.acl.template`, `generate-redis-acl.sh` | Least-privilege users (`studyforge_ops`, `studyforge_django`, `studyforge_worker`) rendered with new random passwords (file holds SHA-256 hashes only). |
| `services/document-processing/provision_database.py` | Opt-in split roles when `PROCESSING_DB_MIGRATOR` is set; default single-owner behaviour unchanged (keeps Compose and `check_processing_live.py` working). |
| `services/document-processing/processing_service/tests/test_provision_database.py` | Real-PostgreSQL tests of the split (runs in CI against the disposable server; skips without a superuser). |
| `infrastructure/secure-transport/rehearse.sh` plus `rehearsal.compose.yml`, `broker_probe.py`, `pg_probe.py` | Repeatable local rehearsal: upgrade, access matrix, Celery (including overlapping workers), password-reset cache, rollback. |
| `infrastructure/secure-transport/docker-user-allowlist.sh`, `studyforge-docker-user-allowlist.service` | `DOCKER-USER` drop rules for non-OKE sources on 5432/6380, re-applied whenever Docker starts. Shellcheck only; not yet run on Linux. |
| `docs/deployment/scrum-134-production-runsheet.md` | Production steps, expected output, stop conditions and rollback. |

## How the pieces fit

- **PostgreSQL:** native TLS (TLSv1.2+). From `PG_REMOTE_TLS_CIDR` (production:
  the verified OKE pod source, expected `10.0.1.0/24`) only `hostssl
  studyforge_processing studyforge_processing` with SCRAM is allowed; every
  other OKE login is rejected. Host-local Django arrives from the Docker
  gateway and keeps its existing SCRAM rule.
- **Processing roles:** `studyforge_processing_owner` (NOLOGIN) owns the
  database and tables. `studyforge_processing_migrator` (LOGIN, NOINHERIT)
  must `SET ROLE` the owner, via `PGOPTIONS="-c role=studyforge_processing_owner"`
  during `manage.py migrate`. `studyforge_processing` (runtime) has CONNECT,
  schema USAGE, SELECT/INSERT/UPDATE and sequence USAGE/SELECT; no DELETE or DDL.
- **Redis:** the default user is off; Django uses `redis://studyforge_django:<pw>@127.0.0.1:6379/0`
  (supported by the current server code without changes); the worker uses
  `rediss://studyforge_worker:<pw>@10.0.0.234:6380/0?ssl_cert_reqs=required&ssl_ca_certs=...`.

### Redis permissions and how they were measured

Commands, keys and channels were recorded with `MONITOR` against permissive
probe users while running the real code (celery 5.6.3, redis-py 6.4.0; kombu
was unpinned then, see finding 1, and is now pinned to 5.7.0): Django readiness `PING`,
`dispatch_document()`, a default-shape legacy Celery worker on `celery`, the
OKE worker command line from `oke-worker.yaml` over TLS, and a hard-killed
worker whose message is restored by a second worker (`crash_probe`). The
kombu source added `SMEMBERS` (exchange lookup), `EXISTS` (queue check) and
`UNSUBSCRIBE`.

- Both app users: connection, queue (`LPUSH/RPUSH/BRPOP/RPOP/LLEN/EXISTS/DEL/PEXPIRE`),
  transactions (`MULTI/EXEC/DISCARD/WATCH/UNWATCH`), unacked tracking (hash,
  sorted set, `GET/SET` mutex), bindings (sets), Lua (`EVALSHA`, `SCRIPT LOAD|EXISTS`,
  `TIME`), Pub/Sub on `/0.celery.pidbox` and `/0.celeryev/worker.*`.
- `studyforge_worker` keys: `document-processing*`, its own binding keys,
  `_kombu.binding_deadlines`, `unacked*`, `celeryev.*`, `*.celery.pidbox*`. It
  cannot touch the `celery` queue or its bindings.
- `studyforge_django` additionally covers `celery*` and all bindings, because
  Gunicorn and the legacy `studyforge-celery.service` share one broker URL,
  plus `INCRBY` on `studyforge_password_reset:*` for the password-reset cache.
- Known, safe edge: `unacked` is shared per Redis DB. If the worker ever tries
  to restore an expired legacy `celery` message, the restore transaction is
  refused and the message stays for the legacy consumer.

## Rehearsal

```sh
infrastructure/secure-transport/rehearse.sh          # about 3 minutes, cleans up
KEEP=1 infrastructure/secure-transport/rehearse.sh   # leave the stack running
```

It starts a production-like plaintext pair, seeds an application row and a
queued task, upgrades in place with the override, provisions and migrates the
processing database, checks every rule from a simulated OKE network
(`172.31.250.128/25`) and from the host, runs Celery end to end, rolls back,
and re-checks the data. All credentials live in a private temporary directory.

### Evidence (2026-11-20, macOS arm64, Docker 29.7.2, Compose 5.5.0)

- `rehearse.sh`: **46/46 passed**, including:
  - data and the queued task survived the upgrade;
  - no wildcard port publications;
  - exactly `executions.0001_initial` and `0002_callback_delivery`, owned by the
    NOLOGIN owner;
  - from OKE: runtime `verify-full` connected over TLSv1.3; plaintext, the
    application database, the migrator, the Django superuser, a wrong password
    and a certificate name mismatch were refused;
  - unchanged Django settings negotiated TLS automatically;
  - Redis refused anonymous access, wrong passwords, untrusted CAs and
    plaintext on 6380, and denied the worker `celery` keys, `FLUSHALL`,
    `CONFIG` and other channels;
  - the manifest's readiness check passed in secure mode and stopped a worker
    with a bad DB password before it subscribed;
  - tasks queued before and after the upgrade and a real `dispatch_document()`
    were consumed over TLS; a killed worker's message was restored and finished;
    the legacy `celery` consumer worked;
  - rollback restored the original behaviour with the data intact.
- Harness mutation (HBA weakened): the two plaintext checks failed as
  expected. This run also surfaced the open ACL issue above.
- `test_provision_database.py`: 5/5 against TLS PostgreSQL 16. Granting
  DELETE to the runtime role, or letting the migrator inherit the owner, each
  made the tests fail.
- ShellCheck clean on all scripts.

## Production findings (read-only, 2026-11-20)

- `studyforge-api` runs Compose 5.7.1 (`!override` supported) and checkout
  `6c3922f`; the Compose file matches the repository.
- `studyforge-db-1` (pgvector pg16, `ssl=off`) and `studyforge-redis-1`
  (Redis 7.4.12) are published on `0.0.0.0` and `[::]`, both with
  **`restart=no`** (they would not return after a reboot; the override
  sets `unless-stopped`).
- Redis data is in an **anonymous volume**; RDB default save policy, AOF off,
  70 unsaved changes at the time. A `SAVE`/snapshot copy is mandatory before
  the container is recreated.
- **One task is waiting in `document-processing`** (no consumer exists yet).
  It must survive the change (rehearsed), and the first OKE worker will process
  it. Sanish should decide whether that is wanted.
- Gunicorn and `studyforge-celery.service` (`celery -A config worker`, queue
  `celery`) both use `CELERY_BROKER_URL=redis://127.0.0.1:6379/0` from
  `/etc/studyforge.env`.
- OCI: the API VNIC (`10.0.0.234`) has no NSG; public ingress is 22/80/443 and
  ICMP only; the OKE API NSG allows 6443 from `10.0.1.0/24`; NAT and service
  gateways exist.

## Remaining work

1. Re-run `rehearse.sh` five times on this branch (needs Docker). Expect zero
   failures and zero denials. Record the summaries. This closes the open issue.
2. Send the [run-sheet](./scrum-134-production-runsheet.md) to Aashish and
   book the window. It covers backups, secret placement, the in-place upgrade,
   processing DB provisioning and migrations, the Django broker switch,
   `DOCKER-USER` rules (`docker-user-allowlist.sh` plus its systemd unit), the
   NSG, the Cloud Shell test, the handoff, and rollback.
3. The VM checkout must contain these files first. Coordinate with the
   SCRUM-127 deploy so Django is deployed only once.
4. Hand Sanish the runtime values (run-sheet H1/H2).

## Rollback (summary)

Start PostgreSQL and Redis with `docker-compose.yml` alone. The data volumes
are reused; the data-directory `pg_hba.conf` was never modified; Redis returns
to its previous anonymous behaviour; the processing database and roles remain
(dropping them is a separate decision). Restore the previous
`CELERY_BROKER_URL` together with the Redis rollback. Remove the NSG and
`DOCKER-USER` rules first if they were added. The rehearsal exercises this path.
