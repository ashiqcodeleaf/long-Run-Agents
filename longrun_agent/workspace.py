"""Local `.longrun/` workspace helpers for the CLI MVP."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_DIR_NAME = ".longrun"
WORKSPACE_SUBDIRS = ("memory", "runs", "logs", "tools", "workers")
DEFAULT_LOCAL_CONFIG = """# LongRun local workspace config
version: 1
default_model: gpt-4.1-mini
max_iterations: 90
checkpoints: true
"""

MVP_STAGES = (
    ("receive_task", "Receive and persist the task prompt."),
    ("create_plan", "Create a structured execution plan."),
    ("execute_steps", "Execute planned steps with tools and workers."),
    ("validate_output", "Validate generated files and command results."),
    ("retry_fix_loop", "Retry or fix failed steps until acceptable."),
    ("final_artifact", "Return the final artifact and run summary."),
)


def workspace_dir(root: Path | None = None) -> Path:
    """Return the local LongRun workspace directory for a project root."""

    return (root or Path.cwd()).resolve() / WORKSPACE_DIR_NAME


def init_workspace(root: Path | None = None) -> dict[str, Any]:
    """Create the MVP `.longrun/` directory layout."""

    path = workspace_dir(root)
    path.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for name in WORKSPACE_SUBDIRS:
        child = path / name
        if not child.exists():
            created.append(str(child))
        child.mkdir(parents=True, exist_ok=True)

    config_path = path / "config.yaml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_LOCAL_CONFIG, encoding="utf-8")
        created.append(str(config_path))

    _append_log(path, "workspace initialized")
    return {
        "workspace": str(path),
        "created": created,
        "config": str(config_path),
    }


def workspace_status(root: Path | None = None) -> dict[str, Any]:
    """Return a status snapshot for the local `.longrun/` workspace."""

    path = workspace_dir(root)
    runs_dir = path / "runs"
    run_dirs = sorted([item for item in runs_dir.glob("*") if item.is_dir()], reverse=True) if runs_dir.exists() else []
    latest = run_dirs[0].name if run_dirs else None
    return {
        "workspace": str(path),
        "exists": path.exists(),
        "config": str(path / "config.yaml"),
        "runs": len(run_dirs),
        "latest_run": latest,
        "logs": str(path / "logs"),
    }


def build_plan(task: str) -> dict[str, Any]:
    """Build the readable MVP plan object for a task."""

    clean_task = task.strip()
    if not clean_task:
        raise ValueError("Task prompt cannot be empty")
    return {
        "task": clean_task,
        "stages": [
            {
                "id": stage_id,
                "name": stage_id.replace("_", " ").title(),
                "description": description,
                "status": "stubbed" if stage_id not in {"receive_task", "create_plan"} else "ready",
            }
            for stage_id, description in MVP_STAGES
        ],
        "mvp_note": "This MVP records the run and plan; autonomous execution is stubbed.",
    }


def create_run(task: str, *, root: Path | None = None) -> dict[str, Any]:
    """Create a run folder, persist the task and plan, and return run metadata."""

    info = init_workspace(root)
    path = Path(info["workspace"])
    run_id = "run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    run_dir = path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    plan = build_plan(task)
    task_path = run_dir / "task.txt"
    plan_path = run_dir / "plan.json"
    status_path = run_dir / "status.json"

    task_path.write_text(task.strip() + "\n", encoding="utf-8")
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = {
        "run_id": run_id,
        "status": "planned",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stubbed": ["execute_steps", "validate_output", "retry_fix_loop", "final_artifact"],
    }
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_log(path, f"created {run_id}: {task.strip()}")

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "task_path": str(task_path),
        "plan_path": str(plan_path),
        "status_path": str(status_path),
        "plan": plan,
    }


def list_workspace_logs(root: Path | None = None) -> list[dict[str, Any]]:
    """List local workspace log files."""

    logs_dir = workspace_dir(root) / "logs"
    if not logs_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(logs_dir.glob("*.log")):
        rows.append({"name": path.name, "path": str(path), "bytes": path.stat().st_size})
    return rows


def read_workspace_log(name: str = "longrun.log", *, lines: int = 50, root: Path | None = None) -> dict[str, Any]:
    """Read the tail of a local workspace log."""

    if lines < 1:
        raise ValueError("lines must be at least 1")
    logs_dir = workspace_dir(root) / "logs"
    path = logs_dir / name
    if not path.exists():
        return {"path": str(path), "exists": False, "content": ""}
    content_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"path": str(path), "exists": True, "content": "\n".join(content_lines[-lines:])}


def _append_log(workspace: Path, message: str) -> None:
    logs_dir = workspace / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with (logs_dir / "longrun.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")
