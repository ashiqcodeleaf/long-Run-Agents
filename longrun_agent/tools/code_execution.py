"""Local Python code execution tool with a small LongRun tool helper API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any


def execute_code(code: str, *, timeout_seconds: int = 60, cwd: str | None = None) -> dict[str, Any]:
    clean_code = code.strip()
    if not clean_code:
        raise ValueError("code cannot be empty")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1")

    workdir = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    if not workdir.exists() or not workdir.is_dir():
        raise ValueError(f"Working directory does not exist: {workdir}")

    started = time.monotonic()
    wrapper = _build_wrapper(clean_code)
    env = os.environ.copy()
    project_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = project_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
        handle.write(wrapper)
        script_path = Path(handle.name)
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        completed = None
        timed_out = True
        stdout = _coerce_output(exc.stdout)
        stderr = _coerce_output(exc.stderr)
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass

    duration_ms = int((time.monotonic() - started) * 1000)
    if timed_out:
        return {
            "exit_code": None,
            "timed_out": True,
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "cwd": str(workdir),
        }
    if completed is None:
        raise RuntimeError("execute_code internal error")
    return {
        "exit_code": completed.returncode,
        "timed_out": False,
        "duration_ms": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "cwd": str(workdir),
    }


def _build_wrapper(user_code: str) -> str:
    return (
        textwrap.dedent(
            """
            import json
            import types
            import sys

            from longrun_agent.agent.tool_executor import execute_tool_call

            def call_tool(name, **kwargs):
                result = execute_tool_call(name, kwargs, approved=True)
                if not result.ok:
                    raise RuntimeError(result.error or f"Tool failed: {name}")
                return result.result

            helper = types.ModuleType("longrun_tools")
            helper.call_tool = call_tool
            helper.file_read = lambda path, **kw: call_tool("file_read", path=path, **kw)
            helper.file_write = lambda path, content: call_tool("file_write", path=path, content=content)
            helper.file_patch = lambda path, old, new: call_tool("file_patch", path=path, old=old, new=new)
            helper.file_search = lambda pattern, **kw: call_tool("file_search", pattern=pattern, **kw)
            helper.terminal_run = lambda command, **kw: call_tool("terminal_run", command=command, **kw)
            helper.todo = lambda **kw: call_tool("todo", **kw)
            sys.modules["longrun_tools"] = helper
            """
        ).strip()
        + "\n\n"
        + user_code
        + "\n"
    )


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def register_code_execution_tools(registry: Any) -> None:
    try:
        registry.register(
            name="execute_code",
            description=(
                "Run a local Python script. The script can import longrun_tools to call existing "
                "LongRun tools programmatically, e.g. from longrun_tools import file_write, terminal_run."
            ),
            toolset="code_execution",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                    "cwd": {"type": "string"},
                },
                "required": ["code"],
                "additionalProperties": False,
            },
            handler=lambda args: execute_code(
                str(args.get("code", "")),
                timeout_seconds=int(args.get("timeout_seconds", 60)),
                cwd=args.get("cwd"),
            ),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise

