"""Standalone configuration: never load main-application settings or models."""

import os
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ImproperlyConfigured


def required(name):
    value = os.environ.get(name, "")
    if not value:
        raise ImproperlyConfigured(f"Set {name} for the document processing service.")
    return value


SECRET_KEY = required("PROCESSING_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = os.environ.get(
    "PROCESSING_ALLOWED_HOSTS", "localhost,127.0.0.1,document-processing"
).split(",")
INSTALLED_APPS = ["executions.apps.ExecutionsConfig"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware"]
ROOT_URLCONF = "processing_service.urls"
WSGI_APPLICATION = "processing_service.wsgi.application"
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PROCESSING_DB_NAME", "studyforge_processing"),
        "USER": os.environ.get("PROCESSING_DB_USER", "studyforge_processing"),
        "PASSWORD": required("PROCESSING_DB_PASSWORD"),
        "HOST": os.environ.get("PROCESSING_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("PROCESSING_DB_PORT", "5432"),
        "OPTIONS": {
            "connect_timeout": 3,
            **({"sslmode": os.environ["PROCESSING_DB_SSLMODE"]} if os.environ.get("PROCESSING_DB_SSLMODE") else {}),
            **({"sslrootcert": os.environ["PROCESSING_DB_SSLROOTCERT"]} if os.environ.get("PROCESSING_DB_SSLROOTCERT") else {}),
        },
    }
}
PROCESSING_REDIS_URL = os.environ.get("PROCESSING_REDIS_URL", "redis://127.0.0.1:6379/0")
PROCESSING_DJANGO_API_URL = os.environ.get("PROCESSING_DJANGO_API_URL", "")
PROCESSING_SERVICE_TOKEN = os.environ.get("PROCESSING_SERVICE_TOKEN", "")
PROCESSING_SOURCE_MODE = os.environ.get("PROCESSING_SOURCE_MODE", "django").strip().lower()
if PROCESSING_SOURCE_MODE not in {"django", "s3"}:
    raise ImproperlyConfigured("PROCESSING_SOURCE_MODE must be django or s3.")
PROCESSING_STORAGE_BUCKET = os.environ.get("PROCESSING_STORAGE_BUCKET", "").strip()
PROCESSING_STORAGE_REGION = os.environ.get("PROCESSING_STORAGE_REGION", "").strip()
PROCESSING_STORAGE_ENDPOINT_URL = os.environ.get("PROCESSING_STORAGE_ENDPOINT_URL", "").strip()
PROCESSING_STORAGE_ACCESS_KEY_ID = os.environ.get("PROCESSING_STORAGE_ACCESS_KEY_ID", "").strip()
PROCESSING_STORAGE_SECRET_ACCESS_KEY = os.environ.get("PROCESSING_STORAGE_SECRET_ACCESS_KEY", "").strip()
PROCESSING_STORAGE_SESSION_TOKEN = os.environ.get("PROCESSING_STORAGE_SESSION_TOKEN", "").strip()
PROCESSING_STORAGE_CA_BUNDLE = os.environ.get("PROCESSING_STORAGE_CA_BUNDLE", "").strip()
PROCESSING_STORAGE_CONNECT_TIMEOUT = int(os.environ.get("PROCESSING_STORAGE_CONNECT_TIMEOUT", "3"))
PROCESSING_STORAGE_READ_TIMEOUT = int(os.environ.get("PROCESSING_STORAGE_READ_TIMEOUT", "10"))
PROCESSING_STORAGE_ADDRESSING_STYLE = os.environ.get(
    "PROCESSING_STORAGE_ADDRESSING_STYLE", "path" if PROCESSING_STORAGE_ENDPOINT_URL else "auto"
).strip()
if PROCESSING_STORAGE_ADDRESSING_STYLE not in {"auto", "path", "virtual"}:
    raise ImproperlyConfigured("PROCESSING_STORAGE_ADDRESSING_STYLE is invalid.")
if PROCESSING_SOURCE_MODE == "s3":
    if not PROCESSING_STORAGE_BUCKET or not PROCESSING_STORAGE_REGION or bool(PROCESSING_STORAGE_ACCESS_KEY_ID) != bool(PROCESSING_STORAGE_SECRET_ACCESS_KEY):
        raise ImproperlyConfigured("Processing S3 storage needs a bucket, region, and a complete credential pair if keys are used.")
    if PROCESSING_STORAGE_ENDPOINT_URL:
        parsed = urlsplit(PROCESSING_STORAGE_ENDPOINT_URL)
        if not parsed.netloc or parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
            raise ImproperlyConfigured("PROCESSING_STORAGE_ENDPOINT_URL is invalid.")
        if parsed.scheme == "http" and os.environ.get("PROCESSING_STORAGE_ALLOW_HTTP", "0").lower() not in {"1", "true", "yes"}:
            raise ImproperlyConfigured("Processing S3 storage requires HTTPS unless local HTTP is explicitly enabled.")
if os.environ.get("STUDYFORGE_REQUIRE_SECURE_CONNECTIONS", "0").lower() in {"1", "true", "yes"}:
    if DATABASES["default"]["OPTIONS"].get("sslmode") != "verify-full":
        raise ImproperlyConfigured("Production processing PostgreSQL requires PROCESSING_DB_SSLMODE=verify-full.")
    if not PROCESSING_REDIS_URL.startswith("rediss://"):
        raise ImproperlyConfigured("Production processing Redis requires rediss://.")
    if parse_qs(urlsplit(PROCESSING_REDIS_URL).query).get("ssl_cert_reqs") != ["required"]:
        raise ImproperlyConfigured("Production processing Redis requires ssl_cert_reqs=required.")
    if PROCESSING_DJANGO_API_URL and not PROCESSING_DJANGO_API_URL.startswith("https://"):
        raise ImproperlyConfigured("Production processing Django URL requires HTTPS.")
    if PROCESSING_STORAGE_ENDPOINT_URL.startswith("http://"):
        raise ImproperlyConfigured("Production processing storage requires HTTPS.")
if os.environ.get("PROCESSING_REQUIRE_DIRECT_STORAGE", "0").lower() in {"1", "true", "yes"}:
    if PROCESSING_SOURCE_MODE != "s3" or not PROCESSING_DJANGO_API_URL.startswith("https://") or not PROCESSING_SERVICE_TOKEN:
        raise ImproperlyConfigured("Production workers require S3 source mode, HTTPS Django URL, and a service token.")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", "768"))
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "16"))
CELERY_BROKER_URL = PROCESSING_REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# A task is acknowledged only after the task function returns successfully.
# If the worker process/pod dies first, Redis can make the task visible again
# for another worker. The timeout must exceed the longest PDF processing run.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": int(
        os.environ.get("PROCESSING_REDIS_VISIBILITY_TIMEOUT", "3600")
    ),
}
CELERY_TASK_ROUTES = {
    "processing_service.tasks.process_document_task": {
        "queue": "document-processing",
    },
}
