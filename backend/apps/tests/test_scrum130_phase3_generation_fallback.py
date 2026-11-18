"""SCRUM-130 Phase 3: feature-level generation fallback tests."""

from unittest import TestCase
from unittest.mock import Mock

from apps.llm_fallback import FallbackClient


class GeminiTemporaryFailure(Exception):
    pass


class GenerationFallbackTests(TestCase):
    def _client_pair(self, method_name):
        gemini = Mock(name="gemini")
        gemini.name = "gemini-flash-latest"
        setattr(gemini, method_name, Mock())
        openai = Mock(name="openai")
        setattr(openai, method_name, Mock(return_value={"provider": "openai"}))
        factory = Mock(return_value=openai)
        return gemini, openai, factory

    def test_notes_use_openai_only_when_gemini_notes_fail(self):
        gemini, openai, factory = self._client_pair("generate_notes")
        gemini.generate_notes.side_effect = GeminiTemporaryFailure("timeout")
        sources = [("Cells", "cell material")]
        options = object()

        result = FallbackClient(gemini, factory).generate_notes(sources, options)

        self.assertEqual(result, {"provider": "openai"})
        openai.generate_notes.assert_called_once_with(sources, options)

    def test_quizzes_use_openai_only_when_gemini_quiz_fails(self):
        gemini, openai, factory = self._client_pair("generate_quiz")
        gemini.generate_quiz.side_effect = GeminiTemporaryFailure("rate limit")
        material, count = "course material", 5

        result = FallbackClient(gemini, factory).generate_quiz(material, count)

        self.assertEqual(result, {"provider": "openai"})
        openai.generate_quiz.assert_called_once_with(material, count)

    def test_pandu_answers_use_openai_only_when_gemini_answer_fails(self):
        gemini, openai, factory = self._client_pair("generate")
        gemini.generate.side_effect = GeminiTemporaryFailure("API error")
        question, chunks = "What is mitosis?", [{"chunk_id": 1, "content": "..."}]

        result = FallbackClient(gemini, factory).generate(question, chunks)

        self.assertEqual(result, {"provider": "openai"})
        openai.generate.assert_called_once_with(question, chunks)
