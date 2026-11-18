"""SCRUM-130 Phase 1: Gemini-first/OpenAI-fallback orchestration tests."""

from unittest import TestCase
from unittest.mock import Mock

from apps.llm_fallback import FallbackClient


class TemporaryProviderError(Exception):
    pass


class InvalidLLMOutput(Exception):
    pass


class FallbackClientTests(TestCase):
    def test_primary_success_does_not_create_or_call_fallback(self):
        primary = Mock(name="gemini")
        primary.name = "gemini-flash-latest"
        primary.generate.return_value = {"answer": "ok"}
        fallback_factory = Mock(name="openai_factory")

        result = FallbackClient(primary, fallback_factory).generate("question", ["chunk"])

        self.assertEqual(result, {"answer": "ok"})
        primary.generate.assert_called_once_with("question", ["chunk"])
        fallback_factory.assert_not_called()

    def test_retryable_primary_failure_retries_once_with_same_arguments(self):
        primary = Mock(name="gemini")
        primary.name = "gemini-flash-latest"
        primary.generate.side_effect = TemporaryProviderError(
            "Gemini generation is temporarily unavailable."
        )
        fallback = Mock(name="openai")
        fallback.generate.return_value = {"answer": "from OpenAI"}
        fallback_factory = Mock(return_value=fallback)

        result = FallbackClient(primary, fallback_factory).generate("question", ["chunk"])

        self.assertEqual(result, {"answer": "from OpenAI"})
        fallback_factory.assert_called_once_with()
        fallback.generate.assert_called_once_with("question", ["chunk"])

    def test_invalid_output_does_not_trigger_fallback(self):
        primary = Mock(name="gemini")
        primary.name = "gemini-flash-latest"
        primary.generate.side_effect = InvalidLLMOutput("invalid response")
        fallback_factory = Mock(name="openai_factory")

        with self.assertRaises(InvalidLLMOutput):
            FallbackClient(primary, fallback_factory).generate("question", ["chunk"])

        fallback_factory.assert_not_called()
