"""Cron job management tool."""

from __future__ import annotations

from typing import Any

from longrun_agent.cron.jobs import (
    create_job,
    get_job,
    list_jobs,
    pause_job,
    remove_job,
    resume_job,
    trigger_job,
)


def cronjob_tool(
    *,
    action: str,
    job_id: str | None = None,
    prompt: str | None = None,
    schedule: str | None = None,
    name: str | None = None,
    repeat: int | None = None,
    include_disabled: bool = True,
    skills: list[str] | None = None,
    enabled_toolsets: list[str] | None = None,
    model: str | None = None,
    provider: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Unified cron job management operation."""

    normalized = action.strip().lower()
    if normalized == "create":
        if not prompt:
            raise ValueError("prompt is required for cronjob create")
        job = create_job(
            prompt=prompt,
            schedule=schedule or "manual",
            name=name,
            repeat=repeat,
            skills=skills,
            enabled_toolsets=enabled_toolsets,
            model=model,
            provider=provider,
        )
        return {"success": True, "job": _format_job(job), "message": f"Cron job '{job['name']}' created."}

    if normalized == "list":
        jobs = [_format_job(job) for job in list_jobs(include_disabled=include_disabled)]
        return {"success": True, "count": len(jobs), "jobs": jobs}

    if not job_id:
        raise ValueError(f"job_id is required for cronjob action '{normalized}'")

    if normalized == "show":
        job = get_job(job_id)
        return {"success": bool(job), "job": _format_job(job) if job else None}

    if normalized == "pause":
        job = pause_job(job_id, reason=reason)
        return {"success": bool(job), "job": _format_job(job) if job else None}

    if normalized == "resume":
        job = resume_job(job_id)
        return {"success": bool(job), "job": _format_job(job) if job else None}

    if normalized in {"run", "trigger", "run_now"}:
        job = trigger_job(job_id)
        return {"success": bool(job), "job": _format_job(job) if job else None, "message": "Job is due on next tick."}

    if normalized == "remove":
        removed = remove_job(job_id)
        return {"success": removed, "removed": removed, "job_id": job_id}

    raise ValueError(f"Unknown cronjob action: {action}")


def register_cronjob_tools(registry: Any) -> None:
    """Register cron management tools with the central registry."""

    try:
        registry.register(
            name="cronjob",
            description=(
                "Manage CLI-only scheduled LongRun jobs. Use action='create' to schedule, "
                "action='list' to inspect, and action='trigger'/'pause'/'resume'/'remove' to manage."
            ),
            toolset="cronjob",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "One of: create, list, show, pause, resume, remove, trigger.",
                    },
                    "job_id": {"type": "string"},
                    "prompt": {"type": "string", "description": "Self-contained task prompt for create."},
                    "schedule": {
                        "type": "string",
                        "description": "manual, an interval like 30m/every 2h, a simple cron expression, or ISO datetime.",
                    },
                    "name": {"type": "string"},
                    "repeat": {"type": "integer"},
                    "include_disabled": {"type": "boolean"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "enabled_toolsets": {"type": "array", "items": {"type": "string"}},
                    "model": {"type": "string"},
                    "provider": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            handler=lambda args: cronjob_tool(
                action=str(args.get("action", "")),
                job_id=args.get("job_id"),
                prompt=args.get("prompt"),
                schedule=args.get("schedule"),
                name=args.get("name"),
                repeat=args.get("repeat"),
                include_disabled=bool(args.get("include_disabled", True)),
                skills=args.get("skills"),
                enabled_toolsets=args.get("enabled_toolsets"),
                model=args.get("model"),
                provider=args.get("provider"),
                reason=args.get("reason"),
            ),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise


def _format_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "prompt": job.get("prompt"),
        "schedule": job.get("schedule_display"),
        "enabled": job.get("enabled"),
        "state": job.get("state"),
        "next_run_at": job.get("next_run_at"),
        "last_run_at": job.get("last_run_at"),
        "last_status": job.get("last_status"),
        "last_error": job.get("last_error"),
        "last_session_id": job.get("last_session_id"),
        "skills": job.get("skills") or [],
        "enabled_toolsets": job.get("enabled_toolsets"),
    }
