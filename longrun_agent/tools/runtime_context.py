"""Runtime context shared with model tools during one agent turn."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


ClarifyCallback = Callable[[str, list[str] | None], str]


@dataclass(frozen=True)
class ToolRuntimeContext:
    session_id: str | None = None
    clarify_callback: ClarifyCallback | None = None


_TOOL_CONTEXT: ContextVar[ToolRuntimeContext] = ContextVar(
    "longrun_tool_runtime_context",
    default=ToolRuntimeContext(),
)


def get_tool_context() -> ToolRuntimeContext:
    return _TOOL_CONTEXT.get()


def set_tool_context(**kwargs: Any):
    current = _TOOL_CONTEXT.get()
    next_context = ToolRuntimeContext(
        session_id=kwargs.get("session_id", current.session_id),
        clarify_callback=kwargs.get("clarify_callback", current.clarify_callback),
    )
    return _TOOL_CONTEXT.set(next_context)


def reset_tool_context(token: Any) -> None:
    _TOOL_CONTEXT.reset(token)

