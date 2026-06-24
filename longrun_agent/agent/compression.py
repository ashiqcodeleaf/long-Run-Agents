"""Deterministic context compression scaffold."""

from __future__ import annotations

from dataclasses import dataclass

from longrun_agent.agent.model_metadata import estimate_messages_tokens_rough
from longrun_agent.agent.transports.base import ChatMessage


@dataclass(frozen=True)
class CompressionResult:
    """Result of a deterministic compression pass."""

    messages: list[ChatMessage]
    summary: str | None
    compressed: bool
    estimated_tokens_before: int
    estimated_tokens_after: int


def compress_messages_if_needed(
    messages: list[ChatMessage],
    *,
    threshold_tokens: int,
    tail_messages: int,
) -> CompressionResult:
    """Summarize old middle messages when the rough request estimate is high."""

    before = estimate_messages_tokens_rough(messages)
    if before <= threshold_tokens or len(messages) <= tail_messages + 2:
        return CompressionResult(
            messages=messages,
            summary=None,
            compressed=False,
            estimated_tokens_before=before,
            estimated_tokens_after=before,
        )

    head = messages[:1]
    tail = messages[-tail_messages:]
    middle = messages[1:-tail_messages]
    summary = build_static_summary(middle)
    summary_message: ChatMessage = {
        "role": "system",
        "content": "Context summary from earlier messages:\n" + summary,
    }
    compressed_messages = [*head, summary_message, *tail]
    after = estimate_messages_tokens_rough(compressed_messages)
    if after >= before:
        return CompressionResult(
            messages=messages,
            summary=None,
            compressed=False,
            estimated_tokens_before=before,
            estimated_tokens_after=before,
        )
    return CompressionResult(
        messages=compressed_messages,
        summary=summary,
        compressed=True,
        estimated_tokens_before=before,
        estimated_tokens_after=after,
    )


def build_static_summary(messages: list[ChatMessage], *, max_lines: int = 24) -> str:
    """Build a deterministic, non-LLM summary for the MVP compression scaffold."""

    lines = [
        "The conversation contained older messages that were compressed before the model call.",
        "Preserved facts from the older messages:",
    ]
    for message in messages[:max_lines]:
        content = " ".join(str(message.get("content") or "").split())
        if len(content) > 220:
            content = content[:217] + "..."
        lines.append(f"- {message.get('role', 'unknown')}: {content}")
    if len(messages) > max_lines:
        lines.append(f"- {len(messages) - max_lines} additional older message(s) omitted.")
    return "\n".join(lines)
