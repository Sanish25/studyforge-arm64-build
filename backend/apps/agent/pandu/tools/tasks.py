"""Task tools: wrap course to-dos with JWT-user ownership via course.owner."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from django.db import IntegrityError

from apps.agent.pandu.tools.registry import ToolSpec, register
from apps.agent.pandu.tools.results import tool_error, tool_ok
from apps.courses.models import TodoItem
from apps.identity.ownership import owned_course


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _creation_key(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except (TypeError, ValueError):
            return None
    return None


def _due_date(value: Any) -> date | None | object:
    """Return a date, None for omitted/null, or Ellipsis when invalid."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return Ellipsis
    return Ellipsis


def _task_payload(todo: TodoItem) -> dict[str, Any]:
    return {
        "id": todo.id,
        "title": todo.title,
        "course_id": todo.course_id,
        "due_date": todo.due_date.isoformat() if todo.due_date else None,
        "is_completed": todo.is_completed,
        "created_at": todo.created_at.isoformat(),
    }


def _owned_todo(user, task_id: int) -> TodoItem | None:
    return (
        TodoItem.objects.select_related("course")
        .filter(pk=task_id, course__owner=user)
        .first()
    )


def list_tasks(*, user, course_id: Any = None) -> dict[str, Any]:
    """List to-dos owned through course.owner; optional course filter."""
    todos = TodoItem.objects.filter(course__owner=user).select_related("course")
    if course_id is not None:
        resolved = _positive_int(course_id)
        if resolved is None:
            return tool_error("INVALID_REQUEST", "Provide a valid course_id.")
        course = owned_course(user, resolved)
        if course is None:
            return tool_error("RESOURCE_NOT_FOUND")
        todos = todos.filter(course=course)

    todos = todos.order_by("is_completed", "due_date", "created_at", "id")
    return tool_ok(tasks=[_task_payload(todo) for todo in todos])


def create_task(
    *,
    user,
    course_id: Any,
    title: Any,
    creation_key: Any,
    due_date: Any = None,
) -> dict[str, Any]:
    """Create a to-do on an owned course (idempotent via creation_key)."""
    resolved_course_id = _positive_int(course_id)
    key = _creation_key(creation_key)
    if resolved_course_id is None or key is None:
        return tool_error(
            "INVALID_REQUEST",
            "Provide course_id, title, and a UUID creation_key.",
        )
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        return tool_error("INVALID_REQUEST", "Provide a title of 1 to 200 characters.")

    parsed_due = _due_date(due_date)
    if parsed_due is Ellipsis:
        return tool_error("INVALID_REQUEST", "due_date must be YYYY-MM-DD or null.")

    course = owned_course(user, resolved_course_id)
    if course is None:
        return tool_error("RESOURCE_NOT_FOUND")

    clean_title = title.strip()
    try:
        todo, created = TodoItem.objects.select_related("course").get_or_create(
            creation_key=key,
            defaults={
                "title": clean_title,
                "course": course,
                "due_date": parsed_due,
            },
        )
    except IntegrityError:
        return tool_error(
            "CONFLICT",
            "This creation key has already been used for a different task.",
        )

    if not created and (
        todo.course.owner_id != user.pk
        or todo.title != clean_title
        or todo.course_id != course.pk
        or todo.due_date != parsed_due
    ):
        # Same safe posture as the todos API: do not leak another student's task.
        return tool_error(
            "CONFLICT",
            "This creation key has already been used for a different task.",
        )

    return tool_ok(task=_task_payload(todo), created=created)


def complete_task(*, user, task_id: Any, is_completed: Any) -> dict[str, Any]:
    """Toggle completion on an owned to-do."""
    resolved_id = _positive_int(task_id)
    if resolved_id is None:
        return tool_error("INVALID_REQUEST", "Provide a valid task_id.")
    if not isinstance(is_completed, bool):
        return tool_error("INVALID_REQUEST", "is_completed must be true or false.")

    todo = _owned_todo(user, resolved_id)
    if todo is None:
        return tool_error("RESOURCE_NOT_FOUND")

    todo.is_completed = is_completed
    todo.save(update_fields=["is_completed"])
    return tool_ok(task=_task_payload(todo))


register(
    ToolSpec(
        name="list_tasks",
        description=(
            "List to-dos for the authenticated student. Optionally filter by an "
            "owned course_id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "course_id": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=list_tasks,
        mutates=False,
    )
)

register(
    ToolSpec(
        name="create_task",
        description=(
            "Create a to-do on an owned course. Pass a UUID creation_key so retries "
            "do not create duplicate tasks."
        ),
        parameters={
            "type": "object",
            "properties": {
                "course_id": {"type": "integer"},
                "title": {"type": "string"},
                "creation_key": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["course_id", "title", "creation_key"],
            "additionalProperties": False,
        },
        handler=create_task,
        mutates=True,
    )
)

register(
    ToolSpec(
        name="complete_task",
        description=(
            "Mark an owned to-do completed or incomplete. Only tasks on the "
            "student's courses can be updated."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "is_completed": {"type": "boolean"},
            },
            "required": ["task_id", "is_completed"],
            "additionalProperties": False,
        },
        handler=complete_task,
        mutates=True,
    )
)
