"""Opt-in real S3 HTTP and cross-process verification using disposable SeaweedFS."""

import hashlib
import os
from pathlib import Path
from secrets import token_urlsafe
import socket
import subprocess
import sys
import time
from uuid import uuid4

import boto3
from botocore.config import Config
import pytest
from django.test import override_settings

from apps.documents.models import Document


BUCKET = "studyforge-scrum127-integration"
ACCESS_KEY = f"test{uuid4().hex[:20]}"
SECRET_KEY = token_urlsafe(32)
SERVICE_TOKEN = token_urlsafe(32)
SERVICE_DIR = Path(__file__).resolve().parents[3] / "services" / "document-processing"
WORKER_CODE = """
import hashlib
import sys
import django
django.setup()
from processing_service.source_client import fetch_source_document
try:
    source = fetch_source_document(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
except Exception as exc:
    print(type(exc).__name__)
    raise SystemExit(2)
print(hashlib.sha256(source.content).hexdigest())
"""


def docker(*args, check=True):
    return subprocess.run(["docker", *args], check=check, text=True, capture_output=True, timeout=90)


@pytest.fixture
def isolated_object_store():
    if os.environ.get("SCRUM127_S3_INTEGRATION") != "1":
        pytest.skip("Set SCRUM127_S3_INTEGRATION=1 to run the Docker S3 integration test")

    suffix = uuid4().hex[:12]
    container = f"studyforge-scrum127-s3-{suffix}"
    volume = f"studyforge-scrum127-s3-{suffix}"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        host_port = listener.getsockname()[1]
    started = False
    try:
        docker(
            "run", "--detach", "--name", container,
            "--publish", f"127.0.0.1:{host_port}:8333",
            "--mount", f"type=volume,source={volume},target=/data",
            "--env", f"AWS_ACCESS_KEY_ID={ACCESS_KEY}",
            "--env", f"AWS_SECRET_ACCESS_KEY={SECRET_KEY}",
            "--env", f"S3_BUCKET={BUCKET}",
            "chrislusf/seaweedfs:latest",
        )
        started = True
        port = docker("port", container, "8333/tcp").stdout.strip().rsplit(":", 1)[1]
        endpoint = f"http://127.0.0.1:{port}"
        client = boto3.client(
            "s3", endpoint_url=endpoint, region_name="us-east-1",
            aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
            config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 1}, s3={"addressing_style": "path"}),
        )
        for attempt in range(30):
            try:
                client.head_bucket(Bucket=BUCKET)
                break
            except Exception:
                if attempt == 29:
                    raise
                time.sleep(1)
        yield container, endpoint, client
    finally:
        if started:
            docker("stop", container, check=False)
            docker("rm", container, check=False)
        docker("volume", "rm", volume, check=False)


def worker_fetch(endpoint, django_url, job, document, digest, *, token=SERVICE_TOKEN, access_key=ACCESS_KEY, secret_key=SECRET_KEY):
    environment = os.environ.copy()
    environment.update(
        DJANGO_SETTINGS_MODULE="processing_service.settings",
        PROCESSING_SECRET_KEY=token_urlsafe(32),
        PROCESSING_DB_PASSWORD=token_urlsafe(32),
        PROCESSING_DJANGO_API_URL=django_url,
        PROCESSING_SERVICE_TOKEN=token,
        PROCESSING_SOURCE_MODE="s3",
        PROCESSING_STORAGE_BUCKET=BUCKET,
        PROCESSING_STORAGE_REGION="us-east-1",
        PROCESSING_STORAGE_ENDPOINT_URL=endpoint,
        PROCESSING_STORAGE_ACCESS_KEY_ID=access_key,
        PROCESSING_STORAGE_SECRET_ACCESS_KEY=secret_key,
        PROCESSING_STORAGE_ALLOW_HTTP="1",
        PROCESSING_STORAGE_CONNECT_TIMEOUT="2",
        PROCESSING_STORAGE_READ_TIMEOUT="3",
    )
    return subprocess.run(
        [sys.executable, "-c", WORKER_CODE, str(job), str(document), digest],
        cwd=SERVICE_DIR, env=environment, text=True, capture_output=True, timeout=35,
    )


@pytest.mark.django_db(transaction=True)
def test_cross_process_upload_auth_outage_and_storage_restart(
    isolated_object_store, live_server, upload, media_root, pdf_factory, settings,
):
    container, endpoint, client = isolated_object_store
    storages = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": BUCKET, "region_name": "us-east-1", "endpoint_url": endpoint,
                "access_key": ACCESS_KEY, "secret_key": SECRET_KEY,
                "default_acl": None, "querystring_auth": True, "file_overwrite": False,
                "client_config": Config(s3={"addressing_style": "path"}),
            },
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    with override_settings(DOCUMENT_STORAGE_BACKEND="s3", STORAGES=storages, PROCESSING_SERVICE_TOKEN=SERVICE_TOKEN):
        response = upload()
        assert response.status_code == 201, response.content
        document = Document.objects.get(pk=response.json()["id"])
        job = document.jobs.get()
        key, digest = document.file.name, document.sha256
        assert key.startswith("documents/")
        assert client.get_object(Bucket=BUCKET, Key=key)["Body"].read() == pdf_factory()
        assert not list(media_root.rglob("*.pdf"))

        success = worker_fetch(endpoint, live_server.url, job.pk, document.pk, digest)
        assert success.returncode == 0, success.stdout + success.stderr
        assert success.stdout.strip() == digest

        missing = worker_fetch(endpoint, live_server.url, job.pk, document.pk, digest, token="")
        assert missing.returncode == 2 and missing.stdout.strip() == "PermanentProcessingError"
        invalid = worker_fetch(endpoint, live_server.url, job.pk, document.pk, digest, token=token_urlsafe(32))
        assert invalid.returncode == 2 and invalid.stdout.strip() == "PermanentProcessingError"
        wrong_secret = token_urlsafe(32)
        denied = worker_fetch(endpoint, live_server.url, job.pk, document.pk, digest, secret_key=wrong_secret)
        assert denied.returncode == 2 and denied.stdout.strip() == "RetryableProcessingError"
        denied_storages = {
            **storages,
            "default": {
                **storages["default"],
                "OPTIONS": {**storages["default"]["OPTIONS"], "secret_key": wrong_secret},
            },
        }
        with override_settings(STORAGES=denied_storages):
            denied_upload = upload()
        assert denied_upload.status_code == 503
        assert denied_upload.json()["code"] == "UPLOAD_UNAVAILABLE"
        assert Document.objects.count() == 1

        docker("stop", container)
        outage = worker_fetch(endpoint, live_server.url, job.pk, document.pk, digest)
        assert outage.returncode == 2 and outage.stdout.strip() == "RetryableProcessingError"
        docker("start", container)
        for attempt in range(30):
            try:
                client.head_bucket(Bucket=BUCKET)
                break
            except Exception:
                if attempt == 29:
                    raise
                time.sleep(1)

        reloaded = Document.objects.get(pk=document.pk)
        assert reloaded.file.name == key
        assert client.get_object(Bucket=BUCKET, Key=key)["Body"].read() == pdf_factory()
        recovered = worker_fetch(endpoint, live_server.url, job.pk, document.pk, digest)
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr
        assert recovered.stdout.strip() == hashlib.sha256(pdf_factory()).hexdigest()

        client.delete_object(Bucket=BUCKET, Key=key)
        missing_object = worker_fetch(endpoint, live_server.url, job.pk, document.pk, digest)
        assert missing_object.returncode == 2 and missing_object.stdout.strip() == "RetryableProcessingError"
