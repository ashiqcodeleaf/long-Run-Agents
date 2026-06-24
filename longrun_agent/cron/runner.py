"""Cron execution runner for LongRun."""

from __future__ import annotations

from typing import Any, Callable

from longrun_agent.agent.runtime import AIAgent
from longrun_agent.cron.jobs import get_due_jobs, get_job, mark_job_run, trigger_job

EventHandler = Callable[[dict[str, Any]], None]


def run_job(job: dict[str, Any], *, event_handler: EventHandler | None = None) -> dict[str, Any]:
    """Run one cron job in a fresh LongRun session."""

    job_id = str(job.get("id") or "")
    prompt = _build_cron_prompt(job)
    try:
        agent = AIAgent(
            title=f"Cron: {job.get('name') or job_id}",
            provider=job.get("provider") or None,
            model=job.get("model") or None,
            event_handler=event_handler,
        )
        result = agent.run_conversation(prompt)
        output = result.final_response
        updated = mark_job_run(
            job_id,
            success=True,
            output=output,
            session_id=result.session_id,
        )
        return {
            "success": True,
            "job": updated,
            "session_id": result.session_id,
            "output": output,
        }
    except Exception as exc:
        updated = mark_job_run(job_id, success=False, error=str(exc))
        return {
            "success": False,
            "job": updated,
            "error": str(exc),
        }


def trigger_and_run(job_id: str, *, event_handler: EventHandler | None = None) -> dict[str, Any]:
    """Mark a job due and run it immediately."""

    job = trigger_job(job_id)
    if not job:
        raise KeyError(f"Cron job not found: {job_id}")
    return run_job(job, event_handler=event_handler)


def tick(*, event_handler: EventHandler | None = None) -> dict[str, Any]:
    """Run every due cron job once."""

    jobs = get_due_jobs()
    results = [run_job(job, event_handler=event_handler) for job in jobs]
    return {
        "count": len(results),
        "results": results,
    }


def preview_job(job_id: str) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job:
        return None
    return {
        "job": job,
        "prompt": _build_cron_prompt(job),
    }


def _build_cron_prompt(job: dict[str, Any]) -> str:
    skills = job.get("skills") or []
    skill_line = f"Attached skills: {', '.join(skills)}\n" if skills else ""
    return (
        "You are LongRun executing a scheduled CLI-only cron job.\n"
        f"Job ID: {job.get('id')}\n"
        f"Job name: {job.get('name')}\n"
        f"Schedule: {job.get('schedule_display')}\n"
        f"{skill_line}"
        "\n"
        "Run this as a fresh isolated task. Do not ask the user for live input. "
        "Use tools when useful, then return the final user-facing result.\n\n"
        f"Task:\n{job.get('prompt')}"
    )
