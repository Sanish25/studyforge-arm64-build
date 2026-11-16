"""Production object retrieval preserves job correlation without shared files."""

from email.message import Message
from io import BytesIO
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.test import SimpleTestCase, override_settings

from processing_service.errors import PermanentProcessingError, RetryableProcessingError
from processing_service.source_client import fetch_source_document


BODY = b"%PDF-1.4\nprivate test source"
DIGEST = hashlib.sha256(BODY).hexdigest()
KEY = "documents/2026/11/stable.pdf"


@override_settings(
    PROCESSING_SOURCE_MODE="s3", PROCESSING_STORAGE_BUCKET="test-private-bucket",
    PROCESSING_DJANGO_API_URL="https://api.example.test", PROCESSING_SERVICE_TOKEN="test-token",
)
class ObjectSourceTests(SimpleTestCase):
    def locator(self, **changes):
        data = {"document_id": 42, "source_sha256": DIGEST, "object_key": KEY, "mime_type": "application/pdf"}
        data.update(changes)
        response = BytesIO(json.dumps(data).encode())
        response.status = 200
        response.headers = Message()
        return response

    def test_worker_reads_stable_key_after_new_client_instance(self):
        calls = []
        def open_locator(request, **kwargs):
            calls.append(request)
            return self.locator()
        s3 = MagicMock()
        s3.get_object.side_effect = lambda **kwargs: {"Body": BytesIO(BODY)}
        with patch("processing_service.source_client.build_opener", return_value=SimpleNamespace(open=open_locator)), patch(
            "processing_service.source_client.object_client", return_value=s3
        ):
            first = fetch_source_document(19, 42, DIGEST)
            second = fetch_source_document(19, 42, DIGEST)
        self.assertEqual(first.content, BODY)
        self.assertEqual(second.content, BODY)
        self.assertEqual(s3.get_object.call_count, 2)
        self.assertEqual(s3.get_object.call_args.kwargs, {"Bucket": "test-private-bucket", "Key": KEY})
        self.assertEqual(calls[0].get_header("Authorization"), "Bearer test-token")
        self.assertTrue(calls[0].full_url.endswith("/internal/v1/jobs/19/object/"))

    def test_rejects_mismatched_locator_before_storage_access(self):
        s3 = MagicMock()
        with patch("processing_service.source_client.build_opener", return_value=SimpleNamespace(open=lambda *a, **k: self.locator(document_id=99))), patch(
            "processing_service.source_client.object_client", return_value=s3
        ):
            with self.assertRaises(PermanentProcessingError):
                fetch_source_document(19, 42, DIGEST)
        s3.assert_not_called()

    def test_missing_object_or_permission_failure_is_retryable_without_details(self):
        for code in ("NoSuchKey", "AccessDenied"):
            with self.subTest(code=code):
                s3 = MagicMock()
                s3.get_object.side_effect = ClientError({"Error": {"Code": code, "Message": "private detail"}}, "GetObject")
                with patch("processing_service.source_client.build_opener", return_value=SimpleNamespace(open=lambda *a, **k: self.locator())), patch(
                    "processing_service.source_client.object_client", return_value=s3
                ):
                    with self.assertRaisesRegex(RetryableProcessingError, "Could not retrieve the source object") as error:
                        fetch_source_document(19, 42, DIGEST)
                self.assertNotIn("private detail", str(error.exception))

    def test_corrupted_object_is_rejected(self):
        s3 = MagicMock()
        s3.get_object.return_value = {"Body": BytesIO(b"wrong")}
        with patch("processing_service.source_client.build_opener", return_value=SimpleNamespace(open=lambda *a, **k: self.locator())), patch(
            "processing_service.source_client.object_client", return_value=s3
        ):
            with self.assertRaises(PermanentProcessingError):
                fetch_source_document(19, 42, DIGEST)
