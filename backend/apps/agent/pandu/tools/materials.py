"""Materials tools: wrap owned course documents and chat uploads."""

from __future__ import annotations

from typing import Any

from apps.agent.pandu.tools.registry import ToolSpec, register
from apps.agent.pandu.tools.results import tool_error, tool_ok
from apps.documents.models import Document
from apps.identity.ownership import owned_course


def _course_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def list_materials(*, user, course_id: Any) -> dict[str, Any]:
    """List course materials for an owned course (not chat uploads)."""
    resolved = _course_id(course_id)
    if resolved is None:
        return tool_error("INVALID_REQUEST", "Provide a valid course_id.")

    course = owned_course(user, resolved)
    if course is None:
        return tool_error("RESOURCE_NOT_FOUND")

    documents = (
        Document.objects.filter(course=course, conversation__isnull=True)
        .order_by("-created_at", "-pk")
        .only("id", "title", "status", "created_at")
    )
    return tool_ok(
        documents=[
            {
                "id": document.id,
                "title": document.title,
                "status": document.status,
                "created_at": document.created_at.isoformat(),
            }
            for document in documents
        ]
    )


register(
    ToolSpec(
        name="list_materials",
        description=(
            "List the authenticated student's course materials for one owned course. "
            "Returns id, title, status, and created_at. Does not include chat uploads."
        ),
        parameters={
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "integer",
                    "description": "Owned course id whose materials should be listed.",
                },
            },
            "required": ["course_id"],
            "additionalProperties": False,
        },
        handler=list_materials,
        mutates=False,
    )
)
