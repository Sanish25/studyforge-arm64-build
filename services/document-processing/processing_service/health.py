"""Infrastructure probes only; no document or job API is exposed."""

from django.conf import settings
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from redis import Redis
from redis.exceptions import RedisError

from executions.models import Execution
from .object_storage import client as object_client


def response(body, status=200):
    result = JsonResponse(body, status=status)
    result["Cache-Control"] = "no-store"
    return result


@require_GET
def live(_request):
    return response({"status": "ok", "service": "document-processing"})


@require_GET
def ready(_request):
    dependencies = {"database": "ok", "redis": "ok"}
    try:
        # Also verifies that the execution table is migrated and accessible.
        Execution.objects.exists()
    except DatabaseError:
        dependencies["database"] = "unavailable"
    try:
        with Redis.from_url(
            settings.PROCESSING_REDIS_URL, socket_connect_timeout=2, socket_timeout=2
        ) as client:
            client.ping()
    except (RedisError, ValueError):
        dependencies["redis"] = "unavailable"
    if settings.PROCESSING_SOURCE_MODE == "s3":
        dependencies["storage"] = "ok"
        try:
            object_client().head_bucket(Bucket=settings.PROCESSING_STORAGE_BUCKET)
        except Exception:
            dependencies["storage"] = "unavailable"
    healthy = all(value == "ok" for value in dependencies.values())
    return response(
        {"status": "ok" if healthy else "unavailable", "dependencies": dependencies},
        status=200 if healthy else 503,
    )
