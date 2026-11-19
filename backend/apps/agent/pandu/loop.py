"""Gemini ↔ tool loop for Pandu.

Runtime flow (see docs/architecture/pandu-agent.md §4):
user message → scope check → model chooses tools → handlers run in Django →
evidence gate → final JSON reply.
"""

from __future__ import annotations

import json
from typing import Any

import apps.agent.pandu.tools  # noqa: F401  — register tool modules
from apps.agent.pandu.llm import AgentLLMError, ToolCallRequest, get_agent_llm
from apps.agent.pandu.prompts import PANDU_SYSTEM_PROMPT, REPLY_REPAIR_PROMPT
from apps.agent.pandu.schema import REPLY_JSON_SCHEMA, enforce_reply, error_reply
from apps.agent.pandu.scope import check_scope
from apps.agent.pandu.tools.registry import all_tools, get_tool
from apps.agent.pandu.tools.results import tool_error

# Hard stop per user message so Gemini ↔ tools cannot run forever.
MAX_TOOL_CALLS_PER_TURN = 10

_LOOP_SYSTEM = (
    PANDU_SYSTEM_PROMPT
    + "\n\n"
    + "When you are done using tools, respond with ONLY a JSON object matching "
    "the Pandu reply envelope: type=message, status (ok|clarify|abstain|error), "
    "text, citations (array, may be empty), tool_trace (array, may be empty). "
    "Prefer ask_course_question for normal material questions. Do not run both "
    "ask_course_question and retrieve_chunks/answer_from_sources in the same turn."
)


def run_pandu_turn(
    *,
    user,
    message: str,
    context: dict[str, Any] | None = None,
    llm=None,
    classifier=None,
) -> dict[str, Any]:
    """Run one agent turn and return the student-facing JSON envelope."""
    context = dict(context or {})
    if user is None or not getattr(user, "is_authenticated", False):
        return error_reply("Authentication is required.")

    try:
        decision = check_scope(
            user=user, message=message, context=context, classifier=classifier
        )
    except Exception:
        return _reply(
            "clarify",
            "I need a bit more detail about what you'd like help with.",
        )

    if decision.label == "OUT_OF_SCOPE":
        return _reply(
            "abstain",
            "That request is outside my current capabilities. I can help with "
            "course materials, academic questions, notes, tasks, and quizzes. "
            "Feel free to ask me anything related to your studies!",
        )

    # Architecture §4.1: material Q with no selection → select/upload clarify.
    # Check before generic UNCLEAR so needs_documents is not swallowed.
    document_ids = context.get("document_ids") or []
    if decision.needs_documents and not document_ids:
        return _reply(
            "clarify",
            "Select or upload at least one READY material, then ask again.",
        )

    if decision.label == "UNCLEAR":
        return _reply(
            "clarify",
            "Could you clarify what you'd like help with for this course?",
        )

    active_llm = llm if llm is not None else get_agent_llm()
    tool_specs = all_tools()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _LOOP_SYSTEM},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "message": message,
                    # course_id / conversation_id stay server-side (tool auto-fill)
                    # so greetings do not parrot "Course ID: …".
                    "course_name": context.get("course_name"),
                    "document_ids": document_ids,
                }
            ),
        },
    ]

    tool_trace: list[dict[str, Any]] = []
    tool_results: list[tuple[str, dict[str, Any]]] = []
    tool_calls_used = 0
    final_text: str | None = None

    try:
        while True:
            allow_tools = tool_calls_used < MAX_TOOL_CALLS_PER_TURN
            step = active_llm.step(messages, tool_specs if allow_tools else [])
            if step.kind == "message":
                final_text = step.text
                break

            if not allow_tools or not step.tool_calls:
                break

            assistant_calls = []
            response_parts = []
            for call in step.tool_calls:
                if tool_calls_used >= MAX_TOOL_CALLS_PER_TURN:
                    break
                result = _execute_tool(user=user, call=call, context=context)
                tool_calls_used += 1
                tool_results.append((call.name, result))
                tool_trace.append(
                    {
                        "name": call.name,
                        "ok": bool(isinstance(result, dict) and result.get("ok")),
                    }
                )
                call_id = call.id or f"call_{tool_calls_used}"
                assistant_call = {
                    "id": call_id,
                    "name": call.name,
                    "args": dict(call.args or {}),
                }
                if call.thought_signature is not None:
                    assistant_call["thought_signature"] = call.thought_signature
                assistant_calls.append(assistant_call)
                response_parts.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": call.name,
                        "content": result,
                    }
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": assistant_calls,
                }
            )
            messages.extend(response_parts)

            if tool_calls_used >= MAX_TOOL_CALLS_PER_TURN:
                # One forced finalization turn without tools.
                finalize = active_llm.step(messages, [])
                if finalize.kind == "message":
                    final_text = finalize.text
                break

        evidence = _evidence_gate(tool_results)
        if evidence is not None:
            evidence["tool_trace"] = tool_trace
            return enforce_reply(evidence)

        if final_text is None:
            return _reply(
                "clarify",
                "I couldn't finish that in one go. Try asking again with a smaller "
                "request, or split it into a follow-up.",
                tool_trace=tool_trace,
            )

        def repair(payload: Any, reason: str) -> Any:
            del reason
            return active_llm.step(
                [
                    {"role": "system", "content": REPLY_REPAIR_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"invalid_payload": payload, "schema": REPLY_JSON_SCHEMA}
                        ),
                    },
                ],
                [],
            ).text

        reply = enforce_reply(final_text, repair=repair)
        if not reply.get("tool_trace"):
            reply = {**reply, "tool_trace": tool_trace}
        return reply
    except (AgentLLMError, TypeError, ValueError):
        return error_reply()


def _execute_tool(*, user, call: ToolCallRequest, context: dict[str, Any]) -> dict[str, Any]:
    spec = get_tool(call.name)
    if spec is None:
        return tool_error("INVALID_REQUEST", f"Unknown tool: {call.name}")

    raw_args = dict(call.args or {})
    raw_args.pop("user", None)

    # Trusted client context wins over model-supplied ids. Gemini often invents
    # a conversation_id after we stopped putting it in the user payload; that
    # made ask_course_question / retrieve_chunks return RESOURCE_NOT_FOUND.
    properties = spec.parameters.get("properties", {})
    if "course_id" in properties and context.get("course_id") is not None:
        raw_args["course_id"] = context["course_id"]
    if "conversation_id" in properties and context.get("conversation_id") is not None:
        raw_args["conversation_id"] = context["conversation_id"]
    if "document_ids" in properties and context.get("document_ids"):
        raw_args["document_ids"] = context["document_ids"]

    try:
        result = spec.handler(user=user, **raw_args)
    except TypeError:
        return tool_error("INVALID_REQUEST", "Invalid tool arguments.")
    except Exception:
        return tool_error(
            "INVALID_REQUEST",
            "The tool request could not be completed.",
        )
    if not isinstance(result, dict):
        return tool_error("INVALID_REQUEST", "Tool returned an invalid result.")
    return result


def _evidence_gate(tool_results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    """After RAG tools, empty evidence must not become an invented answer."""
    for name, result in tool_results:
        if not isinstance(result, dict) or not result.get("ok"):
            continue
        if name == "retrieve_chunks" and not result.get("passages"):
            return {
                "type": "message",
                "status": "abstain",
                "text": "I couldn't find enough in your selected materials to answer that.",
                "citations": [],
                "tool_trace": [],
            }
        if name in {"ask_course_question", "answer_from_sources"} and result.get(
            "status"
        ) == "INSUFFICIENT_CONTEXT":
            return {
                "type": "message",
                "status": "abstain",
                "text": "I couldn't find enough in your selected materials to answer that.",
                "citations": [],
                "tool_trace": [],
            }
    return None


def _reply(status: str, text: str, *, tool_trace: list | None = None) -> dict[str, Any]:
    return enforce_reply(
        {
            "type": "message",
            "status": status,
            "text": text,
            "citations": [],
            "tool_trace": tool_trace or [],
        }
    )
