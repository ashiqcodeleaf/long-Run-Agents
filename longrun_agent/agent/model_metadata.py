"""Context window and rough token estimate helpers."""

from __future__ import annotations

from longrun_agent.agent.transports.base import ChatMessage

DEFAULT_CONTEXT_TOKENS = 128000

MODEL_CONTEXT_LENGTHS: dict[str, int] = {
    "gpt-5.4": 1050000,
    "gpt-5.4-mini": 400000,
    "gpt-5.4-nano": 400000,
    "gpt-4.1": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-nano": 1047576,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
}

CODEX_CONTEXT_LENGTHS: dict[str, int] = {
    "gpt-5.4-mini": 272000,
}


def get_model_context_length(model: str, configured_default: int | None = None) -> int:
    """Return a known or configured context window."""

    return MODEL_CONTEXT_LENGTHS.get(model, configured_default or DEFAULT_CONTEXT_TOKENS)


def get_provider_context_length(
    model: str,
    *,
    provider: str | None = None,
    configured_default: int | None = None,
) -> int:
    """Return provider-aware context length."""

    if provider == "openai-codex":
        return CODEX_CONTEXT_LENGTHS.get(model, configured_default or DEFAULT_CONTEXT_TOKENS)
    return get_model_context_length(model, configured_default)


def estimate_tokens_rough(text: str) -> int:
    """Estimate token count without pulling in a tokenizer."""

    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens_rough(messages: list[ChatMessage]) -> int:
    """Estimate token count for chat messages."""

    total = 0
    for message in messages:
        total += 4
        total += estimate_tokens_rough(str(message.get("role", "")))
        total += estimate_tokens_rough(str(message.get("content") or ""))
        tool_calls = message.get("tool_calls")
        if tool_calls:
            total += estimate_tokens_rough(str(tool_calls))
        tool_call_id = message.get("tool_call_id")
        if tool_call_id:
            total += estimate_tokens_rough(str(tool_call_id))
    return total + 3
