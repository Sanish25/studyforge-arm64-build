"""Agent LLM adapters for the Pandu tool loop (Gemini or scripted fake)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from google import genai
from google.genai import errors, types

from apps.agent.pandu.schema import REPLY_JSON_SCHEMA
from apps.agent.pandu.tools.registry import ToolSpec

DEFAULT_MODEL = "gemini-flash-latest"


class AgentLLMError(Exception):
    """Provider failure for the Pandu agent loop."""


class InvalidAgentOutput(AgentLLMError):
    """Malformed or incomplete agent model output."""


@dataclass(frozen=True)
class ToolCallRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    # Gemini may require this on the next turn after a function call.
    thought_signature: Any = None


@dataclass(frozen=True)
class AgentStep:
    kind: Literal["tool_calls", "message"]
    tool_calls: tuple[ToolCallRequest, ...] = ()
    text: str | None = None


# Gemini FunctionDeclaration parameters accept a JSON-Schema subset only.
# Unknown keys (esp. additionalProperties) cause 400 INVALID_ARGUMENT and
# abort every agent turn, including greetings that never call the tool.
_GEMINI_SCHEMA_KEYS = frozenset(
    {
        "type",
        "description",
        "properties",
        "required",
        "items",
        "enum",
        "nullable",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "format",
    }
)


def _gemini_safe_schema(node: Any) -> Any:
    """Recursively keep only Gemini-supported schema fields and coerce enums."""
    if isinstance(node, list):
        return [_gemini_safe_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key not in _GEMINI_SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {name: _gemini_safe_schema(schema) for name, schema in value.items()}
        elif key == "items":
            cleaned[key] = _gemini_safe_schema(value)
        else:
            cleaned[key] = value

    enum = cleaned.get("enum")
    if isinstance(enum, list):
        original_enum = node.get("enum")
        cleaned["enum"] = [item if isinstance(item, str) else str(item) for item in enum]
        # google-genai enum values are strings.
        if (
            cleaned.get("type") == "integer"
            and isinstance(original_enum, list)
            and original_enum
            and all(isinstance(item, int) for item in original_enum)
        ):
            cleaned["type"] = "string"

    # Gemini requires array schemas to declare items.
    if cleaned.get("type") == "array" and "items" not in cleaned:
        cleaned["items"] = {"type": "object"}
    return cleaned


def _gemini_safe_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Copy tool JSON Schema into a Gemini-safe FunctionDeclaration shape."""
    return _gemini_safe_schema(parameters)


def tool_declarations(tool_specs: list[ToolSpec]) -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=spec.name,
            description=spec.description,
            parameters=_gemini_safe_parameters(spec.parameters),
        )
        for spec in tool_specs
    ]
    if not declarations:
        return []
    return [types.Tool(function_declarations=declarations)]


class ScriptedAgentLLM:
    """Test double: returns a fixed sequence of tool calls / final messages."""

    name = "scripted"

    def __init__(self, steps: list[AgentStep]):
        self._steps = list(steps)
        self._index = 0

    def step(self, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> AgentStep:
        del messages, tools
        if self._index >= len(self._steps):
            return AgentStep(
                kind="message",
                text=json.dumps(
                    {
                        "type": "message",
                        "status": "ok",
                        "text": "Done.",
                        "citations": [],
                        "tool_trace": [],
                    }
                ),
            )
        step = self._steps[self._index]
        self._index += 1
        return step


class GeminiAgentLLM:
    """Native Gemini turn that may return function calls or a final JSON message."""

    def __init__(self, client=None):
        self.name = os.environ.get("PANDU_AGENT_MODEL", DEFAULT_MODEL).strip()
        if not self.name:
            raise AgentLLMError("PANDU_AGENT_MODEL is not set")
        if client is not None:
            self.client = client
            return
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise AgentLLMError("GEMINI_API_KEY is not set")
        self.client = genai.Client(
            api_key=key,
            vertexai=False,
            http_options=types.HttpOptions(
                timeout=60_000,
                retry_options=types.HttpRetryOptions(attempts=2),
            ),
        )

    def step(self, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> AgentStep:
        system = "\n\n".join(
            m["content"] for m in messages if m.get("role") == "system" and isinstance(m.get("content"), str)
        )
        contents = _messages_to_contents(messages)
        config_kwargs: dict[str, Any] = {
            "system_instruction": system or None,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
            "max_output_tokens": 8_192,
        }
        gemini_tools = tool_declarations(tools)
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools
        else:
            # Final answer turn: force the JSON envelope schema.
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = REPLY_JSON_SCHEMA

        try:
            response = self.client.models.generate_content(
                model=self.name,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except (errors.APIError, httpx.HTTPError):
            raise AgentLLMError("Gemini generation is temporarily unavailable. Try again shortly.") from None

        try:
            if not response.candidates or len(response.candidates) != 1:
                raise ValueError("Expected one candidate")
            candidate = response.candidates[0]
            parts = candidate.content.parts if candidate.content else None
            if not parts:
                raise ValueError("Empty response")

            calls = tuple(
                ToolCallRequest(
                    name=part.function_call.name,
                    args=dict(part.function_call.args or {}),
                    id=getattr(part.function_call, "id", None),
                    thought_signature=getattr(part, "thought_signature", None),
                )
                for part in parts
                if part.function_call is not None and part.function_call.name
            )
            if calls:
                return AgentStep(kind="tool_calls", tool_calls=calls)

            text = "".join(p.text for p in parts if p.text and not getattr(p, "thought", None))
            if not text.strip():
                raise ValueError("Empty text response")
            return AgentStep(kind="message", text=_strip_markdown_fence(text))
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidAgentOutput("Gemini returned an invalid or incomplete response.") from exc


def get_agent_llm(client=None):
    backend = os.environ.get("PANDU_AGENT_BACKEND", "fake").strip().lower()
    if backend == "fake":
        # Offline default: no tools, safe clarify-style envelope.
        return ScriptedAgentLLM(
            [
                AgentStep(
                    kind="message",
                    text=json.dumps(
                        {
                            "type": "message",
                            "status": "clarify",
                            "text": "Tell me what you'd like help with for this course.",
                            "citations": [],
                            "tool_trace": [],
                        }
                    ),
                )
            ]
        )
    if backend == "gemini":
        return GeminiAgentLLM(client=client)
    raise AgentLLMError("PANDU_AGENT_BACKEND must be fake or gemini.")


def _strip_markdown_fence(text: str) -> str:
    """Unwrap ```json ... ``` so enforce_reply can parse model text."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _messages_to_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
    contents: list[types.Content] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "user":
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=str(message.get("content", "")))],
                )
            )
            continue
        if role == "assistant":
            parts = []
            for call in message.get("tool_calls") or []:
                part = types.Part.from_function_call(
                    name=call["name"],
                    args=call.get("args") or {},
                )
                signature = call.get("thought_signature")
                if signature is not None:
                    part = part.model_copy(update={"thought_signature": signature})
                parts.append(part)
            text = message.get("content")
            if isinstance(text, str) and text:
                parts.append(types.Part.from_text(text=text))
            if parts:
                contents.append(types.Content(role="model", parts=parts))
            continue
        if role == "tool":
            name = message.get("name") or "unknown"
            response = message.get("content")
            if not isinstance(response, dict):
                response = {"result": response}
            call_id = message.get("tool_call_id") or str(uuid.uuid4())
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=name,
                            response=response,
                        )
                    ],
                )
            )
            del call_id
    return contents
