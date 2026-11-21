"""Exercise StudyForge's real Redis broker usage for SCRUM-134 checks.

Runs without loading backend settings or any env file. The broker URL comes
from SF134_BROKER_URL; nothing secret is printed.

  python broker_probe.py ping            # Django readiness PING
  python broker_probe.py dispatch        # real dispatch_document() publish
  python broker_probe.py send QUEUE [MARKER]  # harmless celery.accumulate task
  python broker_probe.py worker QUEUE    # default Celery worker (legacy shape)
  python broker_probe.py inspect         # control ping; prints the replying workers
"""

import os
import sys
from pathlib import Path
from uuid import uuid4

import django
from django.conf import settings

BACKEND = Path(__file__).resolve().parents[2] / "backend"
URL = os.environ["SF134_BROKER_URL"]
# Same broker options as backend/config/settings.py.
settings.configure(
    CELERY_BROKER_URL=URL,
    CELERY_BROKER_CONNECTION_TIMEOUT=3,
    CELERY_BROKER_TRANSPORT_OPTIONS={"socket_connect_timeout": 3, "socket_timeout": 3},
)
django.setup()


def app(name="sf134-probe"):
    from celery import Celery

    celery_app = Celery(name, set_as_current=False)
    celery_app.config_from_object("django.conf:settings", namespace="CELERY")
    return celery_app


def main(action, *args):
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
