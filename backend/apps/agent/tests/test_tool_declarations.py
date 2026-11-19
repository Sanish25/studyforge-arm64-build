from django.test import SimpleTestCase

import apps.agent.pandu.tools  # noqa: F401 — register tools
from apps.agent.pandu.llm import (
    _gemini_safe_parameters,
    _strip_markdown_fence,
    tool_declarations,
)
from apps.agent.pandu.tools.registry import all_tools, ToolSpec


class ToolDeclarationTests(SimpleTestCase):
    def test_all_registered_tools_build_gemini_declarations(self):
        tools = tool_declarations(all_tools())
        self.assertEqual(len(tools), 1)
        declarations = tools[0].function_declarations or []
        self.assertEqual(len(declarations), len(all_tools()))

    def test_strips_additional_properties_and_coerces_int_enums(self):
        safe = _gemini_safe_parameters(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "num_questions": {"type": "integer", "enum": [5, 10]},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "additionalProperties": False,
                    },
                },
                "required": ["num_questions"],
            }
        )
        self.assertNotIn("additionalProperties", safe)
        self.assertNotIn("additionalProperties", safe["properties"]["tags"])
        self.assertEqual(safe["properties"]["num_questions"]["enum"], ["5", "10"])
        self.assertEqual(safe["properties"]["num_questions"]["type"], "string")

    def test_strip_markdown_fence(self):
        raw = '```json\n{"type":"message","status":"ok","text":"Hi","citations":[],"tool_trace":[]}\n```'
        self.assertTrue(_strip_markdown_fence(raw).startswith("{"))

    def test_declaration_rejects_unsafe_raw_schema(self):
        # Building with stripped params must succeed even when the registry
        # schema still carries additionalProperties for handler docs.
        spec = ToolSpec(
            name="demo",
            description="demo",
            parameters={
                "type": "object",
                "additionalProperties": False,
                "properties": {"course_id": {"type": "integer"}},
                "required": ["course_id"],
            },
            handler=lambda **kwargs: None,
            mutates=False,
        )
        tools = tool_declarations([spec])
        params = tools[0].function_declarations[0].parameters
        # google-genai Schema object should not expose unsupported fields.
        dumped = params.model_dump(exclude_none=True) if hasattr(params, "model_dump") else dict(params)
        self.assertNotIn("additional_properties", dumped)
        self.assertNotIn("additionalProperties", dumped)
