"""Scrum-109 regression checks for KEDA and worker recovery.

Run configuration checks with:

    backend/venv/bin/python -m pytest services/document-processing/tests/test_scrum109_validation.py

Run live kind/Redis checks with:

    SCRUM109_LIVE=1 backend/venv/bin/python -m pytest services/document-processing/tests/test_scrum109_validation.py -s

The live checks use synthetic Redis list entries only for measuring KEDA. They
clear that list before and after the scale test.
"""

import os
from pathlib import Path
import subprocess
import time

import pytest


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "services" / "document-processing" / "keda-worker-scaledobject.yaml"
LIVE = os.environ.get("SCRUM109_LIVE") == "1"
KUBECONFIG = os.environ.get("KUBECONFIG", "/tmp/studyforge-kubeconfig")
REDIS_CONTAINER = os.environ.get("SCRUM109_REDIS_CONTAINER", "studyforge-redis-1")


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True).stdout.strip()


def kubectl(*args, check=True):
    return run("kubectl", "--kubeconfig", KUBECONFIG, *args, check=check)


def redis(*args):
    return run("docker", "exec", REDIS_CONTAINER, "redis-cli", "-n", "0", *args)


def wait_for(predicate, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(5)
    raise AssertionError("Timed out waiting for Scrum-109 live state")


def test_scaler_manifest_has_expected_policy():
    manifest = MANIFEST.read_text(encoding="utf-8")
    for expected in (
        "name: processing-worker-scaler",
        "name: processing-worker",
        "listName: document-processing",
        'listLength: "5"',
        "minReplicaCount: 2",
        "maxReplicaCount: 10",
        "pollingInterval: 15",
        "stabilizationWindowSeconds: 150",
    ):
        assert expected in manifest


@pytest.mark.skipif(not LIVE, reason="set SCRUM109_LIVE=1 for kind/Redis checks")
def test_keda_is_ready_and_worker_hpa_exists():
    scaled = kubectl("get", "scaledobject", "processing-worker-scaler", "-o", "jsonpath={.status.conditions}")
    hpa = kubectl("get", "hpa", "keda-hpa-processing-worker-scaler", "-o", "jsonpath={.spec.minReplicas}:{.spec.maxReplicas}")
    assert '"type":"Ready"' in scaled and '"status":"True"' in scaled
    assert hpa == "2:10"


@pytest.mark.skipif(not LIVE, reason="set SCRUM109_LIVE=1 for kind/Redis checks")
def test_fifteen_queued_items_scale_to_three_and_return_to_two():
    test_list = "scrum109-keda-test"
    redis("DEL", test_list)
    kubectl(
        "patch", "scaledobject", "processing-worker-scaler", "--type=merge",
        "-p", '{"spec":{"triggers":[{"type":"redis","metadata":{"address":"host.docker.internal:6379","databaseIndex":"0","listName":"scrum109-keda-test","listLength":"5","activationListLength":"1"}}]}}',
    )
    try:
        redis("RPUSH", test_list, *[f"scrum109-test-{i}" for i in range(15)])
        wait_for(lambda: kubectl("get", "deployment", "processing-worker", "-o", "jsonpath={.spec.replicas}") == "3")
        redis("DEL", test_list)
        wait_for(lambda: kubectl("get", "deployment", "processing-worker", "-o", "jsonpath={.spec.replicas}") == "2", timeout=210)
    finally:
        redis("DEL", test_list)
        kubectl("apply", "-f", str(MANIFEST))


@pytest.mark.skipif(not LIVE, reason="set SCRUM109_LIVE=1 for kind/Redis checks")
def test_failed_worker_pod_is_replaced():
    before = kubectl("get", "pods", "-l", "app=processing-worker", "-o", "jsonpath={.items[*].metadata.name}").split()
    assert len(before) == 2
    kubectl("delete", "pod", before[0])
    wait_for(lambda: len(kubectl("get", "pods", "-l", "app=processing-worker", "-o", "jsonpath={.items[*].status.containerStatuses[*].ready}").split()) >= 2)
    after = kubectl("get", "pods", "-l", "app=processing-worker", "-o", "jsonpath={.items[*].metadata.name}").split()
    assert len(after) == 2
    assert before[0] not in after
