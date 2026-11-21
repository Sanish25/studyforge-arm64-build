#!/bin/sh
# Start the stock PostgreSQL image with TLS and the SCRUM-134 HBA policy.
# Server key material is copied into the container filesystem so PostgreSQL
# owns it with mode 0600, whatever the host file ownership is.
set -eu

: "${PG_REMOTE_TLS_CIDR:?Set PG_REMOTE_TLS_CIDR to the verified OKE pod source range.}"
case "$PG_REMOTE_TLS_CIDR" in
  *[!0-9./]* | "") echo "PG_REMOTE_TLS_CIDR must be an IPv4 CIDR." >&2; exit 1 ;;
esac

source_dir=/run/studyforge-tls-source
tls_dir=/var/run/postgresql/studyforge-tls
install -d -o postgres -g postgres -m 700 "$tls_dir"
install -o postgres -g postgres -m 600 "$source_dir/postgres.key" "$tls_dir/server.key"
install -o postgres -g postgres -m 644 "$source_dir/postgres.crt" "$tls_dir/server.crt"
sed "s#@REMOTE_TLS_CIDR@#$PG_REMOTE_TLS_CIDR#g" /etc/studyforge/pg_hba.conf.template >"$tls_dir/pg_hba.conf"
chown postgres:postgres "$tls_dir/pg_hba.conf"
chmod 600 "$tls_dir/pg_hba.conf"

exec docker-entrypoint.sh postgres \
  -c ssl=on \
  -c ssl_min_protocol_version=TLSv1.2 \
  -c ssl_cert_file="$tls_dir/server.crt" \
  -c ssl_key_file="$tls_dir/server.key" \
  -c hba_file="$tls_dir/pg_hba.conf" \
  "$@"
