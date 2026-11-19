"""Course tools: list the logged-in student's courses (JWT ownership).

SCRUM-23 AC: "What courses am I taking?" → list_courses → real owned data only.
"""

from __future__ import annotations

from typing import Any

from apps.agent.pandu.tools.registry import ToolSpec, register
from apps.agent.pandu.tools.results import tool_ok
from apps.courses.models import Course


def _course_row(course: Course) -> dict[str, Any]:
    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "created_at": course.created_at.isoformat(),
    }


def list_courses(*, user) -> dict[str, Any]:
    """Return every course owned by the JWT user (newest first).

    Never takes a course_id from the model — this is the student's full list.
    Foreign courses cannot appear because the query is filtered by owner=user.
    """
    courses = Course.objects.filter(owner=user).order_by("-created_at", "-id")
    return tool_ok(courses=[_course_row(course) for course in courses])


register(
    ToolSpec(
        name="list_courses",
        description=(
            "List the authenticated student's courses (id, name, description, created_at). "
            "Use when they ask what courses they are taking. "
            "Returns only their courses — never another user's."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=list_courses,
        mutates=False,
    )
)
