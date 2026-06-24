"""Shared transport types for model calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

ChatMessage = dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """One normalized model-requested tool call."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelResponse:
    """Normalized model response."""

    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    raw: Any | None = None


class ChatTransport(Protocol):
    """Transport interface used by the agent loop."""

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse:
        """Return one assistant response for the supplied messages."""
