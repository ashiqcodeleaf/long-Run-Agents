"""Guardrail checks for tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from longrun_agent.config import auth_path, env_path
from longrun_agent.tools.delegate import current_subagent_depth


@dataclass(frozen=True)
class GuardrailDecision:
    """Guardrail outcome for one tool call."""

    allowed: bool
    reason: str | None = None


def evaluate_tool_call(name: str, args: dict[str, Any]) -> GuardrailDecision:
    """Block tool calls that violate fixed MVP safety rules."""

    if current_subagent_depth() > 0 and name in {"memory_set", "memory_delete"}:
        return GuardrailDecision(False, "Subagents cannot mutate user memory by default")

    if name in {"file_read", "file_write", "file_patch"}:
        path = args.get("path")
        if not path:
            return GuardrailDecision(False, f"{name} requires path")
        sensitive = _sensitive_path_reason(Path(str(path)))
        if sensitive:
            return GuardrailDecision(False, sensitive)

    if name in {"terminal_run", "process_start"}:
        command = str(args.get("command", ""))
        lowered = command.lower()
        if "auth.json" in lowered or ".env" in lowered:
            return GuardrailDecision(False, "Command references LongRun credential files")

    if name == "execute_code":
        code = str(args.get("code", ""))
        lowered = code.lower()
        if "auth.json" in lowered or ".env" in lowered:
            return GuardrailDecision(False, "Code references LongRun credential files")

    return GuardrailDecision(True)


def _sensitive_path_reason(path: Path) -> str | None:
    resolved = path.expanduser().resolve()
    sensitive_paths = (auth_path().resolve(), env_path().resolve())
    for sensitive in sensitive_paths:
        if resolved == sensitive:
            return f"Refusing to access sensitive LongRun file: {resolved}"
    return None
