"""Subagent delegation tool."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from longrun_agent.hooks import run_hooks
from longrun_agent.state import create_agent_job, update_agent_job

_SUBAGENT_DEPTH: ContextVar[int] = ContextVar("longrun_subagent_depth", default=0)


def current_subagent_depth() -> int:
    """Return current in-process subagent depth."""

    return _SUBAGENT_DEPTH.get()


def delegate_task(prompt: str, *, title: str | None = None, max_depth: int = 1) -> dict[str, Any]:
    """Run a child AIAgent and return its result to the parent."""

    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("Delegate prompt cannot be empty")
    depth = current_subagent_depth()
    if depth >= max_depth:
        raise RuntimeError("Subagent recursion is disabled by default")

    from longrun_agent.agent.runtime import AIAgent

    payload = {"prompt": clean_prompt, "title": title, "depth": depth + 1}
    run_hooks("subagent_start", payload)
    job = create_agent_job(clean_prompt, status="running")
    token = _SUBAGENT_DEPTH.set(depth + 1)
    try:
        child = AIAgent(title=title or "Delegated task")
        result = child.run_conversation(clean_prompt)
    except Exception as exc:
        update_agent_job(str(job["id"]), status="failed", error=str(exc))
        raise
    finally:
        _SUBAGENT_DEPTH.reset(token)
    output = {
        "job_id": job["id"],
        "session_id": result.session_id,
        "final_response": result.final_response,
        "provider": result.provider,
        "model": result.model,
        "iterations": result.iterations,
        "stopped_by_limit": result.stopped_by_limit,
        "depth": depth + 1,
    }
    update_agent_job(
        str(job["id"]),
        status="completed",
        session_id=result.session_id,
        result=result.final_response,
        error=None,
    )
    run_hooks("subagent_stop", {**payload, "result": output})
    return output


def register_delegate_tools(registry: Any) -> None:
    """Register subagent tools with the central registry."""

    try:
        registry.register(
            name="delegate_task",
            description="Create a child LongRun agent for a focused task. Recursion is disabled by default.",
            toolset="subagent",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "title": {"type": "string"},
                    "max_depth": {"type": "integer"},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            handler=lambda args: delegate_task(
                str(args.get("prompt", "")),
                title=args.get("title"),
                max_depth=int(args.get("max_depth", 1)),
            ),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise
