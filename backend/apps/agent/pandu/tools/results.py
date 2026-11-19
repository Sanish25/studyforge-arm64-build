"""Structured tool results returned to the model (architecture §4)."""

from __future__ import annotations

from typing import Any

from apps.documents.errors import MESSAGES


def tool_ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def tool_error(code: str, message: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "message": message or MESSAGES.get(code, "The tool request could not be completed."),
    }
