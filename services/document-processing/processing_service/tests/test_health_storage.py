"""Readiness checks direct object storage only when workers use it."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


@override_settings(PROCESSING_SOURCE_MODE="s3", PROCESSING_STORAGE_BUCKET="test-private-bucket")
class StorageHealthTests(SimpleTestCase):
    @override_settings(PROCESSING_SOURCE_MODE="django")
    def test_django_source_mode_does_not_probe_storage(self):
        with patch("processing_service.health.Execution.objects.exists"), patch(
            "processing_service.health.Redis.from_url"
        ), patch("processing_service.health.object_client") as storage:
            response = self.client.get("/ready/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dependencies"], {"database": "ok", "redis": "ok"})
        storage.assert_not_called()

    def test_ready_s3_bucket_is_reported(self):
        with patch("processing_service.health.Execution.objects.exists"), patch(
            "processing_service.health.Redis.from_url"
        ), patch("processing_service.health.object_client") as storage:
            response = self.client.get("/ready/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dependencies"], {
            "database": "ok", "redis": "ok", "storage": "ok",
        })
        storage.return_value.head_bucket.assert_called_once_with(Bucket="test-private-bucket")

    def test_storage_outage_is_unready_without_leaking_details(self):
        with patch("processing_service.health.Execution.objects.exists"), patch(
            "processing_service.health.Redis.from_url"
        ), patch(
            "processing_service.health.object_client", side_effect=OSError("private storage detail")
        ):
            response = self.client.get("/ready/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["dependencies"]["storage"], "unavailable")
        self.assertNotContains(response, "private storage detail", status_code=503)
