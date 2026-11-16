"""Mocked S3 proves persistent keys and direct standalone worker retrieval."""

import boto3
import hashlib
import pytest
from django.core.management import call_command
from django.test import override_settings
from moto import mock_aws

from apps.documents.models import Document
from tests.documents.test_worker_integration import worker_bridge


BUCKET = "studyforge-isolated-test-documents"
S3_STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": BUCKET,
            "region_name": "us-east-1",
            "access_key": "disposable-test-key",
            "secret_key": "disposable-test-secret",
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@pytest.fixture
def isolated_s3():
    with mock_aws():
        client = boto3.client(
            "s3", region_name="us-east-1", aws_access_key_id="disposable-test-key",
            aws_secret_access_key="disposable-test-secret",
        )
        client.create_bucket(Bucket=BUCKET)
        with override_settings(DOCUMENT_STORAGE_BACKEND="s3", STORAGES=S3_STORAGES):
            yield client


@pytest.mark.django_db(transaction=True)
def test_upload_uses_object_storage_and_key_survives_model_reload(isolated_s3, upload, media_root, pdf_factory):
    response = upload()
    assert response.status_code == 201, response.content
    document = Document.objects.get(pk=response.json()["id"])
    key = document.file.name
    assert key.startswith("documents/") and key.endswith(".pdf")
    assert isolated_s3.get_object(Bucket=BUCKET, Key=key)["Body"].read() == pdf_factory()
    assert not list(media_root.rglob("*.pdf"))
    reloaded = Document.objects.get(pk=document.pk)
    assert reloaded.file.name == key
    with reloaded.file.open("rb") as source:
        assert source.read() == pdf_factory()
    assert "file" not in response.json() and "object_key" not in response.json()


@pytest.mark.django_db(transaction=True)
def test_worker_processes_from_object_store_without_shared_media(
    isolated_s3, upload, media_root, worker_bridge, monkeypatch, settings,
):
    from processing_service import source_client

    settings.PROCESSING_SOURCE_MODE = "s3"
    settings.PROCESSING_STORAGE_BUCKET = BUCKET
    monkeypatch.setattr(source_client, "object_client", lambda: isolated_s3)
    response = upload()
    assert response.status_code == 201, response.content
    document = Document.objects.get(pk=response.json()["id"])
    job = document.jobs.get()
    assert not list(media_root.rglob("*.pdf"))
    result = worker_bridge.task.run(job.pk, document.pk, document.sha256)
    document.refresh_from_db()
    assert result["status"] == "SUCCEEDED"
    assert document.status == Document.Status.READY


@pytest.mark.django_db(transaction=True)
def test_legacy_copy_preserves_database_key(isolated_s3, media_root, owner, course, pdf_factory):
    content = pdf_factory()
    key = "documents/2026/11/legacy.pdf"
    path = media_root / key
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    document = Document.objects.create(
        owner=owner, course=course, title="legacy.pdf",
        sha256=hashlib.sha256(content).hexdigest(), file=key,
    )
    call_command("copy_document_sources", source_media_root=str(media_root))
    assert isolated_s3.list_objects_v2(Bucket=BUCKET).get("KeyCount") == 0
    call_command("copy_document_sources", source_media_root=str(media_root), apply=True)
    assert isolated_s3.get_object(Bucket=BUCKET, Key=key)["Body"].read() == content
    document.refresh_from_db()
    assert document.file.name == key
    call_command("copy_document_sources", source_media_root=str(media_root))
