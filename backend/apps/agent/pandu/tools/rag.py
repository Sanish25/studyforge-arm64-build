"""Grounded Q&A tools: wrap knowledge retrieval and conversation questions."""

from __future__ import annotations

from typing import Any

from django.http import Http404
from rest_framework.exceptions import NotAuthenticated

from apps.agent.pandu.tools.registry import ToolSpec, register
from apps.agent.pandu.tools.results import tool_error, tool_ok
from apps.identity.ownership import owned_conversation
from apps.knowledge.llm import (
    InvalidCitation,
    InvalidLLMOutput,
    LLMError,
    _prepare,
    get_client,
    validate_answer,
)
from apps.knowledge.retrieval import retrieve_chunks_for_documents
from apps.knowledge.services import RAGServiceError, answer_question

RAG_FAILED_MESSAGE = "The question could not be answered right now. Please try again."
MAX_TOP_K = 20


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


def _nonempty_question(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    question = value.strip()
    return question or None


def _passage_rows(passages: Any) -> list[dict[str, Any]] | None:
    """Accept tool shape (text/page) or internal shape (content/page_number)."""
    if not isinstance(passages, list):
        return None
    rows: list[dict[str, Any]] = []
    for item in passages:
        if not isinstance(item, dict):
            return None
        chunk_id = _positive_int(item.get("chunk_id"))
        document_id = _positive_int(item.get("document_id"))
        page = _positive_int(item.get("page", item.get("page_number")))
        text = item.get("text", item.get("content"))
        if chunk_id is None or document_id is None or page is None:
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        rows.append(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "page_number": page,
                "content": text,
            }
        )
    return rows


def _map_passages(passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": passage["chunk_id"],
            "document_id": passage["document_id"],
            "page": passage["page_number"],
            "text": passage["content"],
            "score": passage.get("score"),
        }
        for passage in passages
    ]


def retrieve_chunks(
    *,
    user,
    question: Any,
    document_ids: Any,
    conversation_id: Any = None,
    top_k: Any = 5,
) -> dict[str, Any]:
    """Vector search only over owned READY documents."""
    resolved_question = _nonempty_question(question)
    resolved_ids = _document_ids(document_ids)
    if resolved_question is None or resolved_ids is None:
        return tool_error("INVALID_REQUEST", "Provide a question and 1–20 unique document_ids.")

    resolved_top_k = _positive_int(top_k) if top_k is not None else 5
    if resolved_top_k is None or resolved_top_k > MAX_TOP_K:
        return tool_error("INVALID_REQUEST", "Provide a valid top_k.")

    conversation = None
    if conversation_id is not None:
        resolved_conversation_id = _positive_int(conversation_id)
        if resolved_conversation_id is None:
            return tool_error("INVALID_REQUEST", "Provide a valid conversation_id.")
        conversation = owned_conversation(user, resolved_conversation_id)
        if conversation is None:
            return tool_error("RESOURCE_NOT_FOUND")

    try:
        passages = retrieve_chunks_for_documents(
            user,
            resolved_ids,
            resolved_question,
            resolved_top_k,
            conversation=conversation,
        )
    except Http404:
        return tool_error("RESOURCE_NOT_FOUND")
    except (ValueError, NotAuthenticated):
        return tool_error("INVALID_REQUEST", "Provide a question and 1–20 unique document_ids.")
    except Exception:
        return tool_error("RAG_GENERATION_FAILED", RAG_FAILED_MESSAGE)

    return tool_ok(passages=_map_passages(passages))


def ask_course_question(
    *,
    user,
    conversation_id: Any,
    question: Any,
    document_ids: Any,
) -> dict[str, Any]:
    """Main grounded Q&A path for a conversation.

    Prefer the knowledge answer_question path (citations verified). On that
    hard-fail path, fall back to retrieve + answer_from_sources with
    allow_uncited so SCRUM-23 still returns a grounded answer when excerpts
    do not exact-match.
    """
    resolved_conversation_id = _positive_int(conversation_id)
    resolved_question = _nonempty_question(question)
    resolved_ids = _document_ids(document_ids)
    if resolved_conversation_id is None or resolved_question is None or resolved_ids is None:
        return tool_error(
            "INVALID_REQUEST",
            "Provide conversation_id, a question, and 1–20 unique document_ids.",
        )

    conversation = owned_conversation(user, resolved_conversation_id)
    if conversation is None:
        return tool_error("RESOURCE_NOT_FOUND")

    try:
        result = answer_question(
            user,
            resolved_ids,
            resolved_question,
            conversation=conversation,
        )
    except Http404:
        return tool_error("RESOURCE_NOT_FOUND")
    except NotAuthenticated:
        return tool_error("AUTHENTICATION_REQUIRED")
    except RAGServiceError:
        result = None
    else:
        return tool_ok(
            status=result["status"],
            answer=result.get("answer"),
            citations=result.get("citations") or [],
        )

    try:
        passages = retrieve_chunks_for_documents(
            user,
            resolved_ids,
            resolved_question,
            conversation=conversation,
        )
    except Http404:
        return tool_error("RESOURCE_NOT_FOUND")
    except (ValueError, NotAuthenticated):
        return tool_error(
            "INVALID_REQUEST",
            "Provide conversation_id, a question, and 1–20 unique document_ids.",
        )
    except Exception:
        return tool_error("RAG_GENERATION_FAILED", RAG_FAILED_MESSAGE)

    return answer_from_sources(
        user=user,
        question=resolved_question,
        passages=_map_passages(passages),
        allow_uncited=True,
    )


def answer_from_sources(
    *,
    user,
    question: Any,
    passages: Any,
    allow_uncited: Any = True,
) -> dict[str, Any]:
    """Answer from already-retrieved passages (SCRUM-23: citations may be empty)."""
    del user  # Passages must already be authorized by retrieve_chunks in the same turn.
    resolved_question = _nonempty_question(question)
    rows = _passage_rows(passages)
    if resolved_question is None or rows is None:
        return tool_error("INVALID_REQUEST", "Provide a question and valid passages.")

    allow = True if allow_uncited is None else bool(allow_uncited)

    try:
        prepared_question, sources = _prepare(resolved_question, rows)
        if not sources:
            return tool_ok(status="INSUFFICIENT_CONTEXT", answer=None, citations=[])
        result = get_client().generate(
            prepared_question,
            [dict(source) for source in sources],
            allow_uncited=allow,
        )
        # Belt-and-suspenders when a stubbed client returns bad citations.
        try:
            result = validate_answer(result, sources)
        except InvalidCitation:
            answer = result.get("answer") if isinstance(result, dict) else None
            if allow and isinstance(answer, str) and answer.strip():
                result = {
                    "status": "ANSWERED",
                    "answer": answer.strip(),
                    "citations": [],
                }
            else:
                return tool_error("RAG_GENERATION_FAILED", RAG_FAILED_MESSAGE)
    except (LLMError, InvalidLLMOutput, ValueError):
        return tool_error("RAG_GENERATION_FAILED", RAG_FAILED_MESSAGE)

    return tool_ok(
        status=result["status"],
        answer=result.get("answer"),
        citations=result.get("citations") or [],
    )


register(
    ToolSpec(
        name="retrieve_chunks",
        description=(
            "Retrieve relevant passages from selected READY course or conversation "
            "documents. Does not write the student-facing answer."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "document_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 1,
                    "maxItems": 20,
                },
                "conversation_id": {"type": "integer"},
                "top_k": {"type": "integer"},
            },
            "required": ["question", "document_ids"],
            "additionalProperties": False,
        },
        handler=retrieve_chunks,
        mutates=False,
    )
)

register(
    ToolSpec(
        name="ask_course_question",
        description=(
            "Ask a grounded question over selected READY documents in an owned "
            "conversation. Prefer this for normal course Q&A."
        ),
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "integer"},
                "question": {"type": "string"},
                "document_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 1,
                    "maxItems": 20,
                },
            },
            "required": ["conversation_id", "question", "document_ids"],
            "additionalProperties": False,
        },
        handler=ask_course_question,
        mutates=False,
    )
)

register(
    ToolSpec(
        name="answer_from_sources",
        description=(
            "Build an answer from passages already returned by retrieve_chunks. "
            "Citations are preferred but may be empty when allow_uncited is true."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "passages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chunk_id": {"type": "integer"},
                            "document_id": {"type": "integer"},
                            "page": {"type": "integer"},
                            "text": {"type": "string"},
                        },
                        "required": ["chunk_id", "document_id", "text"],
                    },
                },
                "allow_uncited": {"type": "boolean"},
            },
            "required": ["question", "passages"],
            "additionalProperties": False,
        },
        handler=answer_from_sources,
        mutates=False,
    )
)
