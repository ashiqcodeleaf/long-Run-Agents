"""OpenAI Chat Completions transport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from longrun_agent.agent.transports.base import ChatMessage, ModelResponse, ToolCall
from longrun_agent.auth import require_openai_api_key


@dataclass
class OpenAIChatTransport:
    """Small no-tool transport for Stage 2/3."""

    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The `openai` package is not installed. Install project dependencies first."
            ) from exc

        client = OpenAI(api_key=self.api_key or require_openai_api_key(), base_url=self.base_url)
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            request["tools"] = [_to_chat_tool(tool) for tool in tools]
            request["tool_choice"] = "auto"
        response = client.chat.completions.create(**request)
        message = response.choices[0].message
        content = message.content or ""
        return ModelResponse(
            content=content,
            tool_calls=_extract_tool_calls(message),
            raw=response,
        )


def _to_chat_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
        },
    }


def _extract_tool_calls(message: Any) -> tuple[ToolCall, ...]:
    calls = getattr(message, "tool_calls", None) or []
    normalized: list[ToolCall] = []
    for call in calls:
        function = getattr(call, "function", None)
        if function is None:
            continue
        name = getattr(function, "name", "")
        arguments = getattr(function, "arguments", "{}")
        call_id = getattr(call, "id", "") or f"call_{len(normalized) + 1}"
        if name:
            normalized.append(ToolCall(id=str(call_id), name=str(name), arguments=str(arguments or "{}")))
    return tuple(normalized)
