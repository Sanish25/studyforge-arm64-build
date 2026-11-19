"""Tool name → Gemini declaration + Django handler.

Handlers receive the authenticated JWT user from the request context, never from
model-supplied identity args. Registry is empty until tools are registered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    mutates: bool = False


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in _REGISTRY:
        raise ValueError(f"Tool already registered: {spec.name}")
    _REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def clear_registry() -> None:
    """Test helper — removes all registered tools."""
    _REGISTRY.clear()
