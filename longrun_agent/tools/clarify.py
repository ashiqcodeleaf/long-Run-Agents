"""Clarify tool for interactive LongRun sessions."""

from __future__ import annotations

from typing import Any

from longrun_agent.tools.runtime_context import get_tool_context

MAX_CHOICES = 4


def clarify(question: str, choices: list[str] | None = None) -> dict[str, Any]:
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question is required")
    clean_choices: list[str] | None = None
    if choices is not None:
        if not isinstance(choices, list):
            raise ValueError("choices must be an array of strings")
        clean_choices = [str(choice).strip() for choice in choices if str(choice).strip()][:MAX_CHOICES] or None

    callback = get_tool_context().clarify_callback
    if callback is None:
        return {
            "available": False,
            "question": clean_question,
            "choices": clean_choices,
            "error": "clarify is only available in the interactive CLI for now",
        }
    answer = callback(clean_question, clean_choices)
    return {
        "available": True,
        "question": clean_question,
        "choices": clean_choices,
        "answer": answer.strip(),
    }


def register_clarify_tools(registry: Any) -> None:
    try:
        registry.register(
            name="clarify",
            description=(
                "Ask the user a clarifying question from the interactive CLI. "
                "Use only when a decision meaningfully changes the work; otherwise make a reasonable assumption."
            ),
            toolset="clarify",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": MAX_CHOICES,
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
            handler=lambda args: clarify(str(args.get("question", "")), args.get("choices")),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise

