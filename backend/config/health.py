"""Backend liveness and bounded dependency readiness probes."""

from django.conf import settings
from django.db import connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from redis import Redis


def _response(status, dependencies=None):
    body = {"status": status}
    if dependencies is not None:
        body["dependencies"] = dependencies
    result = JsonResponse(body, status=200 if status == "ok" else 503)
    result["Cache-Control"] = "no-store"
    return result


@require_GET
def live(_request):
    return _response("ok")


@require_GET
def ready(_request):
    dependencies = {"database": "ok", "redis": "ok", "storage": "ok", "service_auth": "ok"}
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        dependencies["database"] = "unavailable"
    try:
        with Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2) as client:
            client.ping()
    except Exception:
        dependencies["redis"] = "unavailable"
    if settings.DOCUMENT_STORAGE_BACKEND == "s3":
        try:
            from django.core.files.storage import default_storage

            default_storage.bucket.meta.client.head_bucket(Bucket=settings.STORAGES["default"]["OPTIONS"]["bucket_name"])
        except Exception:
            dependencies["storage"] = "unavailable"
    if not settings.PROCESSING_SERVICE_TOKEN:
        dependencies["service_auth"] = "unavailable"
    return _response("ok" if all(value == "ok" for value in dependencies.values()) else "unavailable", dependencies)
