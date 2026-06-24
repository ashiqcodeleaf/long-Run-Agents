"""Local terminal execution tools."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any


def run_foreground_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Run a local shell command and capture stdout/stderr."""

    clean_command = command.strip()
    if not clean_command:
        raise ValueError("Command cannot be empty")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1")

    workdir = _resolve_cwd(cwd)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            clean_command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "command": clean_command,
            "cwd": str(workdir),
            "exit_code": None,
            "timed_out": True,
            "duration_ms": duration_ms,
            "stdout": _coerce_output(exc.stdout),
            "stderr": _coerce_output(exc.stderr),
        }

    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "command": clean_command,
        "cwd": str(workdir),
        "exit_code": completed.returncode,
        "timed_out": False,
        "duration_ms": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def register_terminal_tools(registry: Any) -> None:
    """Register terminal tools with the central registry."""

    _register_once(
        registry,
        name="terminal_run",
        description=(
            "Run a local foreground shell command and capture stdout, stderr, and exit code. "
            "Use for commands and verification; prefer file_write for creating multi-line files."
        ),
        toolset="terminal",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute."},
                "cwd": {"type": "string", "description": "Working directory."},
                "timeout_seconds": {"type": "integer", "description": "Timeout in seconds."},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        handler=lambda args: run_foreground_command(
            str(args.get("command", "")),
            cwd=args.get("cwd"),
            timeout_seconds=int(args.get("timeout_seconds", 60)),
        ),
    )


def _resolve_cwd(cwd: str | None) -> Path:
    path = Path(cwd).expanduser() if cwd else Path.cwd()
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"Working directory does not exist: {resolved}")
    return resolved


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _register_once(registry: Any, **kwargs: Any) -> None:
    try:
        registry.register(**kwargs)
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise
