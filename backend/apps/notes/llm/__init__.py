"""Pick a generator from the environment, so calling code never
names a provider directly."""

import os

from apps.notes.llm.base import (
    DEFAULT_NOTE_OPTIONS,
    InvalidLLMOutput,
    LLMError,
    NoteOptions,
    NotesMergeTooLargeError,
    validate_course_notes,
    validate_study_guide,
)

__all__ = [
    "get_client",
    "DEFAULT_NOTE_OPTIONS",
    "LLMError",
    "InvalidLLMOutput",
    "NoteOptions",
    "NotesMergeTooLargeError",
    "validate_course_notes",
    "validate_study_guide",
]


def get_client():
    # TODO(SCRUM-68): move to Django settings once the app is registered.
    backend = os.environ.get("NOTES_LLM_BACKEND", "fake")

    if backend == "fake":
        from apps.notes.llm.fake import FakeStudyGuideLLM

        return FakeStudyGuideLLM()

    if backend == "gemini":
        from apps.llm_config import fallback_enabled, require_openai_key
        from apps.notes.llm.gemini import GeminiStudyGuideLLM
        from apps.notes.llm.provider import OpenAIStudyGuideLLM
        from apps.llm_fallback import FallbackClient

        primary = GeminiStudyGuideLLM()
        if not fallback_enabled():
            return primary
        require_openai_key()
        return FallbackClient(primary, OpenAIStudyGuideLLM, feature="notes")

    if backend == "openai":
        from apps.notes.llm.provider import OpenAIStudyGuideLLM

        return OpenAIStudyGuideLLM()

    raise LLMError(f"Unknown NOTES_LLM_BACKEND: {backend!r}")
