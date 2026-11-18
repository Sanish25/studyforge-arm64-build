"""Pick a generator from the environment, so calling code never
names a provider directly."""

import os

from apps.quizzes.llm.base import (
    ALLOWED_QUESTION_COUNTS,
    InvalidLLMOutput,
    LLMError,
    validate_quiz,
)

__all__ = [
    "ALLOWED_QUESTION_COUNTS",
    "get_client",
    "InvalidLLMOutput",
    "LLMError",
    "validate_quiz",
]


def get_client():
    backend = os.environ.get("QUIZ_LLM_BACKEND", "fake")

    if backend == "fake":
        from apps.quizzes.llm.fake import FakeQuizLLM

        return FakeQuizLLM()

    if backend == "gemini":
        from apps.llm_config import fallback_enabled, require_openai_key
        from apps.quizzes.llm.gemini import GeminiQuizLLM
        from apps.quizzes.llm.provider import OpenAIQuizLLM
        from apps.llm_fallback import FallbackClient

        primary = GeminiQuizLLM()
        if not fallback_enabled():
            return primary
        require_openai_key()
        return FallbackClient(primary, OpenAIQuizLLM, feature="quizzes")

    if backend == "openai":
        from apps.quizzes.llm.provider import OpenAIQuizLLM

        return OpenAIQuizLLM()

    raise LLMError(f"Unknown QUIZ_LLM_BACKEND: {backend!r}")
