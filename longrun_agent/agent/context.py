"""Turn context construction and prompt-cache handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from longrun_agent.agent.compression import CompressionResult, compress_messages_if_needed
from longrun_agent.agent.model_metadata import estimate_messages_tokens_rough, get_provider_context_length
from longrun_agent.agent.prompt import build_system_prompt
from longrun_agent.agent.transports.base import ChatMessage
from longrun_agent.state import (
    add_context_summary,
    get_latest_context_summary,
    get_prompt_snapshot,
    set_prompt_snapshot,
)


@dataclass(frozen=True)
class TurnContext:
    """Prepared context for one model request."""

    system_prompt: str
    messages: list[ChatMessage]
    prompt_created: bool
    context_files: tuple[str, ...]
    estimated_tokens: int
    context_window: int
    compressed: bool
    summary: str | None


def build_turn_context(
    *,
    session_id: str,
    history: list[dict[str, Any]],
    user_message: str,
    config: dict[str, Any],
    model: str,
    provider: str | None = None,
    workspace: Path | None = None,
) -> TurnContext:
    """Restore or create the prompt snapshot and prepare model messages."""

    snapshot = get_prompt_snapshot(session_id)
    context_files: tuple[str, ...] = ()
    prompt_created = False

    if snapshot:
        system_prompt = str(snapshot["system_prompt"])
    else:
        built = build_system_prompt(workspace=workspace, config=config)
        system_prompt = built.system_prompt
        context_files = built.context_files
        set_prompt_snapshot(session_id, system_prompt)
        prompt_created = True

    messages = _history_to_model_messages(history)
    latest_summary = get_latest_context_summary(session_id)
    if latest_summary and not _has_summary_message(messages):
        messages.insert(
            0,
            {
                "role": "system",
                "content": "Context summary from previous compression:\n"
                + str(latest_summary["summary"]),
            },
        )

    request_messages: list[ChatMessage] = [
        {"role": "system", "content": system_prompt},
        *messages,
        {"role": "user", "content": user_message},
    ]

    context_cfg = config.get("context", {})
    context_window = get_provider_context_length(
        model,
        provider=provider,
        configured_default=int(context_cfg.get("max_tokens", 128000)),
    )
    threshold = int(context_cfg.get("compression_threshold_tokens", int(context_window * 0.75)))
    tail_messages = int(context_cfg.get("tail_messages", 12))

    compression = compress_messages_if_needed(
        request_messages,
        threshold_tokens=threshold,
        tail_messages=tail_messages,
    )
    if compression.compressed and compression.summary:
        add_context_summary(
            session_id,
            compression.summary,
            source_message_count=len(history),
        )

    final_messages = repair_tool_call_pairs(compression.messages)

    return TurnContext(
        system_prompt=system_prompt,
        messages=final_messages,
        prompt_created=prompt_created,
        context_files=context_files,
        estimated_tokens=estimate_messages_tokens_rough(final_messages),
        context_window=context_window,
        compressed=compression.compressed,
        summary=compression.summary,
    )


def inspect_session_context(
    *,
    session_id: str,
    history: list[dict[str, Any]],
    config: dict[str, Any],
    model: str,
    provider: str | None = None,
) -> dict[str, int | str | bool | None]:
    """Return context metadata for CLI inspection."""

    snapshot = get_prompt_snapshot(session_id)
    messages = _history_to_model_messages(history)
    if snapshot:
        messages = [{"role": "system", "content": str(snapshot["system_prompt"])}, *messages]
    estimate = estimate_messages_tokens_rough(messages)
    context_window = get_provider_context_length(
        model,
        provider=provider,
        configured_default=int(config.get("context", {}).get("max_tokens", 128000)),
    )
    latest_summary = get_latest_context_summary(session_id)
    return {
        "session_id": session_id,
        "has_prompt_snapshot": bool(snapshot),
        "system_prompt_chars": len(str(snapshot["system_prompt"])) if snapshot else 0,
        "message_count": len(history),
        "estimated_tokens": estimate,
        "context_window": context_window,
        "latest_summary_id": int(latest_summary["id"]) if latest_summary else None,
    }


def manual_compress_session(
    *,
    session_id: str,
    history: list[dict[str, Any]],
    config: dict[str, Any],
    model: str,
) -> CompressionResult:
    """Force a deterministic compression summary for the current session."""

    snapshot = get_prompt_snapshot(session_id)
    if not snapshot:
        built = build_system_prompt(config=config)
        snapshot = set_prompt_snapshot(session_id, built.system_prompt)

    messages: list[ChatMessage] = [
        {"role": "system", "content": str(snapshot["system_prompt"])},
        *_history_to_model_messages(history),
    ]
    threshold = 1
    tail_messages = int(config.get("context", {}).get("tail_messages", 12))
    result = compress_messages_if_needed(
        messages,
        threshold_tokens=threshold,
        tail_messages=tail_messages,
    )
    if result.summary:
        add_context_summary(session_id, result.summary, source_message_count=len(history))
    repaired = repair_tool_call_pairs(result.messages)
    return CompressionResult(
        messages=repaired,
        summary=result.summary,
        compressed=result.compressed,
        estimated_tokens_before=result.estimated_tokens_before,
        estimated_tokens_after=estimate_messages_tokens_rough(repaired),
    )


def _history_to_model_messages(history: list[dict[str, Any]]) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for row in history:
        role = str(row["role"])
        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        if role == "tool":
            tool_call_id = str(metadata.get("tool_call_id", ""))
            if not tool_call_id:
                continue
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": str(row["content"]),
                }
            )
            continue

        if role not in {"system", "user", "assistant"}:
            continue
        message: ChatMessage = {"role": role, "content": str(row["content"])}
        if role == "assistant":
            tool_calls = metadata.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                message["tool_calls"] = [_to_chat_tool_call(call) for call in tool_calls if isinstance(call, dict)]
                if not message["content"]:
                    message["content"] = None
        messages.append(message)
    return messages


def repair_tool_call_pairs(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Remove tool-call fragments made invalid by compression boundaries.

    Chat Completions and Responses both require a tool output to follow a
    retained assistant tool call. Context compression can otherwise keep a tail
    that starts with orphan tool outputs after the assistant call was summarized.
    """

    repaired: list[ChatMessage] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        role = str(message.get("role", ""))
        if role == "tool":
            index += 1
            continue

        if role != "assistant" or not isinstance(message.get("tool_calls"), list):
            repaired.append(message)
            index += 1
            continue

        tool_calls = [call for call in message.get("tool_calls", []) if isinstance(call, dict)]
        call_ids = [_tool_call_id(call) for call in tool_calls]
        call_ids = [call_id for call_id in call_ids if call_id]
        if not call_ids:
            repaired.append(_assistant_without_tool_calls(message))
            index += 1
            continue

        tool_messages: list[ChatMessage] = []
        cursor = index + 1
        seen: set[str] = set()
        while cursor < len(messages) and str(messages[cursor].get("role", "")) == "tool":
            tool_call_id = str(messages[cursor].get("tool_call_id", "")).strip()
            if tool_call_id in call_ids:
                tool_messages.append(messages[cursor])
                seen.add(tool_call_id)
            cursor += 1

        if set(call_ids).issubset(seen):
            repaired.append(message)
            repaired.extend(tool_messages)
        else:
            fallback = _assistant_without_tool_calls(message)
            if str(fallback.get("content") or "").strip():
                repaired.append(fallback)
        index = cursor

    return repaired


def _has_summary_message(messages: list[ChatMessage]) -> bool:
    return any(str(message.get("content") or "").startswith("Context summary") for message in messages)


def _to_chat_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(call.get("id", "")),
        "type": "function",
        "function": {
            "name": str(call.get("name", "")),
            "arguments": str(call.get("arguments", "{}")),
        },
    }


def _tool_call_id(call: dict[str, Any]) -> str:
    return str(call.get("id", "")).strip()


def _assistant_without_tool_calls(message: ChatMessage) -> ChatMessage:
    return {
        "role": "assistant",
        "content": str(message.get("content") or ""),
    }
