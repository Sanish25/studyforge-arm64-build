"""Quiz tools: wrap existing quiz generate and fetch (new quiz row each generate)."""

from __future__ import annotations

from typing import Any

from django.http import Http404

from apps.agent.pandu.tools.registry import ToolSpec, register
from apps.agent.pandu.tools.results import tool_error, tool_ok
from apps.documents.models import Document
from apps.documents.selectors import get_owned_course_documents
from apps.identity.ownership import owned_course
from apps.quizzes.llm import ALLOWED_QUESTION_COUNTS, LLMError
from apps.quizzes.selectors import get_owned_quiz
from apps.quizzes.serializers import QuizSerializer
from apps.quizzes.services import EmptyDocumentError, generate_quiz


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _document_ids(value: Any) -> list[int] | None:
    if not isinstance(value, list) or not value:
        return None
    resolved: list[int] = []
    for item in value:
        document_id = _positive_int(item)
        if document_id is None:
            return None
        resolved.append(document_id)
    if len(set(resolved)) != len(resolved) or len(resolved) > 20:
        return None
    return resolved


def _num_questions(value: Any) -> int | None:
    resolved = _positive_int(value)
    if resolved not in ALLOWED_QUESTION_COUNTS:
        return None
    return resolved


def _quiz_payload(quiz) -> dict[str, Any]:
    return QuizSerializer(quiz).data


def generate_quiz_tool(*, user, course_id: Any, document_ids: Any, num_questions: Any) -> dict[str, Any]:
    """Generate a quiz via the existing service. Each call saves a new quiz."""
    resolved_course_id = _positive_int(course_id)
    resolved_ids = _document_ids(document_ids)
    resolved_count = _num_questions(num_questions)
    if resolved_course_id is None or resolved_ids is None or resolved_count is None:
        return tool_error(
            "INVALID_REQUEST",
            "Provide course_id, 1–20 unique document_ids, and num_questions of 5 or 10.",
        )

    course = owned_course(user, resolved_course_id)
    if course is None:
        return tool_error("RESOURCE_NOT_FOUND")

    try:
        documents = get_owned_course_documents(user, course, resolved_ids)
    except Http404:
        return tool_error("RESOURCE_NOT_FOUND")

    not_ready = [document.pk for document in documents if document.status != Document.Status.READY]
    if not_ready:
        return tool_error(
            "DOCUMENT_NOT_READY",
            "Some selected materials are still processing or failed.",
        )

    try:
        quiz = generate_quiz(user, course, documents, resolved_count)
    except EmptyDocumentError:
        return tool_error(
            "DOCUMENT_HAS_NO_TEXT",
            "No readable text could be extracted from some selected materials.",
        )
    except LLMError:
        return tool_error(
            "QUIZ_GENERATION_FAILED",
            "The quiz could not be generated right now. Please try again.",
        )

    return tool_ok(quiz=_quiz_payload(quiz))


def get_quiz(*, user, quiz_id: Any) -> dict[str, Any]:
    """Fetch an owned quiz (answers hidden until submitted, same as API)."""
    resolved_id = _positive_int(quiz_id)
    if resolved_id is None:
        return tool_error("INVALID_REQUEST", "Provide a valid quiz_id.")

    try:
        quiz = get_owned_quiz(user, resolved_id)
    except Http404:
        return tool_error("RESOURCE_NOT_FOUND")

    return tool_ok(quiz=_quiz_payload(quiz))


register(
    ToolSpec(
        name="generate_quiz",
        description=(
            "Generate a multiple-choice quiz from selected READY course materials. "
            "Uses the same quiz feature as the StudyForge UI. Each call creates a "
            "new quiz; students may generate as many quizzes as they need. "
            "num_questions must be 5 or 10."
        ),
        parameters={
            "type": "object",
            "properties": {
                "course_id": {"type": "integer"},
                "document_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 1,
                    "maxItems": 20,
                },
                # Gemini FunctionDeclaration rejects non-string enum values.
                "num_questions": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 10,
                    "description": "Number of questions; must be 5 or 10.",
                },
            },
            "required": ["course_id", "document_ids", "num_questions"],
            "additionalProperties": False,
        },
        handler=generate_quiz_tool,
        mutates=True,
    )
)

register(
    ToolSpec(
        name="get_quiz",
        description=(
            "Fetch a previously generated quiz by id for the authenticated student. "
            "Correct answers stay hidden until the quiz is submitted."
        ),
        parameters={
            "type": "object",
            "properties": {
                "quiz_id": {"type": "integer"},
            },
            "required": ["quiz_id"],
            "additionalProperties": False,
        },
        handler=get_quiz,
        mutates=False,
    )
)
