"""Long-Run workflow tools."""

from __future__ import annotations

from typing import Any

from longrun_agent.long_run import db


def register_long_run_tools(registry: Any) -> None:
    """Register Long-Run tools with the central registry."""

    _register_once(
        registry,
        name="long_run_create",
        description="Create a durable Long-Run task.",
        toolset="long-run",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "assignee": {"type": "string"},
                "board": {"type": "string"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=lambda args: db.create_task(
            str(args.get("title", "")),
            description=str(args.get("description", "")),
            assignee=args.get("assignee"),
            board=str(args.get("board", db.DEFAULT_BOARD)),
        ),
    )
    _register_once(
        registry,
        name="long_run_list",
        description="List durable Long-Run tasks.",
        toolset="long-run",
        parameters={
            "type": "object",
            "properties": {"board": {"type": "string"}, "status": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=lambda args: {
            "tasks": db.list_tasks(
                board=str(args.get("board", db.DEFAULT_BOARD)),
                status=args.get("status"),
            )
        },
    )
    _register_once(
        registry,
        name="long_run_claim",
        description="Atomically claim the next ready Long-Run task.",
        toolset="long-run",
        parameters={
            "type": "object",
            "properties": {"board": {"type": "string"}, "worker": {"type": "string"}},
            "required": ["worker"],
            "additionalProperties": False,
        },
        handler=lambda args: {
            "task": db.claim_next_task(
                str(args.get("worker", "")),
                board=str(args.get("board", db.DEFAULT_BOARD)),
            )
        },
    )
    _register_once(
        registry,
        name="long_run_complete",
        description="Complete a Long-Run task.",
        toolset="long-run",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "result": {"type": "string"},
                "board": {"type": "string"},
            },
            "required": ["task_id", "result"],
            "additionalProperties": False,
        },
        handler=lambda args: db.complete_task(
            str(args.get("task_id", "")),
            str(args.get("result", "")),
            board=str(args.get("board", db.DEFAULT_BOARD)),
        ),
    )
    _register_once(
        registry,
        name="long_run_heartbeat",
        description="Record a Long-Run worker heartbeat.",
        toolset="long-run",
        parameters={
            "type": "object",
            "properties": {
                "worker": {"type": "string"},
                "task_id": {"type": "string"},
                "status": {"type": "string"},
                "board": {"type": "string"},
            },
            "required": ["worker"],
            "additionalProperties": False,
        },
        handler=lambda args: db.heartbeat(
            str(args.get("worker", "")),
            task_id=args.get("task_id"),
            status=str(args.get("status", "alive")),
            board=str(args.get("board", db.DEFAULT_BOARD)),
        ),
    )


def _register_once(registry: Any, **kwargs: Any) -> None:
    try:
        registry.register(**kwargs)
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise
