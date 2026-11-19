"""Forced JSON reply envelope for Pandu (docs/architecture/pandu-agent.md §7).

Enforce in the backend (not prompt-only):
1. Validate against the reply schema before responding.
2. On invalid shape: one repair attempt, then a safe status:\"error\" body.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

REPLY_TYPE = "message"
REPLY_STATUSES = frozenset({"ok", "clarify", "abstain", "error"})
ALLOWED_KEYS = frozenset({"type", "status", "text", "citations", "tool_trace"})

REPLY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "status", "text", "citations"],
    "properties": {
        "type": {"const": REPLY_TYPE},
        "status": {"enum": sorted(REPLY_STATUSES)},
        "text": {"type": "string", "minLength": 1},
        "citations": {"type": "array"},
        "tool_trace": {"type": "array"},
    },
    "additionalProperties": False,
}

DEFAULT_ERROR_TEXT = "Pandu couldn't finish the answer right now. Please try again later."


class InvalidReply(ValueError):
    """Raised when a candidate reply fails the JSON envelope contract."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def error_reply(text: str = DEFAULT_ERROR_TEXT) -> dict[str, Any]:
    return {
        "type": REPLY_TYPE,
        "status": "error",
        "text": text if isinstance(text, str) and text.strip() else DEFAULT_ERROR_TEXT,
        "citations": [],
        "tool_trace": [],
    }


def _as_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            loaded = json.loads(payload)
        except (TypeError, ValueError, RecursionError) as exc:
            raise InvalidReply("Reply is not valid JSON.") from exc
        if not isinstance(loaded, dict):
            raise InvalidReply("Reply JSON must be an object.")
        return loaded
    raise InvalidReply("Reply must be a JSON object.")


def parse_reply(payload: Any) -> dict[str, Any]:
    """Validate and normalize a reply. Raises InvalidReply on contract failure."""
    data = _as_object(payload)

    unknown = set(data) - ALLOWED_KEYS
    if unknown:
        raise InvalidReply(f"Unknown reply fields: {', '.join(sorted(unknown))}.")

    if data.get("type") != REPLY_TYPE:
        raise InvalidReply('Reply type must be "message".')

    status = data.get("status")
    if status not in REPLY_STATUSES:
        raise InvalidReply("Reply status must be ok, clarify, abstain, or error.")

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise InvalidReply("Reply text must be a nonempty string.")

    citations = data.get("citations", [])
    if citations is None:
        citations = []
    if not isinstance(citations, list):
        raise InvalidReply("Reply citations must be an array.")
    if not all(isinstance(item, dict) for item in citations):
        raise InvalidReply("Reply citation items must be objects.")

    tool_trace = data.get("tool_trace", [])
    if tool_trace is None:
        # Architecture allows omitting tool_trace; normalize to [].
        tool_trace = []
    if not isinstance(tool_trace, list):
        raise InvalidReply("Reply tool_trace must be an array.")

    return {
        "type": REPLY_TYPE,
        "status": status,
        "text": text,
        "citations": citations,
        "tool_trace": tool_trace,
    }


def validate_reply(payload: Any) -> dict[str, Any]:
    """Validate without repair. Invalid input becomes a safe error envelope."""
    try:
        return parse_reply(payload)
    except InvalidReply:
        return error_reply()


def enforce_reply(
    payload: Any,
    *,
    repair: Callable[[Any, str], Any] | None = None,
) -> dict[str, Any]:
    """Validate the reply envelope; on failure, attempt exactly one repair.

    ``repair(invalid_payload, reason)`` should return a new candidate (dict or
    JSON string). A second failure (or a repair that raises) yields ``error_reply``.
    """
    try:
        return parse_reply(payload)
    except InvalidReply as first_error:
        if repair is None:
            return error_reply()
        try:
            repaired = repair(payload, first_error.reason)
            return parse_reply(repaired)
        except InvalidReply:
            return error_reply()
        except Exception:
            return error_reply()
