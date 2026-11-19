"""Notes tools: wrap existing course-notes generate and fetch."""

from __future__ import annotations

from typing import Any

from django.http import Http404

from apps.agent.pandu.tools.registry import ToolSpec, register
from apps.agent.pandu.tools.results import tool_error, tool_ok
from apps.documents.models import Document
from apps.documents.selectors import get_owned_course_documents
from apps.identity.ownership import owned_course
from apps.notes.llm import LLMError
from apps.notes.selectors import get_owned_notes
from apps.notes.serializers import CourseNotesSerializer
from apps.notes.services import (
    EmptyMaterialsError,
    NotesInputTooLargeError,
    generate_course_notes,
)


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


def _notes_payload(notes) -> dict[str, Any]:
    return CourseNotesSerializer(notes).data


def generate_notes(*, user, course_id: Any, document_ids: Any) -> dict[str, Any]:
    """Generate course notes via the existing notes service (new row each run)."""
    resolved_course_id = _positive_int(course_id)
    resolved_ids = _document_ids(document_ids)
    if resolved_course_id is None or resolved_ids is None:
        return tool_error(
            "INVALID_REQUEST",
            "Provide course_id and 1–20 unique document_ids.",
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
        notes = generate_course_notes(user, course, documents)
    except EmptyMaterialsError:
        return tool_error(
            "DOCUMENT_HAS_NO_TEXT",
            "No readable text could be extracted from some selected materials.",
        )
    except NotesInputTooLargeError:
        return tool_error(
            "NOTES_INPUT_TOO_LARGE",
            "The selected materials are too long to process together. Select fewer.",
        )
    except LLMError:
        return tool_error(
            "NOTES_GENERATION_FAILED",
            "The notes could not be generated right now. Please try again.",
        )
    except Http404:
        return tool_error("RESOURCE_NOT_FOUND")

    return tool_ok(notes=_notes_payload(notes))


def get_notes(*, user, note_id: Any) -> dict[str, Any]:
    """Fetch an owned CourseNotes row by id."""
    resolved_id = _positive_int(note_id)
    if resolved_id is None:
        return tool_error("INVALID_REQUEST", "Provide a valid note_id.")

    try:
        notes = get_owned_notes(user, resolved_id)
    except Http404:
        return tool_error("RESOURCE_NOT_FOUND")

    return tool_ok(notes=_notes_payload(notes))


register(
    ToolSpec(
        name="generate_notes",
        description=(
            "Generate structured course notes from selected READY materials in an "
            "owned course. Uses the same notes feature as the StudyForge UI and "
            "saves a new notes set each time."
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
            },
            "required": ["course_id", "document_ids"],
            "additionalProperties": False,
        },
        handler=generate_notes,
        mutates=True,
    )
)

register(
    ToolSpec(
        name="get_notes",
        description=(
            "Fetch previously generated course notes by id for the authenticated student."
        ),
        parameters={
            "type": "object",
            "properties": {
                "note_id": {"type": "integer"},
            },
            "required": ["note_id"],
            "additionalProperties": False,
        },
        handler=get_notes,
        mutates=False,
    )
)
