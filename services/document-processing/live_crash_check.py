"""Disposable Redis and two real Celery workers: kill the first task consumer."""

import os
import signal
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from redis import Redis

def wait_until(predicate, label, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for {label}")


def main():
    container = f"studyforge-scrum109-redis-{uuid4().hex[:12]}"
    probe_key = f"scrum109:{uuid4().hex}"
    workers = []
    worker_logs = tempfile.TemporaryFile(mode="w+t")
    try:
        subprocess.run(
            ["docker", "run", "-d", "--rm", "--name", container,
             "-p", "127.0.0.1::6379", "redis:7-alpine"],
            check=True, stdout=subprocess.DEVNULL,
        )
        binding = subprocess.check_output(
            ["docker", "port", container, "6379/tcp"], text=True,
        ).strip()
        port = int(binding.rsplit(":", 1)[1])
        redis_url = f"redis://127.0.0.1:{port}/0"
        broker = Redis.from_url(redis_url)
        wait_until(lambda: broker.ping(), "Redis startup")

        env = os.environ.copy()
        env.update(
            PROCESSING_SECRET_KEY="disposable-crash-check",
            PROCESSING_DB_PASSWORD="unused-crash-check",
            PROCESSING_REDIS_URL=redis_url,
            PROCESSING_REDIS_VISIBILITY_TIMEOUT="10",
        )
        os.environ.update({key: env[key] for key in (
            "PROCESSING_SECRET_KEY", "PROCESSING_DB_PASSWORD",
            "PROCESSING_REDIS_URL", "PROCESSING_REDIS_VISIBILITY_TIMEOUT",
        )})
        from processing_service.celery import app
        print("Transport options:", app.conf.broker_transport_options, flush=True)

        queue = "scrum109-crash-probe"

        def start_worker(name):
            worker = subprocess.Popen(
                [sys.executable, "-m", "celery", "-A", "processing_service.celery:app",
                 "worker", "--pool=solo", "--concurrency=1", "--loglevel=INFO",
                 "-I", "processing_service.tests.crash_probe", "-Q", queue,
                 f"--hostname={name}@%h"],
                cwd=os.path.dirname(__file__), env=env,
                stdout=worker_logs, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            workers.append(worker)
            return worker

        first = start_worker("scrum109-first")
        wait_until(lambda: bool(app.control.inspect(timeout=1).ping() or {}), "first worker startup")
        app.send_task(
            "processing_service.tests.crash_probe.run", args=[redis_url, probe_key],
            queue=queue,
        )
        owner = wait_until(lambda: broker.get(f"{probe_key}:first"), "first worker claim")
        assert b"scrum109-first" in owner, owner
        start_worker("scrum109-second")
        wait_until(
            lambda: any("scrum109-second" in name for name in (app.control.inspect(timeout=1).ping() or {})),
            "second worker startup",
        )
        os.killpg(first.pid, signal.SIGKILL)
        first.wait(timeout=10)
        try:
            recovered = wait_until(
                lambda: broker.get(f"{probe_key}:recovered"), "redelivery to surviving worker", seconds=150,
            )
        except AssertionError:
            print("Broker diagnostic keys:", sorted(key.decode() for key in broker.keys("*")))
            print("Queue length:", broker.llen(queue))
            print("Unacked age seconds:", [(tag.decode(), round(time.time() - score, 1))
                   for tag, score in broker.zrange("unacked_index", 0, -1, withscores=True)])
            worker_logs.flush()
            worker_logs.seek(0)
            print("Worker logs:\n", worker_logs.read()[-8000:])
            raise
        assert b"scrum109-second" in recovered, recovered
        print("PASS: Redis redelivered the unacknowledged task to the surviving worker")
    finally:
        for worker in workers:
            if worker.poll() is None:
                os.killpg(worker.pid, signal.SIGKILL)
                worker.wait(timeout=10)
        subprocess.run(["docker", "stop", container], check=False, stdout=subprocess.DEVNULL)
        worker_logs.close()


if __name__ == "__main__":
    raise SystemExit(main())
