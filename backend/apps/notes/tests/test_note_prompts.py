"""SCRUM-86: how note options shape the prompt, the validator and the output.

Generator-level only: no models, database or API. Nothing calls a provider.
"""

import itertools
import json
import os
from unittest import mock

from django.test import SimpleTestCase

from apps.notes.llm import InvalidLLMOutput, NoteOptions, validate_course_notes
from apps.notes.llm.base import DETAIL_LEVELS, NOTE_FORMATS, NOTE_TYPES
from apps.notes.llm.fake import FakeStudyGuideLLM
from apps.notes.llm.prompts import (
    DETAIL_LEVEL_RULES,
    NOTE_FORMAT_RULES,
    NOTE_TYPE_RULES,
    build_notes_prompt,
)
from apps.notes.llm.provider import OpenAIStudyGuideLLM
from apps.notes.tests.test_course_notes import VALID_NOTES

ALL_OPTIONS = [
    NoteOptions(note_type, detail_level, note_format)
    for note_type, detail_level, note_format in itertools.product(NOTE_TYPES, DETAIL_LEVELS, NOTE_FORMATS)
]


class NoteOptionsTests(SimpleTestCase):
    def test_unknown_option_values_are_refused(self):
        for kwargs in ({"note_type": "essay"}, {"detail_level": "max"}, {"format": "table"}):
            with self.subTest(kwargs), self.assertRaises(ValueError):
                NoteOptions(**kwargs)


class PromptTests(SimpleTestCase):
    def test_every_option_value_has_a_fragment(self):
        self.assertEqual(set(NOTE_TYPE_RULES), set(NOTE_TYPES))
        self.assertEqual(set(DETAIL_LEVEL_RULES), set(DETAIL_LEVELS))
        self.assertEqual(set(NOTE_FORMAT_RULES), set(NOTE_FORMATS))

    def test_the_prompt_carries_exactly_the_chosen_fragments(self):
        for options in ALL_OPTIONS:
            with self.subTest(options):
                prompt = build_notes_prompt(options)
                for rules, chosen in (
                    (NOTE_TYPE_RULES, options.note_type),
                    (DETAIL_LEVEL_RULES, options.detail_level),
                    (NOTE_FORMAT_RULES, options.format),
                ):
                    for value, fragment in rules.items():
                        if value == chosen:
                            self.assertIn(fragment, prompt)
                        else:
                            self.assertNotIn(fragment, prompt)

    def test_every_combination_gets_its_own_prompt_within_budget(self):
        prompts = [build_notes_prompt(options) for options in ALL_OPTIONS]
        self.assertEqual(len(set(prompts)), len(ALL_OPTIONS))
        # Small next to the 60,000-character batch limit.
        self.assertTrue(all(len(prompt) < 5_000 for prompt in prompts))


class PerTypeValidationTests(SimpleTestCase):
    section = VALID_NOTES["sections"][0]

    def notes(self, **section):
        return {**VALID_NOTES, "sections": [{**self.section, **section}]}

    def test_key_concepts_notes_need_concepts_in_every_section(self):
        options = NoteOptions(note_type="key_concepts")
        validate_course_notes(self.notes(points=[]), options)
        with self.assertRaises(InvalidLLMOutput):
            validate_course_notes(
                {**VALID_NOTES, "sections": [self.section, {**self.section, "key_concepts": []}]}, options
            )

    def test_outline_sections_need_points(self):
        with self.assertRaises(InvalidLLMOutput):
            validate_course_notes(self.notes(points=[]), NoteOptions(note_type="outline"))

    def test_a_summary_may_have_no_key_concepts(self):
        options = NoteOptions(note_type="summary")
        self.assertEqual(validate_course_notes(self.notes(key_concepts=[]), options)["sections"][0]["key_concepts"], [])
        with self.assertRaises(InvalidLLMOutput):
            validate_course_notes(self.notes(key_concepts=[], points=[]), options)

    def test_an_omitted_list_counts_as_empty_but_a_wrong_type_does_not(self):
        # Live gpt-4o-mini summary notes left key_concepts out of sections that
        # had none, and every such note was rejected as invalid output.
        no_concepts = {"heading": "Themes", "points": ["Cells divide by mitosis."]}
        no_points = {"heading": "Terms", "key_concepts": self.section["key_concepts"]}
        summary = validate_course_notes(
            {**VALID_NOTES, "sections": [no_concepts]}, NoteOptions(note_type="summary")
        )
        self.assertEqual(summary["sections"][0]["key_concepts"], [])
        glossary = validate_course_notes(
            {**VALID_NOTES, "sections": [no_points]}, NoteOptions(note_type="key_concepts")
        )
        self.assertEqual(glossary["sections"][0]["points"], [])

        for bad in ({"key_concepts": None}, {"points": "Cells divide."}):
            with self.subTest(bad), self.assertRaises(InvalidLLMOutput):
                validate_course_notes(self.notes(**bad), NoteOptions(note_type="summary"))
        with self.assertRaises(InvalidLLMOutput):
            validate_course_notes({**VALID_NOTES, "sections": [{"heading": "Empty"}]})

    def test_the_prompt_asks_for_empty_lists_instead_of_missing_keys(self):
        for options in ALL_OPTIONS:
            with self.subTest(options):
                self.assertIn("never leave a key out", build_notes_prompt(options))


class ProviderOptionTests(SimpleTestCase):
    def make_provider(self, batch_limit=60_000):
        env = {"OPENAI_API_KEY": "test", "NOTES_BATCH_CHAR_LIMIT": str(batch_limit)}
        with mock.patch.dict(os.environ, env), mock.patch("apps.notes.llm.provider.OpenAI"):
            return OpenAIStudyGuideLLM()

    def test_batches_and_merge_all_use_the_chosen_prompt(self):
        options = NoteOptions("key_concepts", "brief", "paragraphs")
        provider = self.make_provider(batch_limit=100)
        with mock.patch.object(provider, "_complete", return_value=json.dumps(VALID_NOTES)) as call:
            provider.generate_notes([("Cells", "a" * 50), ("Genes", "b" * 50)], options)

        self.assertEqual(call.call_count, 3)
        for args in call.call_args_list:
            self.assertEqual(args.args[0], build_notes_prompt(options))

    def test_brief_notes_are_not_mistaken_for_skimmed_output(self):
        # One batch (under the 60,000-character limit) and output of about 1.3%
        # of it: under the 2% standard floor, over the 0.5% brief floor.
        material = [("Cells", "a" * 55_000)]
        output = json.dumps({**VALID_NOTES, "overview": "x" * 500})
        self.assertTrue(0.005 * 55_000 < len(output) < 0.02 * 55_000)
        provider = self.make_provider()

        with mock.patch.object(provider, "_complete", return_value=output) as call:
            provider.generate_notes(material, NoteOptions(detail_level="brief"))
        self.assertEqual(call.call_count, 1)

        with mock.patch.object(provider, "_complete", return_value=output) as call:
            with self.assertRaises(InvalidLLMOutput):
                provider.generate_notes(material, NoteOptions(detail_level="standard"))
        self.assertEqual(call.call_count, 2)

    def test_invalid_json_reports_retry_without_logging_model_text(self):
        provider = self.make_provider()
        raw = "private student material in malformed JSON"

        with mock.patch.object(provider, "_complete", return_value=raw) as call:
            with self.assertLogs("apps.notes.llm.provider", level="WARNING") as logs:
                with self.assertRaisesRegex(InvalidLLMOutput, "Model did not return JSON") as error:
                    provider.generate_notes([("Cells", "Cell text.")])

        self.assertEqual(call.call_count, 2)
        self.assertEqual(len(logs.output), 2)
        self.assertIn("phase=batch attempt=1 options=outline/standard/bullets", logs.output[0])
        self.assertIn("phase=batch attempt=2 options=outline/standard/bullets", logs.output[1])
        self.assertNotIn(raw, str(error.exception))
        self.assertNotIn(raw, "\n".join(logs.output))


class FakeOptionTests(SimpleTestCase):
    """The fake LLM is what the endpoint tests see, so every option must show."""

    sources = [("Cells", "Cell text here."), ("Genes", "Gene text.")]

    def generate(self, **options):
        return FakeStudyGuideLLM().generate_notes(self.sources, NoteOptions(**options))

    def test_each_option_changes_the_output(self):
        base = self.generate()
        for options in ({"note_type": "summary"}, {"note_type": "key_concepts"},
                        {"detail_level": "brief"}, {"detail_level": "detailed"}, {"format": "paragraphs"}):
            with self.subTest(options):
                self.assertNotEqual(self.generate(**options)["sections"], base["sections"])

    def test_the_output_matches_what_each_option_promises(self):
        self.assertEqual([s["heading"] for s in self.generate(note_type="summary")["sections"]], ["Main themes"])
        self.assertTrue(all(not s["points"] for s in self.generate(note_type="key_concepts")["sections"]))
        brief = self.generate(detail_level="brief")["sections"][0]["points"]
        detailed = self.generate(detail_level="detailed")["sections"][0]["points"]
        self.assertLess(len(brief), len(detailed))
        paragraph = self.generate(format="paragraphs")["sections"][0]["points"][0]
        self.assertGreater(paragraph.count(". "), 1)
