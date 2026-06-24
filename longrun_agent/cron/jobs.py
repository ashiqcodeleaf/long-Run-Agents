"""Cron job storage for CLI-only LongRun.

This is adapted from MyAgent's cron shape, but trimmed to the CLI MVP:
jobs are JSON-backed, run in fresh agent sessions, and do not auto-deliver
to gateway platforms.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from longrun_agent.config import cron_jobs_path, cron_output_dir, ensure_home

MANUAL_SCHEDULE = "manual"
_INTERVAL_RE = re.compile(r"^(?:every\s+)?(?P<count>\d+)\s*(?P<unit>m|min|minute|minutes|h|hour|hours|d|day|days)$", re.I)


def create_job(
    *,
    prompt: str,
    schedule: str = MANUAL_SCHEDULE,
    name: str | None = None,
    repeat: int | None = None,
    skills: list[str] | None = None,
    enabled_toolsets: list[str] | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Create a scheduled job record."""

    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("Cron prompt cannot be empty")
    parsed_schedule = parse_schedule(schedule)
    now = _now_iso()
    job = {
        "id": uuid.uuid4().hex[:12],
        "name": name.strip() if name else clean_prompt[:50].strip(),
        "prompt": clean_prompt,
        "schedule": parsed_schedule,
        "schedule_display": parsed_schedule["display"],
        "repeat": {"times": repeat if repeat and repeat > 0 else None, "completed": 0},
        "enabled": True,
        "state": "scheduled",
        "skills": [str(item).strip() for item in skills or [] if str(item).strip()],
        "enabled_toolsets": [str(item).strip() for item in enabled_toolsets or [] if str(item).strip()] or None,
        "model": model.strip() if isinstance(model, str) and model.strip() else None,
        "provider": provider.strip() if isinstance(provider, str) and provider.strip() else None,
        "created_at": now,
        "updated_at": now,
        "next_run_at": compute_next_run(parsed_schedule),
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "last_session_id": None,
        "last_output_path": None,
    }
    jobs = _load_jobs()
    jobs.append(job)
    _save_jobs(jobs)
    return dict(job)


def list_jobs(*, include_disabled: bool = False) -> list[dict[str, Any]]:
    jobs = _load_jobs()
    if not include_disabled:
        jobs = [job for job in jobs if job.get("enabled", True)]
    return [dict(job) for job in jobs]


def get_job(job_id: str) -> dict[str, Any] | None:
    target = _resolve_job_ref(job_id)
    return dict(target) if target else None


def pause_job(job_id: str, reason: str | None = None) -> dict[str, Any] | None:
    return _update_job(
        job_id,
        {
            "enabled": False,
            "state": "paused",
            "paused_reason": reason,
            "paused_at": _now_iso(),
        },
    )


def resume_job(job_id: str) -> dict[str, Any] | None:
    job = _resolve_job_ref(job_id)
    if not job:
        return None
    return _update_job(
        job["id"],
        {
            "enabled": True,
            "state": "scheduled",
            "paused_reason": None,
            "paused_at": None,
            "next_run_at": compute_next_run(job.get("schedule") or {"kind": MANUAL_SCHEDULE}),
        },
    )


def trigger_job(job_id: str) -> dict[str, Any] | None:
    job = _resolve_job_ref(job_id)
    if not job:
        return None
    return _update_job(
        job["id"],
        {
            "enabled": True,
            "state": "scheduled",
            "paused_reason": None,
            "paused_at": None,
            "next_run_at": _now_iso(),
        },
    )


def remove_job(job_id: str) -> bool:
    job = _resolve_job_ref(job_id)
    if not job:
        return False
    jobs = [item for item in _load_jobs() if item["id"] != job["id"]]
    _save_jobs(jobs)
    return True


def get_due_jobs() -> list[dict[str, Any]]:
    now = _now()
    due: list[dict[str, Any]] = []
    for job in _load_jobs():
        if not job.get("enabled", True):
            continue
        next_run_at = str(job.get("next_run_at") or "").strip()
        if not next_run_at:
            continue
        try:
            if _parse_datetime(next_run_at) <= now:
                due.append(dict(job))
        except ValueError:
            continue
    return due


def mark_job_run(
    job_id: str,
    *,
    success: bool,
    output: str = "",
    error: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    """Persist cron run result and advance the schedule."""

    job = _resolve_job_ref(job_id)
    if not job:
        return None
    output_path = save_job_output(job["id"], output) if output else None
    repeat = dict(job.get("repeat") or {})
    completed = int(repeat.get("completed") or 0) + 1
    repeat["completed"] = completed
    repeat_limit = repeat.get("times")
    disabled = repeat_limit is not None and completed >= int(repeat_limit)
    updates: dict[str, Any] = {
        "repeat": repeat,
        "last_run_at": _now_iso(),
        "last_status": "ok" if success else "error",
        "last_error": None if success else error,
        "last_session_id": session_id,
        "last_output_path": str(output_path) if output_path else None,
        "state": "completed" if disabled else "scheduled",
        "enabled": not disabled,
        "next_run_at": None if disabled else compute_next_run(job.get("schedule") or {"kind": MANUAL_SCHEDULE}),
    }
    return _update_job(job["id"], updates)


def save_job_output(job_id: str, output: str) -> Path:
    safe_id = _safe_component(job_id)
    root = cron_output_dir() / safe_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_now().strftime('%Y%m%d-%H%M%S')}.md"
    path.write_text(output, encoding="utf-8")
    return path


def parse_schedule(schedule: str) -> dict[str, Any]:
    text = (schedule or MANUAL_SCHEDULE).strip()
    if not text or text.lower() in {MANUAL_SCHEDULE, "on-demand", "ondemand"}:
        return {"kind": MANUAL_SCHEDULE, "display": MANUAL_SCHEDULE}
    match = _INTERVAL_RE.match(text)
    if match:
        count = int(match.group("count"))
        unit = match.group("unit").lower()
        seconds = count * _unit_seconds(unit)
        return {"kind": "interval", "seconds": seconds, "display": text}
    if len(text.split()) == 5:
        return {"kind": "cron", "expr": text, "display": text}
    try:
        when = _parse_datetime(text)
    except ValueError:
        raise ValueError("Schedule must be 'manual', an interval like '30m', a 5-field cron expression, or ISO datetime")
    return {"kind": "once", "run_at": when.isoformat(), "display": text}


def compute_next_run(schedule: dict[str, Any]) -> str | None:
    kind = schedule.get("kind")
    if kind == MANUAL_SCHEDULE:
        return None
    if kind == "interval":
        return (_now() + timedelta(seconds=int(schedule.get("seconds") or 0))).isoformat()
    if kind == "once":
        return str(schedule.get("run_at") or "")
    if kind == "cron":
        return _next_simple_cron(str(schedule.get("expr") or ""))
    return None


def _next_simple_cron(expr: str) -> str:
    """Best-effort next run for common five-field cron expressions."""

    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("Cron expression must have five fields")
    minute, hour, day, month, weekday = parts
    if day == month == weekday == "*" and minute.isdigit() and hour.isdigit():
        candidate = _now().replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        if candidate <= _now():
            candidate += timedelta(days=1)
        return candidate.isoformat()
    # The MVP stores complex cron expressions but requires manual trigger/tick
    # support until a full croniter dependency is introduced.
    return None


def _update_job(job_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    job = _resolve_job_ref(job_id)
    if not job:
        return None
    jobs = _load_jobs()
    for index, item in enumerate(jobs):
        if item["id"] == job["id"]:
            updated = {**item, **updates, "updated_at": _now_iso()}
            jobs[index] = updated
            _save_jobs(jobs)
            return dict(updated)
    return None


def _resolve_job_ref(ref: str) -> dict[str, Any] | None:
    clean = str(ref or "").strip()
    if not clean:
        return None
    jobs = _load_jobs()
    for job in jobs:
        if job.get("id") == clean:
            return job
    lowered = clean.lower()
    matches = [job for job in jobs if str(job.get("name") or "").lower() == lowered]
    if len(matches) > 1:
        raise ValueError(f"Cron job name is ambiguous: {clean}")
    return matches[0] if matches else None


def _load_jobs() -> list[dict[str, Any]]:
    ensure_home()
    path = cron_jobs_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(data, list):
        raise ValueError(f"Invalid cron jobs file: {path}")
    return [item for item in data if isinstance(item, dict)]


def _save_jobs(jobs: list[dict[str, Any]]) -> None:
    ensure_home()
    path = cron_jobs_path()
    path.write_text(json.dumps(jobs, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_component(value: str) -> str:
    text = str(value or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"Invalid path component: {value!r}")
    return text


def _unit_seconds(unit: str) -> int:
    if unit.startswith("m") and unit != "month":
        return 60
    if unit.startswith("h"):
        return 60 * 60
    if unit.startswith("d"):
        return 60 * 60 * 24
    raise ValueError(f"Unsupported interval unit: {unit}")


def _parse_datetime(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()
