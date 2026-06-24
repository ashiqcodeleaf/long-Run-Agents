"""Central tool execution path.

Stage 5 only has registry dispatch. Later stages will insert hooks, guardrails,
approvals, checkpoints, and file-state tracking here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from longrun_agent.hooks import run_hooks
from longrun_agent.safety.approval import check_approval
from longrun_agent.safety.checkpoints import checkpoint_for_tool
from longrun_agent.safety.guardrails import evaluate_tool_call
from longrun_agent.tools import file_state
from longrun_agent.tools.registry import registry


@dataclass(frozen=True)
class ToolExecutionResult:
    """Normalized tool execution result."""

    name: str
    ok: bool
    result: Any | None = None
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "name": self.name,
                "ok": self.ok,
                "result": self.result,
                "error": self.error,
            },
            indent=2,
            sort_keys=True,
        )


def execute_tool_call(name: str, args: dict[str, Any], *, approved: bool = False) -> ToolExecutionResult:
    """Execute one tool through the central path."""

    if not isinstance(args, dict):
        return ToolExecutionResult(name=name, ok=False, error="Tool arguments must be an object")

    try:
        pre_payload = {"name": name, "args": args}
        run_hooks("pre_tool_call", pre_payload)
        args = pre_payload.get("args", args)
        if not isinstance(args, dict):
            return ToolExecutionResult(name=name, ok=False, error="Hook changed tool args to a non-object")

        guardrail = evaluate_tool_call(name, args)
        if not guardrail.allowed:
            return ToolExecutionResult(name=name, ok=False, error=guardrail.reason)

        approval_payload = {"name": name, "args": args, "approved": approved}
        run_hooks("pre_approval_request", approval_payload)
        approval = check_approval(name, args, approved=approved)
        run_hooks(
            "post_approval_response",
            {
                **approval_payload,
                "allowed": approval.allowed,
                "reason": approval.reason,
            },
        )
        if not approval.allowed:
            return ToolExecutionResult(name=name, ok=False, error=approval.reason)

        stale = _stale_reason_for_tool(name, args)
        if stale:
            return ToolExecutionResult(name=name, ok=False, error=stale)

        checkpoint = checkpoint_for_tool(name, args)
        result = registry.dispatch(name, args)
    except Exception as exc:
        return ToolExecutionResult(name=name, ok=False, error=str(exc))

    if checkpoint:
        if isinstance(result, dict):
            result = {**result, "checkpoint_id": checkpoint["id"]}
        else:
            result = {"value": result, "checkpoint_id": checkpoint["id"]}
    tool_result = ToolExecutionResult(name=name, ok=True, result=result)
    run_hooks("post_tool_call", {"name": name, "args": args, "result": tool_result})
    return tool_result


def _stale_reason_for_tool(name: str, args: dict[str, Any]) -> str | None:
    if name not in {"file_write", "file_patch"}:
        return None
    path = args.get("path")
    if not path:
        return f"{name} requires path"
    return file_state.stale_reason(str(path))
