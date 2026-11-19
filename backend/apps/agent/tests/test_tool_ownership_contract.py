import inspect

from django.test import SimpleTestCase

import apps.agent.pandu.tools  # noqa: F401  — register all tool modules
from apps.agent.pandu.tools.registry import all_tools


class ToolOwnershipContractTests(SimpleTestCase):
    """Every Pandu tool must take the JWT user from call context, not tool args."""

    EXPECTED = {
        "list_courses",
        "list_materials",
        "retrieve_chunks",
        "ask_course_question",
        "answer_from_sources",
        "generate_notes",
        "get_notes",
        "generate_quiz",
        "get_quiz",
        "list_tasks",
        "create_task",
        "complete_task",
        "recall_history",
        "remember_turn",
    }

    def test_registered_tools_match_inventory(self):
        names = {spec.name for spec in all_tools()}
        self.assertEqual(names, self.EXPECTED)

    def test_every_handler_requires_user_keyword(self):
        for spec in all_tools():
            parameters = inspect.signature(spec.handler).parameters
            self.assertIn(
                "user",
                parameters,
                msg=f"{spec.name} must accept user from JWT context",
            )
            self.assertNotIn(
                "user",
                spec.parameters.get("properties", {}),
                msg=f"{spec.name} must not expose user as a model-supplied tool arg",
            )
