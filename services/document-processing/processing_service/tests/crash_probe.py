"""Test-only Celery task for observing broker recovery after a worker is killed."""

import time

from celery import shared_task
from redis import Redis


@shared_task(name="processing_service.tests.crash_probe.run")
def run(redis_url: str, probe_key: str) -> None:
    broker = Redis.from_url(redis_url)
    hostname = run.request.hostname
    if broker.set(f"{probe_key}:first", hostname, nx=True):
        # The live test kills this worker before it can acknowledge the task.
        time.sleep(90)
        return
    broker.set(f"{probe_key}:recovered", hostname)
