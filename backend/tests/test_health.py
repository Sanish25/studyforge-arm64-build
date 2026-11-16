"""Backend liveness and readiness keep dependency details private."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


class BackendHealthTests(SimpleTestCase):
    def test_liveness_does_not_query_dependencies(self):
        with patch("config.health.connections") as database, patch("config.health.Redis.from_url") as redis:
            response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        database.assert_not_called()
        redis.assert_not_called()

    @override_settings(CELERY_BROKER_URL="redis://test.invalid/0", PROCESSING_SERVICE_TOKEN="test-token", DOCUMENT_STORAGE_BACKEND="filesystem")
    def test_readiness_checks_database_and_redis(self):
        with patch("config.health.connections") as database, patch("config.health.Redis.from_url") as redis:
            response = self.client.get("/api/v1/ready/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dependencies"], {"database": "ok", "redis": "ok", "storage": "ok", "service_auth": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")
        database.__getitem__.return_value.cursor.assert_called_once()
        redis.return_value.__enter__.return_value.ping.assert_called_once()

    @override_settings(CELERY_BROKER_URL="redis://test.invalid/0", PROCESSING_SERVICE_TOKEN="", DOCUMENT_STORAGE_BACKEND="filesystem")
    def test_missing_token_and_outage_are_unready_without_details(self):
        with patch("config.health.connections") as database, patch("config.health.Redis.from_url") as redis:
            database.__getitem__.return_value.cursor.side_effect = OSError("private database detail")
            redis.side_effect = OSError("private redis detail")
            response = self.client.get("/api/v1/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["dependencies"], {
            "database": "unavailable", "redis": "unavailable", "storage": "ok", "service_auth": "unavailable",
        })
        self.assertNotIn("private", response.content.decode())

    @override_settings(
        CELERY_BROKER_URL="redis://test.invalid/0", PROCESSING_SERVICE_TOKEN="test-token",
        DOCUMENT_STORAGE_BACKEND="s3",
        STORAGES={"default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {"bucket_name": "test-bucket"}}},
    )
    def test_storage_outage_is_unready_without_details(self):
        with patch("config.health.connections"), patch("config.health.Redis.from_url"), patch(
            "django.core.files.storage.default_storage"
        ) as storage:
            storage.bucket.meta.client.head_bucket.side_effect = OSError("private storage detail")
            response = self.client.get("/api/v1/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["dependencies"]["storage"], "unavailable")
        self.assertNotIn("private storage detail", response.content.decode())
