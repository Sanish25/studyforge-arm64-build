"""Provider telemetry for SCRUM-130; never records prompts or source content."""
import logging
from collections import Counter

logger = logging.getLogger("studyforge.llm")
COUNTERS = Counter()


def record(event, *, feature, provider, failure=None, duration_ms=None, usage=None):
    COUNTERS[(feature, provider, event)] += 1
    extra = {"feature": feature, "provider": provider, "event": event}
    if failure:
        extra["failure"] = failure
    if duration_ms is not None:
        extra["duration_ms"] = round(duration_ms, 2)
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if isinstance(usage.get(key), int):
                extra[key] = usage[key]
    logger.info("llm_provider_event", extra=extra)
