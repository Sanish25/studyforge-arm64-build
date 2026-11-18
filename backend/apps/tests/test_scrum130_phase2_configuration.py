"""SCRUM-130 Phase 2 configuration and failure checks."""
import os
from unittest import TestCase
from unittest.mock import patch

from apps.llm_config import fallback_enabled, openai_model, require_openai_key


class ConfigurationTests(TestCase):
    def test_fallback_defaults_to_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(fallback_enabled())

    def test_missing_openai_key_is_rejected_when_enabled(self):
        with patch.dict(os.environ, {"AI_FALLBACK_ENABLED": "true"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                require_openai_key()

    def test_missing_openai_key_is_allowed_when_disabled(self):
        with patch.dict(os.environ, {"AI_FALLBACK_ENABLED": "false"}, clear=True):
            require_openai_key()

    def test_openai_model_setting_is_separate_and_overrides_legacy_setting(self):
        env = {"NOTES_LLM_MODEL": "gemini-model", "OPENAI_NOTES_MODEL": "openai-model"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(openai_model("notes"), "openai-model")
