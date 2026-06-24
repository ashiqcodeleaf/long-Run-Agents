"""Persistent background process tools."""

from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from longrun_agent.config import ensure_home, process_logs_dir, processes_path

WRAPPER_CODE = r"""
import subprocess
import sys
from pathlib import Path

command, cwd, stdout_path, stderr_path, exit_path = sys.argv[1:6]
workdir = cwd or None
with open(stdout_path, "a", encoding="utf-8", errors="replace") as stdout:
    with open(stderr_path, "a", encoding="utf-8", errors="replace") as stderr:
        completed = subprocess.run(command, shell=True, cwd=workdir, stdout=stdout, stderr=stderr, text=True)
Path(exit_path).write_text(str(completed.returncode), encoding="utf-8")
"""


def start_background_process(command: str, *, cwd: str | None = None) -> dict[str, Any]:
    """Start a command in a wrapper process and persist metadata."""

    clean_command = command.strip()
    if not clean_command:
        raise ValueError("Command cannot be empty")

    ensure_home()
    workdir = _resolve_cwd(cwd)
    session_id = f"proc-{uuid.uuid4().hex[:12]}"
    logs_dir = process_logs_dir()
    stdout_path = logs_dir / f"{session_id}.stdout.log"
    stderr_path = logs_dir / f"{session_id}.stderr.log"
    exit_path = logs_dir / f"{session_id}.exit"

    creationflags = 0
    if platform.system() == "Windows":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            WRAPPER_CODE,
            clean_command,
            str(workdir),
            str(stdout_path),
            str(stderr_path),
            str(exit_path),
        ],
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    record = {
        "id": session_id,
        "command": clean_command,
        "cwd": str(workdir),
        "pid": process.pid,
        "status": "running",
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "exit_path": str(exit_path),
    }
    store = _load_store()
    store["processes"][session_id] = record
    _save_store(store)
    return poll_process(session_id)


def poll_process(session_id: str, *, max_chars: int = 4000) -> dict[str, Any]:
    """Poll one process and return status plus recent output."""

    store = _load_store()
    record = _get_record(store, session_id)
    status, exit_code = _current_status(record)
    record["status"] = status
    record["updated_at"] = _now_iso()
    if exit_code is not None:
        record["exit_code"] = exit_code
        record.setdefault("finished_at", _now_iso())
    _save_store(store)

    return {
        "id": session_id,
        "command": record["command"],
        "cwd": record["cwd"],
        "pid": record["pid"],
        "status": record["status"],
        "exit_code": record.get("exit_code"),
        "started_at": record["started_at"],
        "updated_at": record["updated_at"],
        "stdout": _read_tail(Path(record["stdout_path"]), max_chars=max_chars),
        "stderr": _read_tail(Path(record["stderr_path"]), max_chars=max_chars),
    }


def kill_process(session_id: str) -> dict[str, Any]:
    """Kill a tracked process tree where possible."""

    store = _load_store()
    record = _get_record(store, session_id)
    status, exit_code = _current_status(record)
    if status == "running":
        _kill_pid(int(record["pid"]))
        record["status"] = "killed"
        record["killed_at"] = _now_iso()
        record["updated_at"] = _now_iso()
    else:
        record["status"] = status
        record["exit_code"] = exit_code
        record["updated_at"] = _now_iso()
    _save_store(store)
    return poll_process(session_id)


def list_processes() -> list[dict[str, Any]]:
    """List tracked process records with refreshed statuses."""

    store = _load_store()
    rows: list[dict[str, Any]] = []
    for session_id in sorted(store["processes"]):
        rows.append(poll_process(session_id, max_chars=0))
    return rows


def register_process_tools(registry: Any) -> None:
    """Register background process tools."""

    _register_once(
        registry,
        name="process_start",
        description="Start a background shell command.",
        toolset="process",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run in the background."},
                "cwd": {"type": "string", "description": "Working directory."},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        handler=lambda args: start_background_process(str(args.get("command", "")), cwd=args.get("cwd")),
    )
    _register_once(
        registry,
        name="process_poll",
        description="Poll a background process.",
        toolset="process",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Process session id."}},
            "required": ["id"],
            "additionalProperties": False,
        },
        handler=lambda args: poll_process(str(args.get("id", ""))),
    )
    _register_once(
        registry,
        name="process_kill",
        description="Kill a background process.",
        toolset="process",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Process session id."}},
            "required": ["id"],
            "additionalProperties": False,
        },
        handler=lambda args: kill_process(str(args.get("id", ""))),
    )
    _register_once(
        registry,
        name="process_list",
        description="List tracked background processes.",
        toolset="process",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda _args: list_processes(),
    )


def _load_store() -> dict[str, Any]:
    ensure_home()
    path = processes_path()
    if not path.exists():
        return {"processes": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("processes", {})
    return data


def _save_store(store: dict[str, Any]) -> Path:
    ensure_home()
    path = processes_path()
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _get_record(store: dict[str, Any], session_id: str) -> dict[str, Any]:
    try:
        return store["processes"][session_id]
    except KeyError as exc:
        raise KeyError(f"Unknown process session: {session_id}") from exc


def _current_status(record: dict[str, Any]) -> tuple[str, int | None]:
    exit_path = Path(record["exit_path"])
    if exit_path.exists():
        try:
            exit_code = int(exit_path.read_text(encoding="utf-8").strip())
        except ValueError:
            exit_code = None
        return "exited", exit_code
    if record.get("status") == "killed":
        return "killed", record.get("exit_code")
    if _pid_alive(int(record["pid"])):
        return "running", None
    return "unknown", None


def _pid_alive(pid: int) -> bool:
    if platform.system() == "Windows":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in completed.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _kill_pid(pid: int) -> None:
    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _read_tail(path: Path, *, max_chars: int) -> str:
    if max_chars <= 0 or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _resolve_cwd(cwd: str | None) -> Path:
    path = Path(cwd).expanduser() if cwd else Path.cwd()
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"Working directory does not exist: {resolved}")
    return resolved


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _register_once(registry: Any, **kwargs: Any) -> None:
    try:
        registry.register(**kwargs)
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise

