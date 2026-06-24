"""Approval checks for risky tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from longrun_agent.config import load_config


@dataclass(frozen=True)
class ApprovalDecision:
    """Approval outcome for one tool call."""

    allowed: bool
    reason: str | None = None


DANGEROUS_COMMAND_MARKERS = (
    "rm -rf",
    "remove-item",
    " rmdir ",
    "rd /s",
    "del /s",
    "format ",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "reg delete",
    "diskpart",
    "takeown ",
    "icacls ",
)


def check_approval(name: str, args: dict[str, Any], *, approved: bool = False) -> ApprovalDecision:
    """Return whether a tool call may proceed without interactive approval."""

    config = load_config()
    mode = str(config.get("approvals", {}).get("mode", "default"))
    if mode == "off":
        return ApprovalDecision(allowed=True)

    command = _command_for_tool(name, args)
    if not command:
        return ApprovalDecision(allowed=True)

    reason = detect_dangerous_command(command)
    if not reason:
        return ApprovalDecision(allowed=True)
    if approved:
        return ApprovalDecision(allowed=True)
    return ApprovalDecision(
        allowed=False,
        reason=f"Approval required for {name}: {reason}. Re-run with --approve if intentional.",
    )


def detect_dangerous_command(command: str) -> str | None:
    """Detect commands that should require explicit approval."""

    normalized = f" {command.lower()} "
    for marker in DANGEROUS_COMMAND_MARKERS:
        if marker in normalized:
            return f"dangerous command marker `{marker.strip()}`"
    return None


def _command_for_tool(name: str, args: dict[str, Any]) -> str | None:
    if name in {"terminal_run", "process_start"}:
        command = args.get("command")
        return str(command) if command is not None else ""
    return None

