#!/usr/bin/env bash
# Create the StudyForge private CA and PostgreSQL/Redis server certificates.
#
# Usage: generate-certs.sh OUT_DIR SAN_LIST [--encrypt-ca-key]
#   SAN_LIST is an OpenSSL subjectAltName list, for production:
#     IP:127.0.0.1,IP:10.0.0.234
#   --encrypt-ca-key prompts for a passphrase that protects ca.key.
#
# Distribute only ca.crt to clients. ca.key never goes to a server, a
# Kubernetes object, or Git. Each server receives only its own .crt/.key.
set -euo pipefail

usage() { echo "Usage: $0 OUT_DIR SAN_LIST [--encrypt-ca-key]" >&2; exit 2; }
[[ $# -ge 2 && $# -le 3 ]] || usage
out=$1
sans=$2
encrypt=${3:-}
[[ -z "$encrypt" || "$encrypt" == "--encrypt-ca-key" ]] || usage
[[ "$sans" =~ ^((IP|DNS):[A-Za-z0-9.:-]+,?)+$ ]] || { echo "Invalid SAN_LIST." >&2; exit 2; }

umask 077
mkdir -p "$out"
if [[ -e "$out/ca.key" || -e "$out/ca.crt" ]]; then
  echo "Refusing to overwrite an existing CA in $out." >&2
  exit 1
fi

if [[ "$encrypt" == "--encrypt-ca-key" ]]; then
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -aes-256-cbc -out "$out/ca.key"
else
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$out/ca.key"
fi
openssl req -x509 -new -key "$out/ca.key" -sha256 -days 1825 \
  -subj "/O=StudyForge/CN=StudyForge private CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash" \
  -out "$out/ca.crt"

extensions="$out/server-ext.cnf"
cat >"$extensions" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
subjectAltName=$sans
EOF

for service in postgres redis; do
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$out/$service.key"
  openssl req -new -key "$out/$service.key" -subj "/O=StudyForge/CN=studyforge-$service" -out "$out/$service.csr"
  openssl x509 -req -in "$out/$service.csr" -CA "$out/ca.crt" -CAkey "$out/ca.key" \
    -set_serial "0x$(openssl rand -hex 16)" -days 397 -sha256 \
    -extfile "$extensions" -out "$out/$service.crt"
  rm -f "$out/$service.csr"
  openssl verify -CAfile "$out/ca.crt" "$out/$service.crt" >/dev/null
done
rm -f "$extensions"
chmod 644 "$out/ca.crt" "$out/postgres.crt" "$out/redis.crt"
chmod 600 "$out/ca.key" "$out/postgres.key" "$out/redis.key"
echo "Created CA and server certificates in $out for: $sans"
