#!/usr/bin/env bash
# SCRUM-134: let only the verified OKE source reach the PostgreSQL and Redis
# TLS ports that Docker publishes on the VM's private address. Published ports
# bypass the INPUT chain, so the rules live in Docker's DOCKER-USER chain and
# match the pre-DNAT destination. Every rule carries one comment, so `remove`
# deletes exactly what `apply` added.
#
# Usage (as root): docker-user-allowlist.sh apply|remove|status
# Config file (default /etc/studyforge/docker-user-allowlist.env):
#   STUDYFORGE_PRIVATE_IP=10.0.0.234
#   OKE_SOURCE_CIDR=<verified OKE source, e.g. 10.0.1.0/24>
#   PRIVATE_INTERFACE=enp0s6          # optional
#   ALLOWLIST_PORTS="5432 6380"       # optional
set -euo pipefail

[[ $# -eq 1 && "$1" =~ ^(apply|remove|status)$ ]] || { echo "Usage: $0 apply|remove|status" >&2; exit 2; }
action=$1
conf=${STUDYFORGE_ALLOWLIST_CONF:-/etc/studyforge/docker-user-allowlist.env}
comment=studyforge-scrum-134

remove_rules() {
  local line parts
  while read -r line; do
    read -r -a parts <<<"$line"
    parts[0]=-D
    iptables "${parts[@]}"
  done < <(iptables -S DOCKER-USER | grep -F -- "--comment $comment" || true)
}

wait_for_chain() {
  for _ in $(seq 30); do
    iptables -S DOCKER-USER >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "DOCKER-USER chain not found; is Docker running with iptables enabled?" >&2
  exit 1
}

wait_for_chain
case "$action" in
  status)
    iptables -L DOCKER-USER -v -n --line-numbers
    exit 0
    ;;
  remove)
    remove_rules
    exit 0
    ;;
esac

# shellcheck disable=SC1090
. "$conf"
: "${STUDYFORGE_PRIVATE_IP:?Set STUDYFORGE_PRIVATE_IP in $conf}"
: "${OKE_SOURCE_CIDR:?Set OKE_SOURCE_CIDR in $conf}"
iface=${PRIVATE_INTERFACE:-enp0s6}
read -r -a ports <<<"${ALLOWLIST_PORTS:-5432 6380}"
ipv4='([0-9]{1,3}\.){3}[0-9]{1,3}'
[[ "$STUDYFORGE_PRIVATE_IP" =~ ^$ipv4$ ]] || { echo "STUDYFORGE_PRIVATE_IP must be an IPv4 address." >&2; exit 1; }
[[ "$OKE_SOURCE_CIDR" =~ ^$ipv4/([0-9]|[12][0-9]|3[0-2])$ ]] || { echo "OKE_SOURCE_CIDR must be an IPv4 CIDR." >&2; exit 1; }
ip -o link show "$iface" >/dev/null || { echo "Interface $iface not found." >&2; exit 1; }

remove_rules
for port in "${ports[@]}"; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] || { echo "Invalid port: $port" >&2; exit 1; }
  iptables -I DOCKER-USER 1 -i "$iface" -p tcp ! -s "$OKE_SOURCE_CIDR" \
    -m conntrack --ctorigdst "$STUDYFORGE_PRIVATE_IP" --ctorigdstport "$port" \
    -m comment --comment "$comment" -j DROP
done
iptables -S DOCKER-USER | grep -F -- "--comment $comment"
