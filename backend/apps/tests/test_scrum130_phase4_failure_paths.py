"""SCRUM-130 Phase 4: verify fallback and final failure behavior."""

from unittest import TestCase
from unittest.mock import Mock

from apps.llm_fallback import FallbackClient


class GeminiFailure(Exception):
    pass


class InvalidLLMOutput(Exception):
    pass


class FailurePathTests(TestCase):
    def test_each_retryable_gemini_failure_reaches_openai_once(self):
        for reason in ("API error", "rate limit", "timeout", "connection failure"):
            with self.subTest(reason=reason):
                gemini = Mock(name="gemini")
                gemini.generate.side_effect = GeminiFailure(reason)
                openai = Mock(name="openai")
                openai.generate.return_value = {"status": "ANSWERED"}
                factory = Mock(return_value=openai)
                request = ("question", [{"chunk_id": 9, "content": "source"}])

                result = FallbackClient(gemini, factory).generate(*request)

                self.assertEqual(result, {"status": "ANSWERED"})
                factory.assert_called_once_with()
                openai.generate.assert_called_once_with(*request)

    def test_openai_failure_is_returned_after_gemini_failure(self):
        gemini = Mock(name="gemini")
        gemini.generate.side_effect = GeminiFailure("timeout")
        openai = Mock(name="openai")
        openai.generate.side_effect = RuntimeError("OpenAI unavailable")

        with self.assertRaisesRegex(RuntimeError, "OpenAI unavailable"):
            FallbackClient(gemini, Mock(return_value=openai)).generate("q", [])

    def test_invalid_gemini_output_does_not_fallback(self):
        gemini = Mock(name="gemini")
        gemini.generate.side_effect = InvalidLLMOutput("invalid response")
        factory = Mock(name="openai_factory")

        with self.assertRaises(InvalidLLMOutput):
            FallbackClient(gemini, factory).generate("q", [])

        factory.assert_not_called()
