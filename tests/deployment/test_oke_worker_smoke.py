"""Read-only smoke checks for the deployed SCRUM-122 worker on OKE.

Run with:

    SCRUM122_KUBE_CONTEXT=context-studyforge-oke-cmidganrxna \
    KUBECONFIG=~/.kube/studyforge-oke-bastion \
    backend/venv/bin/python -m pytest tests/deployment/test_oke_worker_smoke.py -v

The checks inspect Kubernetes state and, when a ready worker is present, call
its read-only dependency readiness check. They never publish or consume tasks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest


NAMESPACE = "studyforge"
DEPLOYMENT = "processing-worker"
SELECTOR = "app.kubernetes.io/name=processing-worker"
EXPECTED_IMAGE = os.environ.get(
    "SCRUM122_EXPECTED_WORKER_IMAGE",
    "phx.ocir.io/axcyydnoof5f/studyforge/document-processing@sha256:"
    "c07d7b5d5fd4b089f65617733e100f0f062cd76122fe10366c3496b0f14858f6",
)
EXPECTED_REPLICAS = int(os.environ.get("SCRUM122_EXPECTED_WORKER_REPLICAS", "1"))
OKE_CONTEXT = "context-studyforge-oke-cmidganrxna"


def _kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", "--context", OKE_CONTEXT, *args],
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )


def _json_result(*args: str, missing_is_failure: bool = False) -> dict:
    result = _kubectl(*args, "-o", "json", "--request-timeout=10s")
    if result.returncode:
        if missing_is_failure and "NotFound" in result.stderr:
            pytest.fail(f"Required Kubernetes resource is missing: {' '.join(args)}")
        pytest.skip(
            "OKE Kubernetes API is unavailable or this identity cannot read the "
            "required resources; no live health claim can be made."
        )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def cluster_snapshot() -> dict:
    if os.environ.get("SCRUM122_KUBE_CONTEXT") != OKE_CONTEXT:
        pytest.skip("Set SCRUM122_KUBE_CONTEXT to the dedicated OKE context to enable live checks.")
    if not shutil.which("kubectl"):
        pytest.skip("kubectl is not installed; OKE smoke checks require live API access.")

    context = _kubectl("config", "get-contexts", "-o", "name")
    if context.returncode or OKE_CONTEXT not in context.stdout.splitlines():
        pytest.skip("The dedicated OKE context is absent from the configured kubeconfig.")

    # Listing nodes confirms API access before workload-specific assertions.
    nodes = _json_result("get", "nodes")
    deployment = _json_result(
        "get", "deployment", DEPLOYMENT, "-n", NAMESPACE, missing_is_failure=True
    )
    pods = _json_result("get", "pods", "-n", NAMESPACE, "-l", SELECTOR)
    return {"nodes": nodes, "deployment": deployment, "pods": pods}


def _ready(node: dict) -> bool:
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in node.get("status", {}).get("conditions", [])
    )


def test_worker_deployment_exists_in_studyforge(cluster_snapshot: dict) -> None:
    deployment = cluster_snapshot["deployment"]
    assert deployment.get("metadata", {}).get("namespace") == NAMESPACE
    assert deployment.get("metadata", {}).get("name") == DEPLOYMENT


def test_deployment_uses_expected_immutable_arm64_image(cluster_snapshot: dict) -> None:
    containers = cluster_snapshot["deployment"].get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    worker = next((item for item in containers if item.get("name") == "processing-worker"), None)
    assert worker is not None, "processing-worker container is absent from the Deployment"
    assert worker.get("image") == EXPECTED_IMAGE, "Deployment image differs from the expected digest"
    assert "@sha256:" in EXPECTED_IMAGE, "Expected worker image must be pinned by digest"
    assert cluster_snapshot["deployment"]["spec"]["template"]["spec"].get("nodeSelector", {}).get(
        "kubernetes.io/arch"
    ) == "arm64"


def test_worker_pod_is_scheduled_on_ready_arm64_node(cluster_snapshot: dict) -> None:
    pods = cluster_snapshot["pods"].get("items", [])
    assert pods, "No processing-worker Pods are present"
    nodes = {node["metadata"]["name"]: node for node in cluster_snapshot["nodes"].get("items", [])}
    scheduled = [pod for pod in pods if pod.get("spec", {}).get("nodeName")]
    assert scheduled, "No processing-worker Pod has been scheduled"
    assert any(
        (node := nodes.get(pod["spec"]["nodeName"]))
        and node.get("metadata", {}).get("labels", {}).get("kubernetes.io/arch") == "arm64"
        and _ready(node)
        for pod in scheduled
    ), "No worker Pod is scheduled on a Ready ARM64 node"


def test_deployment_has_expected_ready_replicas(cluster_snapshot: dict) -> None:
    deployment = cluster_snapshot["deployment"]
    spec_replicas = deployment.get("spec", {}).get("replicas", 1)
    status = deployment.get("status", {})
    assert spec_replicas == EXPECTED_REPLICAS
    assert status.get("readyReplicas", 0) == EXPECTED_REPLICAS
    assert status.get("availableReplicas", 0) == EXPECTED_REPLICAS


def test_worker_container_is_running_without_crash_loop(cluster_snapshot: dict) -> None:
    pods = cluster_snapshot["pods"].get("items", [])
    assert pods, "No processing-worker Pods are present"
    worker_containers = [
        status
        for pod in pods
        for status in pod.get("status", {}).get("containerStatuses", [])
        if status.get("name") == "processing-worker"
    ]
    assert worker_containers, "No processing-worker container status is available"
    for container in worker_containers:
        waiting = container.get("state", {}).get("waiting", {})
        assert waiting.get("reason") != "CrashLoopBackOff", "Worker container is in CrashLoopBackOff"
        assert container.get("state", {}).get("running") is not None, "Worker container is not running"


def test_worker_readiness_and_health_checks_pass(cluster_snapshot: dict) -> None:
    pods = cluster_snapshot["pods"].get("items", [])
    assert pods, "No processing-worker Pods are present"
    ready_pods = [
        pod
        for pod in pods
        if any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in pod.get("status", {}).get("conditions", [])
        )
    ]
    assert ready_pods, "No worker Pod is Ready; its Kubernetes readiness checks have not passed"
    assert any(
        status.get("name") == "processing-worker" and status.get("ready") is True
        for pod in ready_pods
        for status in pod.get("status", {}).get("containerStatuses", [])
    ), "Kubernetes does not report the worker container as ready"


def test_worker_postgres_redis_and_storage_readiness(cluster_snapshot: dict) -> None:
    """Ask the live worker's existing read-only probe; never print credentials."""
    pods = cluster_snapshot["pods"].get("items", [])
    ready_pod = next(
        (
            pod
            for pod in pods
            if any(
                condition.get("type") == "Ready" and condition.get("status") == "True"
                for condition in pod.get("status", {}).get("conditions", [])
            )
        ),
        None,
    )
    if ready_pod is None:
        pytest.skip("No Ready worker Pod is available to safely check PostgreSQL/Redis readiness.")

    script = (
        "import django; django.setup(); "
        "from django.test import RequestFactory; "
        "from processing_service.health import ready; "
        "r=ready(RequestFactory().get('/ready/')); "
        "print(r.content.decode()); "
        "raise SystemExit(0 if r.status_code == 200 else 1)"
    )
    result = _kubectl(
        "exec", "-n", NAMESPACE, ready_pod["metadata"]["name"], "-c", "processing-worker",
        "--", "python", "-c", script,
    )
    assert result.returncode == 0, "Worker read-only dependency readiness check failed"
    health = json.loads(result.stdout.strip().splitlines()[-1])
    dependencies = health.get("dependencies", {})
    assert health.get("status") == "ok"
    assert dependencies.get("database") == "ok", "Worker PostgreSQL readiness check failed"
    assert dependencies.get("redis") == "ok", "Worker Redis readiness check failed"
    if "storage" in dependencies:
        assert dependencies["storage"] == "ok", "Worker Object Storage readiness check failed"
