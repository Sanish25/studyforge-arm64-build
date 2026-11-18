#!/usr/bin/env python3
"""Legacy SCRUM-122 Cloud Shell preflight, retained for historical reference.

The historical checks below use a fixed image tag and an older VM configuration.
The command line entry point is retired. Use the OKE deployment runbook for
current TLS, storage, and dependency validation.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
from urllib.parse import urlsplit

TENANCY_OCID = "ocid1.tenancy.oc1..aaaaaaaamic5qhkdlchwwn7ht3jflgtlmeqktb5l3uufwbtzn5nx5b4b47ia"
CLUSTER_OCID = "ocid1.cluster.oc1.phx.aaaaaaaazuokzxkbuwoqgz3ctjvqxww4d3vrwwhvpyrkbth55cmidganrxna"
EXPECTED_CLUSTER = "studyforge-oke"
EXPECTED_NAMESPACE = "studyforge"
EXPECTED_REPOSITORY = "studyforge/document-processing"
EXPECTED_IMAGE_TAG = "arm64-46d02f8a5edc998768c9f19e716a3d6019a869c1"
API_HOST = "studyforge-rodians.duckdns.org"
API_PRIVATE_IP = "10.0.0.234"
PLANNED_DB = {
    "PROCESSING_DB_HOST": API_PRIVATE_IP,
    "PROCESSING_DB_PORT": "5432",
    "PROCESSING_DB_NAME": "studyforge_processing",
    "PROCESSING_DB_USER": "studyforge_processing",
}
REQUIRED_SECRET_KEYS = {
    "PROCESSING_REDIS_URL",
    "PROCESSING_SECRET_KEY",
    "PROCESSING_DB_PASSWORD",
    "PROCESSING_SERVICE_TOKEN",
    "GEMINI_API_KEY",
}
EXPECTED_MIGRATION = "0002_callback_delivery"

checks: list[tuple[str, str, str]] = []
blockers: list[str] = []


def report(status: str, label: str, detail: str, *, blocker: bool = False) -> None:
    checks.append((status, label, detail))
    print(f"[{status}] {label}: {detail}")
    if blocker:
        blockers.append(f"{label}: {detail}")


def command(args: list[str], timeout: int = 20) -> tuple[int, str]:
    """Capture output in memory. Callers must never print untrusted output."""
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def json_command(args: list[str], timeout: int = 20) -> dict | list | None:
    code, stdout = command(args, timeout)
    if code != 0:
        return None
    try:
        return json.loads(stdout)
    except (TypeError, json.JSONDecodeError):
        return None


def field(obj: dict, *names: str, default=None):
    for name in names:
        if name in obj:
            return obj[name]
        alt = name.replace("-", "_")
        if alt in obj:
            return obj[alt]
    return default


def b64_secret(secret: dict | None, key: str) -> bytes | None:
    if not secret:
        return None
    encoded = (secret.get("data") or {}).get(key)
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None


def redis_ping(redis_url: str) -> tuple[bool, str]:
    """Send PING, AUTH (if configured), and SELECT without logging credentials."""
    try:
        parsed = urlsplit(redis_url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            return False, "broker URL is missing or is not redis:// or rediss://"
        port = parsed.port or (6380 if parsed.scheme == "rediss" else 6379)
        db_text = parsed.path.lstrip("/") or "0"
        db = int(db_text)
        raw = socket.create_connection((parsed.hostname, port), timeout=4)
        conn = (
            ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
            if parsed.scheme == "rediss"
            else raw
        )
        stream = conn.makefile("rwb", buffering=0)

        def request(*parts: str) -> str:
            payload = f"*{len(parts)}\r\n" + "".join(
                f"${len(part.encode())}\r\n{part}\r\n" for part in parts
            )
            stream.write(payload.encode())
            response = stream.readline(4096).decode("utf-8", "replace").strip()
            if response.startswith("-"):
                raise RuntimeError("Redis rejected a read-only command")
            return response

        if parsed.password is not None:
            if parsed.username:
                request("AUTH", parsed.username, parsed.password)
            else:
                request("AUTH", parsed.password)
        if db:
            request("SELECT", str(db))
        pong = request("PING")
        stream.close()
        conn.close()
        host_detail = f"{parsed.hostname}:{port}"
        return pong == "+PONG", f"{host_detail} returned PONG" if pong == "+PONG" else f"{host_detail} did not return PONG"
    except Exception:
        return False, "connection, authentication, or PING failed (credential details suppressed)"


def main() -> int:
    print("SCRUM-122 read-only Cloud Shell preflight")
    print("No Kubernetes, OCI, database, Redis, or credential state will be changed.\n")

    cloud_shell = (
        os.environ.get("OCI_CLI_AUTH") == "instance_obo_user"
        and os.environ.get("OCI_CLI_CONFIG_FILE") == "/etc/oci/config"
    )
    report(
        "PASS" if cloud_shell else "FAIL",
        "Cloud Shell environment",
        "OCI Cloud Shell preauthenticated profile detected" if cloud_shell else "Cloud Shell preauthenticated OCI environment not detected",
        blocker=not cloud_shell,
    )

    # OCI Cloud Shell preauthentication check.
    if not shutil.which("oci"):
        report("FAIL", "OCI CLI", "oci is not on PATH", blocker=True)
        namespace = None
    else:
        ns_obj = json_command(["oci", "os", "ns", "get", "--output", "json"])
        namespace = field(ns_obj, "data") if isinstance(ns_obj, dict) else None
        if namespace:
            report("PASS", "OCI authentication", f"preauthenticated; namespace {namespace}")
        else:
            report("FAIL", "OCI authentication", "Cloud Shell OCI CLI call failed", blocker=True)

    # Confirm the OKE cluster and the active kubeconfig refer to the same API.
    cluster_obj = None
    if namespace:
        result = json_command(
            ["oci", "ce", "cluster", "get", "--cluster-id", CLUSTER_OCID, "--output", "json"]
        )
        cluster_obj = field(result, "data") if isinstance(result, dict) else None
    if not cluster_obj or field(cluster_obj, "name") != EXPECTED_CLUSTER:
        report("FAIL", "OKE cluster", "studyforge-oke was not readable through OCI", blocker=True)
        cluster_endpoint = None
    else:
        endpoints = field(cluster_obj, "endpoints", default={}) or {}
        cluster_endpoint = field(endpoints, "private-endpoint")
        report(
            "PASS" if field(cluster_obj, "lifecycle-state") == "ACTIVE" else "FAIL",
            "OKE cluster",
            f"{EXPECTED_CLUSTER} state={field(cluster_obj, 'lifecycle-state')} endpoint={cluster_endpoint}",
            blocker=field(cluster_obj, "lifecycle-state") != "ACTIVE",
        )

    kubeconfig = json_command(["kubectl", "config", "view", "--minify", "-o", "json"])
    current_context = None
    server = None
    if isinstance(kubeconfig, dict):
        current_context = field(kubeconfig, "current-context")
        clusters = kubeconfig.get("clusters") or []
        if clusters:
            server = field(field(clusters[0], "cluster", default={}) or {}, "server")
    if not current_context or not server:
        report("FAIL", "Kubernetes context", "no usable current kubeconfig context", blocker=True)
        kube_ok = False
    else:
        endpoint_url = f"https://{cluster_endpoint}" if cluster_endpoint else None
        same_cluster = server == endpoint_url
        report(
            "PASS" if same_cluster else "FAIL",
            "Kubernetes context",
            f"context={current_context}; endpoint match={same_cluster}",
            blocker=not same_cluster,
        )
        kube_ok = False
        if same_cluster:
            nodes = json_command(["kubectl", "get", "nodes", "-o", "json"], timeout=25)
            node_items = nodes.get("items") if isinstance(nodes, dict) else None
            if isinstance(node_items, list) and node_items:
                ready = sum(
                    any(c.get("type") == "Ready" and c.get("status") == "True" for c in (n.get("status", {}).get("conditions") or []))
                    for n in node_items
                )
                kube_ok = True
                report("PASS", "OKE connectivity", f"kubectl reached cluster; nodes Ready={ready}/{len(node_items)}")
            else:
                report("FAIL", "OKE connectivity", "kubectl could not list cluster nodes", blocker=True)

    namespace_obj = None
    secrets: dict[str, dict] = {}
    configmap: dict = {}
    if kube_ok:
        ns_obj = json_command(["kubectl", "get", "namespace", EXPECTED_NAMESPACE, "-o", "json"])
        if isinstance(ns_obj, dict) and field(ns_obj.get("metadata", {}), "name") == EXPECTED_NAMESPACE:
            namespace_obj = ns_obj
            report("PASS", "Namespace", f"{EXPECTED_NAMESPACE} exists")
        else:
            report("FAIL", "Namespace", f"{EXPECTED_NAMESPACE} is absent or unreadable", blocker=True)

    if namespace_obj:
        sec_obj = json_command(["kubectl", "get", "secrets", "-n", EXPECTED_NAMESPACE, "-o", "json"])
        cm_obj = json_command(["kubectl", "get", "configmap", "studyforge-processing-worker", "-n", EXPECTED_NAMESPACE, "-o", "json"])
        if isinstance(sec_obj, dict):
            for item in sec_obj.get("items", []):
                name = field(item.get("metadata", {}), "name")
                if name:
                    secrets[name] = item
            print("INFO Secret inventory (names only): " + (", ".join(sorted(secrets)) or "none"))
            # Inspect the existing pull Secret entirely in memory. Report only
            # type and registry hostnames, never the docker config or auth data.
            pull_secret = secrets.get("ocir-pull-secret")
            if pull_secret:
                secret_type = field(pull_secret, "type", default="")
                docker_config = b64_secret(pull_secret, ".dockerconfigjson")
                if not docker_config:
                    docker_config = b64_secret(pull_secret, ".dockercfg")
                try:
                    docker_obj = json.loads(docker_config) if docker_config else {}
                    auths = docker_obj.get("auths", docker_obj) if isinstance(docker_obj, dict) else {}
                    hosts = sorted(str(host) for host in auths if isinstance(host, str)) if isinstance(auths, dict) else []
                except (TypeError, json.JSONDecodeError):
                    hosts = []
                registry_match = any(host.rstrip("/").split("/")[0] == "phx.ocir.io" for host in hosts)
                reusable = secret_type == "kubernetes.io/dockerconfigjson" and registry_match
                report(
                    "PASS" if reusable else "FAIL",
                    "OCIR pull Secret reuse",
                    f"ocir-pull-secret type={secret_type or 'unknown'}; registry hosts="
                    f"{', '.join(hosts) or 'none'}; matching phx.ocir.io={registry_match}",
                    blocker=not reusable,
                )
            else:
                report("FAIL", "OCIR pull Secret reuse", "ocir-pull-secret is absent", blocker=True)
            worker_secret = secrets.get("studyforge-processing-secrets")
            keys = sorted(((worker_secret or {}).get("data") or {}).keys())
            print("INFO studyforge-processing-secrets keys (names only): " + (", ".join(keys) or "none"))
            missing = sorted(REQUIRED_SECRET_KEYS - set(keys))
            if missing:
                report("FAIL", "Worker Secret", "missing keys: " + ", ".join(missing), blocker=True)
            else:
                report("PASS", "Worker Secret", "all required keys present; values were not displayed")
        else:
            report("FAIL", "Kubernetes Secrets", "could not list Secret metadata", blocker=True)
            worker_secret = None
            missing = sorted(REQUIRED_SECRET_KEYS)

        if isinstance(cm_obj, dict):
            configmap = cm_obj.get("data") or {}
            report("PASS", "Worker ConfigMap", "existing configuration found")
        else:
            configmap = {}
            report("INFO", "Worker ConfigMap", "not present yet; checking prepared target values")

        # API health endpoint over HTTPS, pinned to the private VM IP.
        curl = shutil.which("curl")
        if curl:
            code, out = command([
                curl, "--silent", "--show-error", "--output", "/dev/null",
                "--write-out", "%{http_code}", "--connect-timeout", "5", "--max-time", "10",
                "--connect-to", f"{API_HOST}:443:{API_PRIVATE_IP}:443",
                f"https://{API_HOST}/api/v1/health/",
            ], timeout=12)
            http_status = out.strip() if code == 0 else "unreachable"
            passed = code == 0 and http_status == "200"
            report("PASS" if passed else "FAIL", "Private Django API", f"HTTPS health status={http_status}", blocker=not passed)
        else:
            report("FAIL", "Private Django API", "curl is unavailable", blocker=True)

        # Use the configured Redis URL from the Secret; only the result/host is shown.
        redis_secret = b64_secret(worker_secret, "PROCESSING_REDIS_URL") if worker_secret else None
        redis_url = redis_secret.decode("utf-8", "replace") if redis_secret else configmap.get("PROCESSING_REDIS_URL", "")
        if redis_url:
            redis_ok, detail = redis_ping(redis_url)
            report("PASS" if redis_ok else "FAIL", "Redis PING", detail, blocker=not redis_ok)
        else:
            report("FAIL", "Redis PING", "no Redis URL available in the worker Secret/configuration", blocker=True)

        # PostgreSQL TCP and read-only schema checks.
        db_values = {**PLANNED_DB, **configmap}
        db_host = db_values.get("PROCESSING_DB_HOST", API_PRIVATE_IP)
        try:
            db_port = int(db_values.get("PROCESSING_DB_PORT", "5432"))
        except ValueError:
            db_port = 5432
        try:
            with socket.create_connection((db_host, db_port), timeout=4):
                report("PASS", "PostgreSQL TCP", f"Cloud Shell can reach {db_host}:{db_port}; this does not prove OKE Pod reachability")
        except OSError:
            report("FAIL", "PostgreSQL TCP", f"{db_host}:{db_port} is unreachable from Cloud Shell; OKE Pod reachability remains untested", blocker=True)

        db_password = b64_secret(worker_secret, "PROCESSING_DB_PASSWORD") if worker_secret else None
        psql = shutil.which("psql")
        if not db_password:
            report("FAIL", "Processing DB/schema", "authorized PROCESSING_DB_PASSWORD is unavailable in the namespace Secret", blocker=True)
        elif not psql:
            report("FAIL", "Processing DB/schema", "psql is unavailable in Cloud Shell", blocker=True)
        else:
            env = os.environ.copy()
            env.update({
                "PGPASSWORD": db_password.decode("utf-8", "replace"),
                "PGCONNECT_TIMEOUT": "5",
            })
            sql = (
                "BEGIN READ ONLY; "
                "SELECT current_database(); "
                "SELECT to_regclass('public.executions_execution') IS NOT NULL; "
                "SELECT EXISTS (SELECT 1 FROM django_migrations "
                f"WHERE app='executions' AND name='{EXPECTED_MIGRATION}'); "
                "ROLLBACK;"
            )
            try:
                result = subprocess.run(
                    [psql, "-X", "-w", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                     "-h", db_host, "-p", str(db_port), "-U", db_values["PROCESSING_DB_USER"],
                     "-d", db_values["PROCESSING_DB_NAME"], "-c", sql],
                    check=False, capture_output=True, text=True, timeout=12, env=env,
                )
                rows = [row.strip() for row in result.stdout.splitlines() if row.strip()]
                db_ok = (
                    result.returncode == 0
                    and len(rows) >= 3
                    and rows[0] == db_values["PROCESSING_DB_NAME"]
                    and rows[1:] == ["t", "t"]
                )
                detail = "processing database, Execution table, and expected migration exist" if db_ok else "database/schema check failed; diagnostic details suppressed"
                report("PASS" if db_ok else "FAIL", "Processing DB/schema", detail, blocker=not db_ok)
            except (OSError, subprocess.TimeoutExpired):
                report("FAIL", "Processing DB/schema", "read-only psql check could not run", blocker=True)

    # Vault inventory is names/metadata only. Secret values are never requested.
    vault_obj = json_command([
        "oci", "vault", "secret", "list", "--compartment-id", TENANCY_OCID,
        "--all", "--output", "json",
    ]) if namespace else None
    if isinstance(vault_obj, dict):
        vault_items = vault_obj.get("data", [])
        names = sorted({field(item, "secret-name", default="") for item in vault_items if field(item, "secret-name")})
        candidates = [name for name in names if any(word in name.lower() for word in ("processing", "redis", "gemini", "celery"))]
        report("PASS" if candidates else "INFO", "OCI Vault source", ", ".join(candidates) if candidates else "no processing-related Vault secret names listed; values were not queried")
    else:
        report("INFO", "OCI Vault source", "Vault list unavailable; values were not queried")

    # OCIR repository/image inventory; no image is pushed or pulled.
    repos = json_command([
        "oci", "artifacts", "container", "repository", "list",
        "--compartment-id", TENANCY_OCID, "--compartment-id-in-subtree", "true",
        "--all", "--output", "json",
    ]) if namespace else None
    repo_items = repos.get("data", []) if isinstance(repos, dict) else []
    target = next((item for item in repo_items if field(item, "display-name") == EXPECTED_REPOSITORY), None)
    if target:
        report("PASS", "OCIR repository", "target repository is visible")
        images = json_command([
            "oci", "artifacts", "container", "image", "list",
            "--compartment-id", TENANCY_OCID, "--compartment-id-in-subtree", "true",
            "--repository-id", field(target, "id"), "--all", "--output", "json",
        ])
        image_items = images.get("data", []) if isinstance(images, dict) else []
        labels = [str(field(item, "display-name", "version", default="")) for item in image_items]
        tag_found = any(EXPECTED_IMAGE_TAG in label for label in labels)
        report("PASS" if tag_found else "FAIL", "OCIR image", "expected ARM64 commit tag visible" if tag_found else "expected commit tag is not published", blocker=not tag_found)
    elif repos is None:
        report("FAIL", "OCIR repository", "repository inventory could not be read", blocker=True)
    else:
        report("FAIL", "OCIR repository", f"{EXPECTED_REPOSITORY} is absent or not visible", blocker=True)

    passed = sum(status == "PASS" for status, _, _ in checks)
    failed = sum(status == "FAIL" for status, _, _ in checks)
    print(f"\nSUMMARY: PASS={passed} FAIL={failed}")
    if blockers:
        print("REMAINING BLOCKERS:")
        for item in blockers:
            print(f"- {item}")
    else:
        print("REMAINING BLOCKERS: none found by this read-only preflight")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(
        "Legacy Cloud Shell preflight is retired. "
        "Use docs/deployment/scrum-122-oke-worker.md for current validation."
    )
