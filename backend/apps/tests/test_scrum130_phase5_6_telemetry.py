"""SCRUM-130 Phases 5–6: fallback logs and usage counters."""
import logging
from unittest import TestCase
from unittest.mock import Mock, patch

from apps.llm_fallback import FallbackClient
from apps.llm_telemetry import COUNTERS


class TelemetryTests(TestCase):
    def setUp(self):
        COUNTERS.clear()

    def test_gemini_success_records_no_fallback(self):
        gemini = Mock()
        gemini.generate.return_value = {"answer": "ok"}
        factory = Mock()

        with self.assertLogs("studyforge.llm", level=logging.INFO) as logs:
            FallbackClient(gemini, factory, feature="pandu").generate("q", [])

        self.assertEqual(COUNTERS[("pandu", "gemini", "success")], 1)
        self.assertNotIn(("pandu", "gemini", "fallback_triggered"), COUNTERS)
        factory.assert_not_called()
        self.assertIn("llm_provider_event", logs.output[0])

    def test_gemini_failure_and_openai_success_record_both_events(self):
        gemini = Mock()
        gemini.generate.side_effect = RuntimeError("Gemini timeout")
        openai = Mock()
        openai.generate.return_value = {"answer": "backup"}

        FallbackClient(gemini, Mock(return_value=openai), feature="pandu").generate("q", [])

        self.assertEqual(COUNTERS[("pandu", "gemini", "fallback_triggered")], 1)
        self.assertEqual(COUNTERS[("pandu", "openai", "success")], 1)

    def test_both_failures_record_openai_failure(self):
        gemini = Mock()
        gemini.generate.side_effect = RuntimeError("Gemini timeout")
        openai = Mock()
        openai.generate.side_effect = RuntimeError("OpenAI unavailable")

        with self.assertRaisesRegex(RuntimeError, "OpenAI unavailable"):
            FallbackClient(gemini, Mock(return_value=openai), feature="notes").generate("q", [])

        self.assertEqual(COUNTERS[("notes", "openai", "failure")], 1)
