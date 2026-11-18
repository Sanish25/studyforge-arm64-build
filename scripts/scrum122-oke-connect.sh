#!/usr/bin/env bash
set -euo pipefail

action="${1:-start}"
requested_session_id="${2:-}"
profile="studyforge-scrum122-local"
region="us-phoenix-1"
target_ip="10.0.1.9"
target_port="6443"
local_ip="127.0.0.1"
local_port="16443"
ssh_key="$HOME/.ssh/studyforge-oke-bastion"
known_hosts="$HOME/.ssh/known_hosts.studyforge-bastion"
kubeconfig="$HOME/.kube/studyforge-oke-bastion"
state_dir="/private/tmp/studyforge-scrum122-oke"
session_file="$state_dir/session-id"
pid_file="$state_dir/tunnel.pid"
log_file="$state_dir/tunnel.log"
ssh_host="host.bastion.us-phoenix-1.oci.oraclecloud.com"
approved_session_id="ocid1.bastionsession.oc1.phx.amaaaaaatvvdeaaaq54p3lvzrnavrectihwgsoabbwcokklm4trwdzivr2kq"

usage() {
  echo "Usage: $0 [start|reconnect] [session-ocid] | [stop|status]" >&2
  exit 2
}

case "$action" in
  start|reconnect) [[ "$#" -le 2 ]] || usage ;;
  stop|status) [[ "$#" -eq 1 ]] || usage ;;
  *) usage ;;
esac
if [[ -n "$requested_session_id" && ! "$requested_session_id" =~ ^ocid1\.bastionsession\.oc1\.phx\.[[:alnum:]]+$ ]]; then
  usage
fi

oci_safe() {
  printf 'n\n' | oci "$@"
}

mkdir -p "$state_dir"
chmod 700 "$state_dir"

owns_listener() {
  local pid="$1" listeners
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  listeners="$(lsof -nP -a -p "$pid" -iTCP:"$local_port" -sTCP:LISTEN)" || return 1
  awk -v endpoint="$local_ip:$local_port" \
    'NR > 1 && $1 == "ssh" && $9 == endpoint { found = 1 } END { exit !found }' <<<"$listeners"
}

port_has_listener() {
  lsof -nP -iTCP:"$local_port" -sTCP:LISTEN >/dev/null
}

stop_tunnel() {
  local pid
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if owns_listener "$pid"; then
      if ! kill -TERM "$pid"; then
        echo "Could not signal the verified SSH listener (pid $pid)." >&2
        return 1
      fi
      for _ in {1..10}; do
        owns_listener "$pid" || break
        sleep 1
      done
      if owns_listener "$pid"; then
        echo "SSH tunnel did not stop cleanly (pid $pid)." >&2
        return 1
      fi
    fi
  fi
  if port_has_listener; then
    echo "Port $local_port still has a listener. Verify its owner before stopping it." >&2
    return 1
  fi
  if [[ -f "$pid_file" ]]; then
    rm -f "$pid_file"
  fi
}

verify_oke() {
  kubectl --kubeconfig "$kubeconfig" get nodes -o json --request-timeout=15s | \
    python3 -c 'import json,sys; x=json.load(sys.stdin); ns=x.get("items",[]); r=sum(any(c.get("type")=="Ready" and c.get("status")=="True" for c in n.get("status",{}).get("conditions",[])) for n in ns); print(f"OKE nodes Ready={r}/{len(ns)}")'
}

start_tunnel() {
  local id metadata pid
  id="$approved_session_id"
  if [[ -f "$session_file" ]]; then
    id="$(cat "$session_file")"
  fi
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if owns_listener "$pid"; then
      if [[ -n "$requested_session_id" && "$requested_session_id" != "$id" ]]; then
        echo "Use reconnect to switch the running tunnel to the requested session." >&2
        return 1
      fi
      echo "Tunnel process is already running (pid $pid)."
      verify_oke
      return
    fi
  fi
  if port_has_listener; then
    echo "Local port $local_ip:$local_port is already in use." >&2
    return 1
  fi
  id="${requested_session_id:-$id}"
  metadata="$(oci_safe --profile "$profile" --auth security_token --region "$region" \
    bastion session get --session-id "$id" --output json)" || {
      echo "Could not read the Bastion session. Check OCI authentication and the session ID." >&2
      return 1
    }
  umask 077
  python3 - "$metadata" "$ssh_key" "$known_hosts" "$pid_file" "$log_file" \
    "$local_ip" "$local_port" "$target_ip" "$target_port" "$ssh_host" <<'PY'
import json
import os
import shlex
import socket
import subprocess
import sys
import time

metadata, private_key, known_hosts, pid_file, log_file, local_ip, local_port, target_ip, target_port, expected_host = sys.argv[1:]
data = json.loads(metadata).get("data", {})
if data.get("lifecycle-state") != "ACTIVE":
    raise SystemExit(f"Bastion session state is {data.get('lifecycle-state', 'unknown')}. Use an ACTIVE session.")
details = data.get("target-resource-details", {})
if details.get("target-resource-private-ip-address") != target_ip or str(details.get("target-resource-port")) != target_port:
    raise SystemExit("OCI session target did not match the approved OKE endpoint.")
if not os.path.isfile(private_key) or os.stat(private_key).st_mode & 0o077:
    raise SystemExit("Dedicated SSH key is missing or has unsafe permissions.")
if not os.path.isfile(known_hosts):
    raise SystemExit("Pinned Bastion host key is missing; refusing an unverified SSH connection.")

command = shlex.split((data.get("ssh-metadata") or {}).get("command", ""))
if not command or command[0] != "ssh":
    raise SystemExit("OCI returned an unrecognized SSH command.")
try:
    key_index = command.index("-i") + 1
    forward_index = command.index("-L") + 1
except (ValueError, IndexError):
    raise SystemExit("OCI SSH metadata omitted the key or port-forward arguments.")
command[key_index] = private_key
command[forward_index] = f"{local_ip}:{local_port}:{target_ip}:{target_port}"
if not command[-1].endswith("@" + expected_host):
    raise SystemExit("OCI SSH metadata returned an unexpected Bastion hostname.")
command[1:1] = [
    "-o", "IdentitiesOnly=yes",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", f"UserKnownHostsFile={known_hosts}",
    "-o", "ConnectTimeout=10",
]
with open(log_file, "ab") as log:
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=log, start_new_session=True)
with open(pid_file, "w", encoding="utf-8") as stream:
    stream.write(str(proc.pid) + "\n")
os.chmod(pid_file, 0o600)
for _ in range(20):
    if proc.poll() is not None:
        os.unlink(pid_file)
        raise SystemExit("SSH exited before the local tunnel opened; inspect the private log file.")
    try:
        with socket.create_connection((local_ip, int(local_port)), timeout=1):
            print(f"SSH tunnel is listening on {local_ip}:{local_port} (pid {proc.pid}).")
            break
    except OSError:
        time.sleep(0.5)
else:
    proc.terminate()
    os.unlink(pid_file)
    raise SystemExit("SSH tunnel did not open its local port within 10 seconds.")
PY
  printf '%s\n' "$id" > "$session_file"
  verify_oke
}

case "$action" in
  start) start_tunnel ;;
  reconnect) stop_tunnel; start_tunnel ;;
  stop) stop_tunnel; echo "Local SSH tunnel stopped; the Bastion session expires automatically." ;;
  status)
    if [[ -f "$pid_file" ]] && pid="$(cat "$pid_file")" && owns_listener "$pid"; then
      echo "SSH tunnel is listening on $local_ip:$local_port (pid $pid)."
    elif port_has_listener; then
      echo "Port $local_port has a listener that is not managed by this script." >&2
      exit 1
    else
      echo "No managed SSH tunnel is running."
    fi
    ;;
esac
