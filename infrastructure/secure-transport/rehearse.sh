#!/usr/bin/env bash
# SCRUM-134 local rehearsal. Starts a production-like (plaintext, anonymous)
# PostgreSQL/Redis pair, seeds data and a queued task, upgrades it in place to
# TLS + named users, verifies every access rule and the Celery path from a
# simulated OKE network, then rolls back and checks the data is still there.
#
# Needs Docker and a Python with celery, psycopg, redis and Django (the
# backend virtualenv): PYTHON defaults to backend/venv/bin/python.
#   infrastructure/secure-transport/rehearse.sh         # run, then clean up
#   KEEP=1 infrastructure/secure-transport/rehearse.sh  # leave the stack up
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
here=infrastructure/secure-transport
py=${PYTHON:-backend/venv/bin/python}
py="$(cd "$(dirname "$py")" && pwd)/$(basename "$py")"
image=studyforge-document-processing:sf134
work=$(mktemp -d "${TMPDIR:-/tmp}/sf134.XXXXXX")
chmod 700 "$work"
failures=0

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }
expect() { # LABEL REGEX OUTPUT
  if grep -qE -- "$2" <<<"$3"; then pass "$1"; else fail "$1 (got: ${3:0:160})"; fi
}
section() { printf '\n== %s\n' "$1"; }

cat >"$work/compose.env" <<EOF
COMPOSE_PROJECT_NAME=sf134r
POSTGRES_PASSWORD=rehearsal-$(openssl rand -hex 12)
POSTGRES_PORT=55432
POSTGRES_PRIVATE_PORT=55433
REDIS_PORT=56379
REDIS_TLS_PORT=56380
STUDYFORGE_PRIVATE_IP=127.0.0.1
PG_REMOTE_TLS_CIDR=172.31.250.128/25
STUDYFORGE_TLS_DIR=$work/tls
STUDYFORGE_REDIS_ACL_FILE=$work/acl/redis-users.acl
EOF
app_password=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$work/compose.env")
base() { docker compose --env-file "$work/compose.env" -f docker-compose.yml -f "$here/rehearsal.compose.yml" "$@"; }
secure() { docker compose --env-file "$work/compose.env" -f docker-compose.yml -f docker-compose.secure.yml -f "$here/rehearsal.compose.yml" "$@"; }
legacy=
# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  # A surviving legacy worker would keep logging in to the next run's Redis
  # with stale credentials (seen as an `auth` ACL denial there).
  if [[ -n "$legacy" ]]; then kill "$legacy" 2>/dev/null || true; fi
  docker ps -q --filter name=sf134r- | xargs -r docker stop >/dev/null 2>&1 || true
  if [[ "${KEEP:-0}" != 1 ]]; then
    secure down --volumes --remove-orphans >/dev/null 2>&1 || true
  else
    echo "Stack left running; credentials in $work"
  fi
}
trap cleanup EXIT

section "Prepare certificates, Redis ACL, credentials and worker image"
if pgrep -f "$here/broker_probe.py worker" >/dev/null; then
  echo "A broker_probe.py worker from an earlier run is still running; stop it first." >&2
  exit 1
fi
"$here/generate-certs.sh" "$work/tls" IP:127.0.0.1,IP:172.31.250.10,IP:172.31.250.11 >/dev/null 2>&1
"$here/generate-redis-acl.sh" "$work/acl" >/dev/null
# shellcheck disable=SC1091
. "$work/acl/redis-credentials.env"
runtime_password=$(openssl rand -hex 32)
migrator_password=$(openssl rand -hex 32)
docker image inspect "$image" >/dev/null 2>&1 || docker build -q -t "$image" services/document-processing >/dev/null
pass "inputs ready in a private temporary directory"
# The ACL is measured against exact versions; a stale image or venv invalidates the run.
versions='import celery, kombu, redis; print(celery.__version__, kombu.__version__, redis.__version__)'
expect "worker image has the pinned celery/kombu/redis" "^5\.6\.3 5\.7\.0 6\.4\.0$" "$(docker run --rm --entrypoint python "$image" -c "$versions")"
expect "probe Python has the pinned celery/kombu/redis" "^5\.6\.3 5\.7\.0 6\.4\.0$" "$("$py" -c "$versions")"

ops() { docker exec sf134r-redis-1 redis-cli --user studyforge_ops --pass "$REDIS_OPS_PASSWORD" --no-auth-warning "$@"; }
psql_app() { docker exec sf134r-db-1 psql -U studyforge -d "$1" -tAc "$2"; }
on_oke() { # IP CMD... : run a client container from the simulated OKE pod range
  local ip=$1; shift
  docker run --rm --network sf134r_oke-sim --ip "$ip" -v "$work/tls/ca.crt:/ca.pem:ro" \
    -v "$root/$here/pg_probe.py:/pg_probe.py:ro" "$@" 2>&1
}
oke_pg() { on_oke 172.31.250.210 "$image" python /pg_probe.py "$@"; }
oke_redis() { on_oke 172.31.250.211 redis:7-alpine redis-cli --tls --cacert /ca.pem -h 172.31.250.11 -p 6380 --no-auth-warning "$@" | head -1; }
host_pg() { "$py" "$here/pg_probe.py" "$@" 2>&1; }
broker() { SF134_BROKER_URL=$1 "$py" "$here/broker_probe.py" "${@:2}" 2>&1; }
django_url="redis://studyforge_django:$REDIS_DJANGO_PASSWORD@127.0.0.1:56379/0"
worker_url="rediss://studyforge_worker:$REDIS_WORKER_PASSWORD@172.31.250.11:6380/0?ssl_cert_reqs=required&ssl_ca_certs=/etc/studyforge/trust/redis-ca.pem"

section "Before: production-like plaintext services with data and a queued task"
base up -d --wait db redis >/dev/null 2>&1
psql_app studyforge "CREATE TABLE sf134_seed (v text); INSERT INTO sf134_seed VALUES ('kept')" >/dev/null
broker redis://127.0.0.1:56379/0 send document-processing sf134-queued-before-upgrade >/dev/null
expect "anonymous Redis works before the change" "^PONG$" "$(docker exec sf134r-redis-1 redis-cli ping)"
expect "one task is queued before the change" "^1$" "$(docker exec sf134r-redis-1 redis-cli LLEN document-processing)"
docker exec sf134r-redis-1 redis-cli SAVE >/dev/null

section "Upgrade in place: TLS, HBA policy, named Redis users, loopback/private binds"
secure up -d --wait db redis >/dev/null 2>&1
expect "PostgreSQL ssl is on" "^on$" "$(psql_app postgres 'show ssl')"
expect "application data survived the upgrade" "^kept$" "$(psql_app studyforge 'select v from sf134_seed')"
expect "queued task survived the Redis recreate" "^1$" "$(ops LLEN document-processing)"
expect "Redis default user is disabled" "user default off" "$(ops ACL LIST)"
expect "no wildcard IPv4/IPv6 port publications" "^0$" \
  "$( (docker port sf134r-db-1; docker port sf134r-redis-1) | grep -cE '0\.0\.0\.0|\[::\]' || true)"

section "Processing database: least-privilege roles and the two migrations"
if (
  cd services/document-processing
  export PROCESSING_DB_NAME=studyforge_processing PROCESSING_DB_USER=studyforge_processing \
    PROCESSING_DB_OWNER=studyforge_processing_owner PROCESSING_DB_MIGRATOR=studyforge_processing_migrator \
    PROCESSING_DB_HOST=127.0.0.1 PROCESSING_DB_PORT=55432 PROCESSING_DB_SSLMODE=verify-full \
    PROCESSING_DB_SSLROOTCERT="$work/tls/ca.crt" PROCESSING_APPLICATION_DB=studyforge
  PROCESSING_DB_ADMIN_USER=studyforge PROCESSING_DB_ADMIN_PASSWORD="$app_password" \
    PROCESSING_DB_PASSWORD="$runtime_password" PROCESSING_DB_MIGRATOR_PASSWORD="$migrator_password" \
    "$py" -B provision_database.py
  PROCESSING_SECRET_KEY=rehearsal PROCESSING_DB_USER=studyforge_processing_migrator \
    PROCESSING_DB_PASSWORD="$migrator_password" PGOPTIONS="-c role=studyforge_processing_owner" \
    "$py" -B manage.py migrate --noinput
) >"$work/migrate.log" 2>&1; then
  pass "provisioned and migrated over verify-full"
else
  fail "provision/migrate (see $work/migrate.log)"
fi
expect "exactly the two processing migrations are applied" "^executions[|]0001_initial,executions[|]0002_callback_delivery$" \
  "$(psql_app studyforge_processing "select string_agg(app||'|'||name, ',' order by name) from django_migrations")"
expect "tables are owned by the NOLOGIN owner" "^studyforge_processing_owner$" \
  "$(psql_app studyforge_processing "select string_agg(distinct tableowner, ',') from pg_tables where schemaname='public'")"

section "PostgreSQL from the simulated OKE pod network"
db=172.31.250.10
expect "runtime role, verify-full, processing DB" "CONNECTED ssl=True TLSv1\.[23]" "$(oke_pg studyforge_processing "$runtime_password" studyforge_processing $db 5432 verify-full /ca.pem)"
expect "plaintext is refused" "REFUSED: .*no encryption" "$(oke_pg studyforge_processing "$runtime_password" studyforge_processing $db 5432 disable)"
expect "application database is refused" "REFUSED: .*rejects connection" "$(oke_pg studyforge_processing "$runtime_password" studyforge $db 5432 verify-full /ca.pem)"
expect "migrator login is refused from OKE" "REFUSED: .*rejects connection" "$(oke_pg studyforge_processing_migrator "$migrator_password" studyforge_processing $db 5432 verify-full /ca.pem)"
expect "Django superuser is refused from OKE" "REFUSED: .*rejects connection" "$(oke_pg studyforge "$app_password" studyforge $db 5432 verify-full /ca.pem)"
expect "wrong password is refused" "REFUSED: .*password authentication failed" "$(oke_pg studyforge_processing wrong studyforge_processing $db 5432 verify-full /ca.pem)"
expect "certificate name mismatch is refused" "REFUSED: .*(certificate|does not match)" "$(oke_pg studyforge_processing "$runtime_password" studyforge_processing db 5432 verify-full /ca.pem)"

section "PostgreSQL from the host (existing Django, settings unchanged)"
expect "default sslmode negotiates TLS" "CONNECTED ssl=True" "$(host_pg studyforge "$app_password" studyforge 127.0.0.1 55432 default)"
expect "Django verify-full via 127.0.0.1 works (future setting)" "CONNECTED ssl=True" "$(host_pg studyforge "$app_password" studyforge 127.0.0.1 55432 verify-full "$work/tls/ca.crt")"
expect "processing DB refuses host plaintext" "REFUSED: .*no encryption" "$(host_pg studyforge_processing "$runtime_password" studyforge_processing 127.0.0.1 55432 disable)"

section "Redis access rules"
expect "worker PING over TLS" "^PONG$" "$(oke_redis --user studyforge_worker --pass "$REDIS_WORKER_PASSWORD" ping)"
expect "anonymous over TLS is refused" "NOAUTH" "$(oke_redis ping)"
# Full output, not oke_redis's first line: the AUTH error and NOAUTH reply race on stdout/stderr.
expect "wrong password is refused" "WRONGPASS" "$(on_oke 172.31.250.211 redis:7-alpine redis-cli --tls --cacert /ca.pem \
  -h 172.31.250.11 -p 6380 --no-auth-warning --user studyforge_worker --pass wrong ping)"
expect "plaintext to the TLS port fails" "(reset|closed|Error)" "$(on_oke 172.31.250.212 redis:7-alpine redis-cli -h 172.31.250.11 -p 6380 ping | head -1)"
expect "worker cannot touch the legacy celery queue" "NOPERM" "$(oke_redis --user studyforge_worker --pass "$REDIS_WORKER_PASSWORD" LPUSH celery x)"
expect "worker cannot FLUSHALL" "NOPERM" "$(oke_redis --user studyforge_worker --pass "$REDIS_WORKER_PASSWORD" FLUSHALL)"
expect "worker cannot read configuration" "NOPERM" "$(oke_redis --user studyforge_worker --pass "$REDIS_WORKER_PASSWORD" CONFIG GET dir)"
expect "Django user cannot change ACLs" "NOPERM" "$(docker exec sf134r-redis-1 redis-cli --user studyforge_django --pass "$REDIS_DJANGO_PASSWORD" --no-auth-warning ACL SETUSER x on 2>&1)"
expect "Django readiness PING (loopback, named user)" "ping: ok" "$(broker "$django_url" ping)"
ops ACL LOG RESET >/dev/null
expect "Django user can use the password-reset cache" "^reset-cache: ok$" "$(broker "$django_url" reset-cache)"

section "Celery: secure OKE-equivalent worker and the legacy consumer"
dependency_check=$("$py" -c "
import sys, yaml
for doc in yaml.safe_load_all(open('services/document-processing/oke-worker.yaml')):
    if doc and doc['kind'] == 'Deployment':
        env = doc['spec']['template']['spec']['containers'][0]['env']
        print(next(e['value'] for e in env if e['name'] == 'WORKER_DEPENDENCY_CHECK'))")
# Same shell semantics as the manifest's `/bin/sh -ec` wrapper (expanded in the container).
# shellcheck disable=SC2016
printf 'set -e\npython -c "$WORKER_DEPENDENCY_CHECK"\necho "DEPENDENCY CHECK PASSED"\nexec "$@"\n' >"$work/entry.sh"
secure_worker() { # NAME IP DB_PASSWORD [docker-run flags]
  local name=$1 ip=$2 password=$3; shift 3
  docker run --rm --name "$name" --network sf134r_oke-sim --ip "$ip" "$@" \
    -v "$work/tls/ca.crt:/etc/studyforge/trust/postgres-ca.pem:ro" -v "$work/tls/ca.crt:/etc/studyforge/trust/redis-ca.pem:ro" \
    -v "$work/entry.sh:/entry.sh:ro" -e WORKER_DEPENDENCY_CHECK="$dependency_check" \
    -e DJANGO_SETTINGS_MODULE=processing_service.settings -e STUDYFORGE_REQUIRE_SECURE_CONNECTIONS=1 \
    -e PROCESSING_SECRET_KEY="rehearsal-$(openssl rand -hex 8)" -e PROCESSING_DB_HOST=$db -e PROCESSING_DB_PORT=5432 \
    -e PROCESSING_DB_NAME=studyforge_processing -e PROCESSING_DB_USER=studyforge_processing -e PROCESSING_DB_PASSWORD="$password" \
    -e PROCESSING_DB_SSLMODE=verify-full -e PROCESSING_DB_SSLROOTCERT=/etc/studyforge/trust/postgres-ca.pem \
    -e PROCESSING_REDIS_URL="$worker_url" -e PROCESSING_REDIS_VISIBILITY_TIMEOUT=5 \
    -e PROCESSING_DJANGO_API_URL=https://api.example.test -e PROCESSING_SOURCE_MODE=django \
    --entrypoint /bin/sh "$image" /entry.sh celery -A processing_service.celery:app worker --loglevel=INFO \
    --concurrency=1 --prefetch-multiplier=1 --queues=document-processing --hostname="$name@%h" \
    --include=processing_service.tests.crash_probe 2>&1
}
expect "readiness gate stops a worker with a bad DB password" "\"database\": \"unavailable\"" "$(secure_worker sf134r-neg 172.31.250.220 wrong || true)"
secure_worker sf134r-w1 172.31.250.221 "$runtime_password" -d >/dev/null
sleep 12
broker "$django_url" dispatch >/dev/null
broker "$django_url" send document-processing >/dev/null
ops_url="rediss://studyforge_ops:$REDIS_OPS_PASSWORD@172.31.250.11:6380/0?ssl_cert_reqs=required&ssl_ca_certs=/etc/studyforge/trust/redis-ca.pem"
docker exec sf134r-w1 python -c "
from celery import Celery; import os
Celery(broker=os.environ['PROCESSING_REDIS_URL']).send_task('processing_service.tests.crash_probe.run',
    args=['$ops_url', 'sf134r-crash'], queue='document-processing', ignore_result=True)"
sleep 4
w1_log=$(docker logs sf134r-w1 2>&1)
docker kill sf134r-w1 >/dev/null
expect "manifest readiness check passes in secure mode" "DEPENDENCY CHECK PASSED" "$w1_log"
expect "worker connected over rediss" "Connected to rediss://" "$w1_log"
expect "task queued before the upgrade was consumed" "succeeded.*sf134-queued-before-upgrade" "$w1_log"
expect "task published after the upgrade was consumed" "succeeded.*'sf134-marker'" "$w1_log"
expect "real dispatch_document() publish was consumed" "process_document_task\[.*received" "$w1_log"
secure_worker sf134r-w2 172.31.250.222 "$runtime_password" -d >/dev/null
sleep 20
expect "message from a killed worker was restored and finished" "^sf134r-w1@.* sf134r-w2@" "$(ops MGET sf134r-crash:first sf134r-crash:recovered | paste -sd' ' -)"
# Production topology: the VM's legacy consumer runs while the OKE worker is
# up, so startup mingle and control replies cross both Redis users.
# exec, so $! is the Python worker itself and `kill` really stops it.
(SF134_BROKER_URL=$django_url exec "$py" "$here/broker_probe.py" worker celery) >"$work/legacy.log" 2>&1 &
legacy=$!
sleep 8
expect "legacy consumer synced with the running OKE worker" "mingle: sync with 1 nodes" "$(cat "$work/legacy.log")"
expect "both workers answer a control ping" "replies: .*sf134-legacy@.*sf134r-w2@" "$(broker "$django_url" inspect)"
broker "$django_url" send celery >/dev/null
sleep 4
docker stop -t 10 sf134r-w2 >/dev/null
kill "$legacy"
wait "$legacy" 2>/dev/null || true
legacy=
expect "legacy celery-queue consumer works with the Django user" "celery\.accumulate\[.*succeeded" "$(cat "$work/legacy.log")"
denials=$(ops ACL LOG 100 | grep -cx reason || true)
expect "no Redis ACL denials during Celery traffic" "^0$" "$denials"
if [[ "$denials" != 0 ]]; then
  # ACL LOG metadata only (reason, context, denied command/key, user); no payloads.
  ops ACL LOG 100 | paste - - | grep -E '^(reason|context|object|username|age-seconds)'$'\t' | cut -c1-200
  # Which client: address, connection name, library and command only (no credentials).
  ops ACL LOG 100 | paste - - | sed -n 's/^client-info\t//p' | grep -oE '(addr|name|lib-name|lib-ver|cmd)=[^ ]*' | paste -sd' ' -
fi
expect "document-processing queue drained" "^0$" "$(ops LLEN document-processing)"

section "Rollback: base Compose file only"
ops SET sf134r:marker kept >/dev/null
ops SAVE >/dev/null
base up -d --wait db redis >/dev/null 2>&1
expect "PostgreSQL back to the original configuration" "^off$" "$(psql_app postgres 'show ssl')"
expect "application data intact after rollback" "^kept$" "$(psql_app studyforge 'select v from sf134_seed')"
expect "processing database preserved" "^1$" "$(psql_app postgres "select count(*) from pg_database where datname='studyforge_processing'")"
expect "anonymous Redis restored (pre-change behaviour)" "^PONG$" "$(docker exec sf134r-redis-1 redis-cli ping)"
expect "Redis data intact after rollback" "^kept$" "$(docker exec sf134r-redis-1 redis-cli GET sf134r:marker)"

printf '\n%s\n' "$([[ $failures -eq 0 ]] && echo "REHEARSAL PASSED" || echo "REHEARSAL FAILED: $failures check(s)")"
exit $((failures > 0))
