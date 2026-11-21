"""Durable chat memory tools: read/write ConversationMessage via ownership helpers.

SCRUM-23 memory slice:
  recall_history  — read recent turns (for continuing a thread)
  remember_turn   — write one turn (user question or assistant reply)

Fits SCRUM-24 ConversationMessage shape:
  - roles: user | assistant only (no tool/system rows)
  - user  → PENDING question (start_question)
  - assistant → reply linked to that question (save_answer)
"""

from __future__ import annotations

import json
from typing import Any

from django.http import Http404

from apps.agent.pandu.tools.registry import ToolSpec, register
from apps.agent.pandu.tools.results import tool_error, tool_ok
from apps.conversations.models import ConversationMessage
from apps.conversations.services import save_answer, start_question
from apps.identity.ownership import owned_conversation

# How many messages Pandu can pull back in one recall.
DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 50
# Auto-injected into each agent turn so follow-ups work without a tool call.
AUTO_HISTORY_LIMIT = 8

Status = ConversationMessage.Status
Role = ConversationMessage.Role


# --- helpers -----------------------------------------------------------------


def prior_turns_for_prompt(conversation, *, limit: int = AUTO_HISTORY_LIMIT) -> list[dict[str, str]]:
    """Recent completed Q→A turns for the agent prompt (oldest → newest).

    Only ANSWERED user questions with a delivered assistant reply are included.
    PENDING / FAILED asks are skipped so the model does not see in-flight or
    failed turns. Empty content is skipped. Call this *before* saving the new
    user question so the current ask is not duplicated in the prompt.
    """
    capped = max(1, min(int(limit), MAX_HISTORY_LIMIT))
    # Newest answered questions first; stop once we have enough message rows.
    questions = (
        ConversationMessage.objects.filter(
            conversation=conversation,
            role=Role.USER,
            status=Status.ANSWERED,
        )
        .exclude(content="")
        .select_related("reply")
        .order_by("-created_at", "-id")
    )

    pairs: list[tuple[str, str]] = []
    for question in questions:
        reply = getattr(question, "reply", None)
        if reply is None:
            continue
        question_text = question.content.strip()
        reply_text = (reply.content or "").strip()
        if not question_text or not reply_text:
            continue
        pairs.append((question_text, reply_text))
        if len(pairs) * 2 >= capped:
            break

    pairs.reverse()  # oldest → newest for the prompt
    turns: list[dict[str, str]] = []
    for question_text, reply_text in pairs:
        # Keep only full Q→A pairs inside the window (never cut mid-pair).
        if len(turns) + 2 > capped:
            break
        turns.append({"role": Role.USER, "content": question_text})
        turns.append({"role": Role.ASSISTANT, "content": reply_text})
    return turns


def _positive_int(value: Any) -> int | None:
    """Accept int / digit-string ids; reject bools and junk."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _history_limit(value: Any) -> int | None:
    """Default 20; hard cap 50 so prompts stay small."""
    if value is None:
        return DEFAULT_HISTORY_LIMIT
    resolved = _positive_int(value)
    if resolved is None or resolved > MAX_HISTORY_LIMIT:
        return None
    return resolved


def _content_text(value: Any) -> str | None:
    """Normalize content to a string (objects → JSON text)."""
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return None


def _message_row(message: ConversationMessage) -> dict[str, Any]:
    """Shape returned to the model for each history row."""
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def _resolve_question(conversation, reply_to: Any) -> ConversationMessage | None:
    """Find the user question this assistant reply should attach to.

    Prefer explicit reply_to; else latest open (PENDING/FAILED) question.
    """
    if reply_to is not None:
        resolved = _positive_int(reply_to)
        if resolved is None:
            return None
        return ConversationMessage.objects.filter(
            pk=resolved,
            conversation=conversation,
            role=Role.USER,
            status__in=[Status.PENDING, Status.FAILED],
        ).first()

    # No reply_to → newest unanswered question in this chat.
    return (
        ConversationMessage.objects.filter(
            conversation=conversation,
            role=Role.USER,
            status__in=[Status.PENDING, Status.FAILED],
        )
        .order_by("-created_at", "-id")
        .first()
    )


# --- recall_history (read) ---------------------------------------------------


def recall_history(
    *,
    user,
    conversation_id: Any,
    limit: Any = None,
) -> dict[str, Any]:
    """Load recent owned chat messages, oldest → newest within the window."""
    resolved_id = _positive_int(conversation_id)
    resolved_limit = _history_limit(limit)
    if resolved_id is None:
        return tool_error("INVALID_REQUEST", "Provide a valid conversation_id.")
    if resolved_limit is None:
        return tool_error(
            "INVALID_REQUEST",
            f"Provide a limit between 1 and {MAX_HISTORY_LIMIT}.",
        )

    # Ownership: missing and foreign look the same.
    conversation = owned_conversation(user, resolved_id)
    if conversation is None:
        return tool_error("RESOURCE_NOT_FOUND")

    # Take newest N, then reverse → model sees chronological order.
    recent = list(
        ConversationMessage.objects.filter(conversation=conversation)
        .order_by("-created_at", "-id")[:resolved_limit]
    )
    recent.reverse()
    return tool_ok(messages=[_message_row(message) for message in recent])


# --- remember_turn (write) ---------------------------------------------------


def remember_turn(
    *,
    user,
    conversation_id: Any,
    role: Any,
    content: Any,
    reply_to: Any = None,
    status: Any = None,
    citations: Any = None,
    tool_trace: Any = None,
) -> dict[str, Any]:
    """Persist one chat turn on an owned conversation.

    user      → start_question (PENDING + optional auto title)
    assistant → save_answer linked to reply_to / latest open question
    """
    resolved_id = _positive_int(conversation_id)
    if resolved_id is None:
        return tool_error("INVALID_REQUEST", "Provide a valid conversation_id.")

    # DB only allows user|assistant (SCRUM-24 constraint).
    if role not in {Role.USER, Role.ASSISTANT, "user", "assistant"}:
        return tool_error(
            "INVALID_REQUEST",
            "role must be user or assistant (tool/system turns are not stored).",
        )

    text = _content_text(content)
    if text is None and role in {Role.USER, "user"}:
        return tool_error("INVALID_REQUEST", "Provide non-empty content.")
    if text is None:
        text = ""  # empty assistant reply → usually INSUFFICIENT_CONTEXT

    conversation = owned_conversation(user, resolved_id)
    if conversation is None:
        return tool_error("RESOURCE_NOT_FOUND")

    # --- user turn: save question before answering ---
    if role in {Role.USER, "user"}:
        message = start_question(conversation, text)
        return tool_ok(
            id=message.id,
            conversation_id=conversation.id,
            role=message.role,
            created_at=message.created_at.isoformat(),
        )

    # --- assistant turn: must attach to an open question ---
    question = _resolve_question(conversation, reply_to)
    if question is None:
        return tool_error(
            "INVALID_REQUEST",
            "Provide reply_to for an open user question, or ask first.",
        )

    # Status: explicit arg wins; else empty text → abstain-style reply.
    reply_status = status if status in {Status.ANSWERED, Status.INSUFFICIENT_CONTEXT} else (
        Status.INSUFFICIENT_CONTEXT if not text else Status.ANSWERED
    )
    citation_rows = citations if isinstance(citations, list) else []
    trace_rows = tool_trace if isinstance(tool_trace, list) else []

    try:
        _question, reply = save_answer(
            question,
            {
                "status": reply_status,
                "answer": text,
                "citations": citation_rows,
                "tool_trace": trace_rows,
            },
        )
    except Http404:
        # Conversation deleted while we were answering.
        return tool_error("RESOURCE_NOT_FOUND")

    return tool_ok(
        id=reply.id,
        conversation_id=conversation.id,
        role=reply.role,
        created_at=reply.created_at.isoformat(),
    )


# --- registry (Gemini sees these declarations) -------------------------------

register(
    ToolSpec(
        name="recall_history",
        description=(
            "Optional deeper lookback: load older owned conversation messages "
            "(oldest to newest). Recent turns are already in the chat prompt when "
            "available — call this only if you need more history. Never refuse to "
            "answer because this tool was unused, failed, or returned no messages. "
            "Does not include other users' chats."
        ),
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "integer",
                    "description": "Owned conversation whose history should be loaded.",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        f"Max messages to return (default {DEFAULT_HISTORY_LIMIT}, "
                        f"max {MAX_HISTORY_LIMIT})."
                    ),
                },
            },
            "required": ["conversation_id"],
            "additionalProperties": False,
        },
        handler=recall_history,
        mutates=False,
    )
)

register(
    ToolSpec(
        name="remember_turn",
        description=(
            "Persist one chat turn on an owned conversation. "
            "role=user saves a PENDING question; role=assistant saves the reply "
            "linked to reply_to or the latest open question. "
            "Only user/assistant roles are supported."
        ),
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "integer",
                    "description": "Owned conversation to write into.",
                },
                "role": {
                    "type": "string",
                    "enum": ["user", "assistant"],
                    "description": "Who said this turn.",
                },
                "content": {
                    "type": "string",
                    "description": "Message text, or a JSON object/array stored as text.",
                },
                "reply_to": {
                    "type": "integer",
                    "description": (
                        "User message id this assistant reply answers. "
                        "Optional; defaults to the latest open question."
                    ),
                },
                "status": {
                    "type": "string",
                    "enum": ["ANSWERED", "INSUFFICIENT_CONTEXT"],
                    "description": "Assistant reply status (default ANSWERED when content is non-empty).",
                },
                "citations": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional citation objects for an assistant reply.",
                },
                "tool_trace": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional tool-trace entries for an assistant reply.",
                },
            },
            "required": ["conversation_id", "role", "content"],
            "additionalProperties": False,
        },
        handler=remember_turn,
        mutates=True,
    )
)
