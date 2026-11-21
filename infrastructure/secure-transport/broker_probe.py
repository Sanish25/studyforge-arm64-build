"""Exercise StudyForge's real Redis broker usage for SCRUM-134 checks.

The broker URL comes from SF134_BROKER_URL. The password-reset probe uses
backend settings with disposable values. No probe loads an env file.

  python broker_probe.py ping            # Django readiness PING
  python broker_probe.py dispatch        # real dispatch_document() publish
  python broker_probe.py password-reset  # real Django cache and throttle
  python broker_probe.py send QUEUE [MARKER]  # harmless celery.accumulate task
  python broker_probe.py worker QUEUE    # default Celery worker (legacy shape)
  python broker_probe.py inspect         # control ping; prints the replying workers
  python broker_probe.py reset-cache     # production password-reset cache calls
"""

import os
import sys
from pathlib import Path
from uuid import uuid4

import django
from django.conf import settings

BACKEND = Path(__file__).resolve().parents[2] / "backend"
URL = os.environ["SF134_BROKER_URL"]


def password_reset():
    sys.path.insert(0, str(BACKEND))
    # Use the real production settings with disposable values. In particular,
    # leave PASSWORD_RESET_CACHE_URL unset to exercise its broker URL fallback.
    os.environ.clear()
    os.environ.update(
        DJANGO_SETTINGS_MODULE="config.settings",
        PYTHON_DOTENV_DISABLED="1",
        DJANGO_DEBUG="0",
        DJANGO_SECRET_KEY="sf134-rehearsal",
        DJANGO_ALLOWED_HOSTS="localhost",
        PASSWORD_RESET_FRONTEND_URL="https://frontend.example.test",
        STUDYFORGE_REQUIRE_SECURE_CONNECTIONS="1",
        POSTGRES_PASSWORD="unused",
        POSTGRES_SSLMODE="verify-full",
        DOCUMENT_STORAGE_BACKEND="s3",
        DOCUMENT_STORAGE_BUCKET="sf134-rehearsal",
        DOCUMENT_STORAGE_REGION="us-phoenix-1",
        PROCESSING_SERVICE_TOKEN="sf134-rehearsal",
        CELERY_BROKER_URL=URL,
    )
    django.setup()
    from apps.users.password_reset import EMAIL_REQUEST_LIMIT, _consume_email_limit

    email = f"sf134-{uuid4().hex}@example.test"
    allowed = [_consume_email_limit(email) for _ in range(EMAIL_REQUEST_LIMIT + 1)]
    if allowed != [True] * EMAIL_REQUEST_LIMIT + [False]:
        raise SystemExit("Password-reset throttle did not enforce the email limit")
    print("password-reset: ok")


def app(name="sf134-probe"):
    from celery import Celery

    celery_app = Celery(name, set_as_current=False)
    celery_app.config_from_object("django.conf:settings", namespace="CELERY")
    return celery_app


def main(action, *args):
    if action == "password-reset":
        password_reset()
        return

    # Same broker options as backend/config/settings.py.
    settings.configure(
        CELERY_BROKER_URL=URL,
        CELERY_BROKER_CONNECTION_TIMEOUT=3,
        CELERY_BROKER_TRANSPORT_OPTIONS={"socket_connect_timeout": 3, "socket_timeout": 3},
    )
    django.setup()
    if action == "ping":
        from redis import Redis

        with Redis.from_url(URL, socket_connect_timeout=2, socket_timeout=2) as client:
            client.ping()
    elif action == "dispatch":
        sys.path.insert(0, str(BACKEND))
        from apps.documents.dispatch import dispatch_document

        dispatch_document(str(uuid4()), str(uuid4()), "0" * 64)
    elif action == "send":
        celery_app = app()
        marker = args[1] if len(args) > 1 else "sf134-marker"
        celery_app.send_task("celery.accumulate", args=[marker], queue=args[0], ignore_result=True)
        celery_app.close()
    elif action == "worker":
        app("sf134-legacy").worker_main(
            ["worker", "--loglevel=INFO", "--pool=solo", f"--queues={args[0]}", "--hostname=sf134-legacy@%h"]
        )
    elif action == "reset-cache":
        from django.core.cache.backends.redis import RedisCache

        # Same backend, prefix and calls as apps/users/password_reset.py with DEBUG off.
        cache = RedisCache(URL, {"KEY_PREFIX": "studyforge_password_reset"})
        key = f"password-reset:probe:{uuid4().hex}"
        if not (cache.add(key, 1, timeout=60) and cache.incr(key) == 2):
            raise SystemExit("reset-cache: unexpected result")
        cache.delete(key)
    elif action == "inspect":
        celery_app = app()
        replies = celery_app.control.inspect(timeout=3).ping() or {}
        celery_app.close()
        print("replies:", " ".join(sorted(replies)))
    else:
        raise SystemExit(__doc__)
    print(f"{action}: ok")


if __name__ == "__main__":
    main(*sys.argv[1:])
