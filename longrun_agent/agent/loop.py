"""Conversation loop for model calls and tool-call iteration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from longrun_agent.agent.tool_executor import ToolExecutionResult, execute_tool_call
from longrun_agent.agent.transports.base import ChatMessage, ChatTransport, ModelResponse, ToolCall
from longrun_agent.hooks import run_hooks
from longrun_agent.tools.registry import registry


@dataclass(frozen=True)
class PersistedLoopMessage:
    """One message produced by the loop that should be stored after the run."""

    role: str
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class LoopResult:
    """Final loop result plus generated durable messages."""

    final_response: str
    messages_to_persist: tuple[PersistedLoopMessage, ...]
    iterations: int
    stopped_by_limit: bool
    tools_used: tuple[str, ...] = ()


def run_no_tool_turn(
    *,
    transport: ChatTransport,
    messages: list[ChatMessage],
    max_iterations: int,
) -> ModelResponse:
    """Run one assistant turn before tool calling exists.

    The `max_iterations` parameter is accepted now because the full agent loop
    will use it later. In Stage 3, no tools exist, so one model request is the
    whole turn.
    """

    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    if not messages:
        raise ValueError("messages cannot be empty")
    return transport.complete(messages)


def run_tool_loop(
    *,
    transport: ChatTransport,
    messages: list[ChatMessage],
    max_iterations: int,
    approved_tools: bool = False,
    event_handler: Callable[[dict[str, Any]], None] | None = None,
) -> LoopResult:
    """Run model/tool iterations through the central tool executor."""

    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    if not messages:
        raise ValueError("messages cannot be empty")

    working_messages = list(messages)
    persisted: list[PersistedLoopMessage] = []
    tools_used: list[str] = []
    tool_definitions = registry.get_definitions()

    for iteration in range(1, max_iterations + 1):
        llm_payload = {"messages": working_messages, "tools": tool_definitions, "iteration": iteration}
        _emit(
            event_handler,
            {
                "type": "llm_start",
                "iteration": iteration,
                "tool_count": len(tool_definitions),
                "message_count": len(working_messages),
            },
        )
        run_hooks("pre_llm_call", llm_payload)
        payload_messages = llm_payload.get("messages", working_messages)
        payload_tools = llm_payload.get("tools", tool_definitions)
        if not isinstance(payload_messages, list):
            raise ValueError("pre_llm_call hook changed messages to a non-list")
        if not isinstance(payload_tools, list):
            raise ValueError("pre_llm_call hook changed tools to a non-list")
        working_messages = payload_messages
        response = transport.complete(working_messages, tools=payload_tools)
        _emit(
            event_handler,
            {
                "type": "llm_complete",
                "iteration": iteration,
                "tool_calls": [call.name for call in response.tool_calls],
                "content_chars": len(response.content or ""),
                "content": response.content or "",
            },
        )
        run_hooks(
            "post_llm_call",
            {
                "messages": working_messages,
                "tools": payload_tools,
                "iteration": iteration,
                "response": response,
            },
        )
        if not response.tool_calls:
            final_text = response.content.strip()
            persisted.append(
                PersistedLoopMessage(
                    role="assistant",
                    content=final_text,
                    metadata={},
                )
            )
            return LoopResult(
                final_response=final_text,
                messages_to_persist=tuple(persisted),
                iterations=iteration,
                stopped_by_limit=False,
                tools_used=tuple(tools_used),
            )

        assistant_message = _assistant_tool_message(response)
        working_messages.append(assistant_message)
        persisted.append(
            PersistedLoopMessage(
                role="assistant",
                content=response.content,
                metadata={"tool_calls": [_persisted_tool_call(call) for call in response.tool_calls]},
            )
        )

        for tool_call in response.tool_calls:
            tools_used.append(tool_call.name)
            _emit(
                event_handler,
                {
                    "type": "tool_start",
                    "iteration": iteration,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            )
            tool_result = _execute_model_tool_call(tool_call, approved=approved_tools)
            _emit(
                event_handler,
                {
                    "type": "tool_complete",
                    "iteration": iteration,
                    "name": tool_call.name,
                    "ok": tool_result.ok,
                    "error": tool_result.error,
                    "result": tool_result.result,
                },
            )
            tool_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result.to_json(),
            }
            working_messages.append(tool_message)
            persisted.append(
                PersistedLoopMessage(
                    role="tool",
                    content=tool_result.to_json(),
                    metadata={"tool_call_id": tool_call.id, "name": tool_call.name},
                )
            )

    final_text = (
        "Stopped after reaching the maximum tool-call iterations. "
        "The last tool results were persisted for the next turn."
    )
    persisted.append(PersistedLoopMessage(role="assistant", content=final_text, metadata={}))
    return LoopResult(
        final_response=final_text,
        messages_to_persist=tuple(persisted),
        iterations=max_iterations,
        stopped_by_limit=True,
        tools_used=tuple(tools_used),
    )


def _execute_model_tool_call(tool_call: ToolCall, *, approved: bool) -> ToolExecutionResult:
    try:
        parsed = json.loads(tool_call.arguments or "{}")
    except json.JSONDecodeError as exc:
        return ToolExecutionResult(
            name=tool_call.name,
            ok=False,
            error=f"Invalid tool JSON arguments: {exc}",
        )
    if not isinstance(parsed, dict):
        return ToolExecutionResult(
            name=tool_call.name,
            ok=False,
            error="Tool JSON arguments must decode to an object",
        )
    return execute_tool_call(tool_call.name, parsed, approved=approved)


def _emit(event_handler: Callable[[dict[str, Any]], None] | None, event: dict[str, Any]) -> None:
    if event_handler is None:
        return
    try:
        event_handler(event)
    except Exception:
        return


def _assistant_tool_message(response: ModelResponse) -> ChatMessage:
    return {
        "role": "assistant",
        "content": response.content or None,
        "tool_calls": [_chat_tool_call(call) for call in response.tool_calls],
    }


def _chat_tool_call(call: ToolCall) -> dict[str, Any]:
    return {
        "id": call.id,
        "type": "function",
        "function": {
            "name": call.name,
            "arguments": call.arguments,
        },
    }


def _persisted_tool_call(call: ToolCall) -> dict[str, str]:
    return {
        "id": call.id,
        "name": call.name,
        "arguments": call.arguments,
    }
