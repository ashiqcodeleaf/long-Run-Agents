"""Codex OAuth transport boundary.

The source MyAgent project talks to the Codex backend through a Responses-style
adapter. This MVP starts with the same boundary but keeps the network call
disabled until the full OAuth refresh/login flow is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from longrun_agent.agent.transports.base import ChatMessage, ModelResponse, ToolCall
from longrun_agent.auth import get_codex_runtime_credentials


@dataclass
class CodexResponsesTransport:
    """Stage 2 scaffold for the ChatGPT/Codex OAuth transport."""

    model: str
    base_url: str = "https://chatgpt.com/backend-api/codex"

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

        creds = get_codex_runtime_credentials()
        client = OpenAI(api_key=creds["access_token"], base_url=self.base_url)
        instructions, input_items = _to_responses_payload(messages)
        request: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": input_items,
            "store": False,
            "stream": True,
        }
        response_tools = _to_responses_tools(tools)
        if response_tools:
            request["tools"] = response_tools
            request["tool_choice"] = "auto"
            request["parallel_tool_calls"] = True

        stream = client.responses.create(
            **request,
        )
        content, response, tool_calls = _collect_stream_response(stream)
        if not content and not tool_calls:
            raise RuntimeError("Codex response did not contain assistant text or tool calls")
        return ModelResponse(content=content, tool_calls=tuple(tool_calls), raw=response)


def _to_responses_tools(tools: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Convert LongRun registry schemas to Responses function tools."""

    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": str(tool.get("description", "")),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                "strict": False,
            }
        )
    return converted


def _to_responses_payload(messages: list[ChatMessage]) -> tuple[str, list[dict[str, object]]]:
    instructions = ""
    items: list[dict[str, object]] = []
    seen_function_call_ids: set[str] = set()
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if role == "system":
            instructions = content if not instructions else instructions + "\n\n" + content
            continue
        if role == "tool":
            call_id = str(message.get("tool_call_id", "")).strip()
            if call_id and call_id in seen_function_call_ids:
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": str(content or ""),
                    }
                )
            continue
        if role not in {"user", "assistant"}:
            continue
        item_role = "user" if role == "user" else "assistant"
        item_type = "input_text" if item_role == "user" else "output_text"
        if content:
            items.append(
                {
                    "type": "message",
                    "role": item_role,
                    "content": [{"type": item_type, "text": str(content)}],
                }
            )
        tool_calls = message.get("tool_calls")
        if role == "assistant" and isinstance(tool_calls, list):
            for call in tool_calls:
                normalized = _responses_function_call_item(call)
                if normalized:
                    seen_function_call_ids.add(str(normalized["call_id"]))
                    items.append(normalized)
    return instructions, items


def _responses_function_call_item(call: Any) -> dict[str, object] | None:
    if not isinstance(call, dict):
        return None
    function = call.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    arguments = function.get("arguments", "{}")
    if isinstance(arguments, dict):
        import json

        arguments = json.dumps(arguments, ensure_ascii=False)
    elif not isinstance(arguments, str):
        arguments = str(arguments)
    call_id = str(call.get("id", "") or "").strip()
    if not call_id:
        call_id = f"call_{abs(hash((name, arguments))) & 0xFFFFFFFF:x}"
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": arguments or "{}",
    }


def _extract_response_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    output = getattr(response, "output", None)
    if isinstance(output, list):
        for item in output:
            if getattr(item, "type", None) != "message":
                continue
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for part in content:
                text = getattr(part, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
    return "\n".join(parts).strip()


def _collect_stream_response(stream: object) -> tuple[str, object | None, list[ToolCall]]:
    parts: list[str] = []
    output_items: list[object] = []
    completed: object | None = None

    for event in stream:  # type: ignore[operator]
        event_type = str(getattr(event, "type", "") or "")
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", None)
            if isinstance(delta, str):
                parts.append(delta)
            continue

        if event_type == "response.output_item.done":
            item = getattr(event, "item", None)
            if item is not None:
                output_items.append(item)
            continue

        if event_type == "response.completed":
            completed = getattr(event, "response", None) or event
            continue

        if event_type == "response.failed":
            response = getattr(event, "response", None)
            error = getattr(response, "error", None) if response is not None else None
            raise RuntimeError(f"Codex response failed: {error or event}")

    text = "".join(parts).strip()
    tool_calls = _extract_tool_calls_from_items(output_items)
    if not text and not tool_calls and completed is not None:
        text = _extract_response_text(completed)
        output = getattr(completed, "output", None)
        if isinstance(output, list):
            tool_calls = _extract_tool_calls_from_items(output)
    return text, completed, tool_calls


def _extract_tool_calls_from_items(items: list[object]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in items:
        item_type = getattr(item, "type", None)
        if item_type not in {"function_call", "custom_tool_call"}:
            continue
        name = getattr(item, "name", "")
        if not isinstance(name, str) or not name.strip():
            continue
        arguments = getattr(item, "arguments", None)
        if arguments is None:
            arguments = getattr(item, "input", "{}")
        if not isinstance(arguments, str):
            import json

            arguments = json.dumps(arguments, ensure_ascii=False)
        call_id = getattr(item, "call_id", None) or getattr(item, "id", None) or f"call_{len(calls) + 1}"
        calls.append(ToolCall(id=str(call_id), name=name, arguments=arguments or "{}"))
    return calls
