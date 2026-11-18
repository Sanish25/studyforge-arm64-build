"""Small provider failover helper used by text-generation features."""

import time

from apps.llm_telemetry import record


def is_retryable_provider_error(error):
    """Return true only for temporary provider failures, not bad model output."""
    if error.__class__.__name__ in {"InvalidLLMOutput", "InvalidCitation"}:
        return False
    message = str(error).casefold()
    return any(term in message for term in (
        "temporarily unavailable", "timeout", "timed out", "rate limit",
        "connection", "api error", "service unavailable",
    ))


class FallbackClient:
    """Call the primary once, then lazily call the fallback once if eligible."""

    def __init__(self, primary, fallback_factory, *, feature="unknown"):
        self.primary = primary
        self.fallback_factory = fallback_factory
        self.fallback = None
        self.name = getattr(primary, "name", "gemini")
        self.feature = feature

    def __getattr__(self, method_name):
        primary_method = getattr(self.primary, method_name)

        def call(*args, **kwargs):
            started = time.monotonic()
            try:
                result = primary_method(*args, **kwargs)
                record("success", feature=self.feature, provider="gemini",
                       duration_ms=(time.monotonic() - started) * 1000,
                       usage=getattr(result, "usage", None))
                return result
            except Exception as error:
                if not is_retryable_provider_error(error):
                    raise
                record("fallback_triggered", feature=self.feature, provider="gemini",
                       failure=error.__class__.__name__,
                       duration_ms=(time.monotonic() - started) * 1000)
                if self.fallback is None:
                    self.fallback = self.fallback_factory()
                fallback_started = time.monotonic()
                try:
                    result = getattr(self.fallback, method_name)(*args, **kwargs)
                except Exception:
                    record("failure", feature=self.feature, provider="openai",
                           duration_ms=(time.monotonic() - fallback_started) * 1000)
                    raise
                record("success", feature=self.feature, provider="openai",
                       duration_ms=(time.monotonic() - fallback_started) * 1000,
                       usage=getattr(result, "usage", None))
                return result

        return call
