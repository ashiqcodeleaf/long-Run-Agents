"""File tools for LongRun Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from longrun_agent.tools import file_state

SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache"}


def read_file(path: str, *, offset: int = 1, limit: int = 500) -> dict[str, Any]:
    """Read a text file and record its fingerprint."""

    resolved = _resolve_file(path)
    if offset < 1:
        raise ValueError("offset must be 1 or greater")
    if limit < 1:
        raise ValueError("limit must be 1 or greater")

    text = resolved.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start_index = offset - 1
    selected = lines[start_index : start_index + limit]
    state = file_state.record_read(resolved)
    return {
        "path": str(resolved),
        "offset": offset,
        "limit": limit,
        "line_count": len(lines),
        "content": "\n".join(selected),
        "fingerprint": state["fingerprint"],
    }


def write_file(path: str, content: str) -> dict[str, Any]:
    """Write a text file and record the new fingerprint."""

    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    state = file_state.record_write(resolved)
    return {
        "path": str(resolved),
        "bytes": len(content.encode("utf-8")),
        "fingerprint": state["fingerprint"],
    }


def patch_file(path: str, old: str, new: str) -> dict[str, Any]:
    """Replace exactly one text fragment in a file."""

    resolved = _resolve_file(path)
    if old == "":
        raise ValueError("old cannot be empty")

    text = resolved.read_text(encoding="utf-8", errors="replace")
    count = text.count(old)
    if count == 0:
        raise ValueError("old text not found")
    if count > 1:
        raise ValueError("old text appears more than once; provide a unique fragment")

    updated = text.replace(old, new, 1)
    resolved.write_text(updated, encoding="utf-8")
    state = file_state.record_write(resolved)
    return {
        "path": str(resolved),
        "replacements": 1,
        "fingerprint": state["fingerprint"],
    }


def search_files(pattern: str, *, path: str = ".", target: str = "content", limit: int = 50) -> dict[str, Any]:
    """Search file names or content under a directory."""

    if not pattern:
        raise ValueError("pattern cannot be empty")
    if target not in {"content", "name"}:
        raise ValueError("target must be content or name")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Search path not found: {root}")

    matches: list[dict[str, Any]] = []
    paths = [root] if root.is_file() else _walk_files(root)
    lowered = pattern.lower()
    for file_path in paths:
        if len(matches) >= limit:
            break
        if target == "name":
            if lowered in file_path.name.lower():
                matches.append({"path": str(file_path)})
            continue

        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            if lowered in line.lower():
                matches.append({"path": str(file_path), "line": line_no, "text": line})
                break

    return {"pattern": pattern, "target": target, "root": str(root), "matches": matches}


def register_file_tools(registry: Any) -> None:
    """Register file tools with the central registry."""

    _register_once(
        registry,
        name="file_read",
        description="Read a text file and record its freshness fingerprint.",
        toolset="file",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=lambda args: read_file(
            str(args.get("path", "")),
            offset=int(args.get("offset", 1)),
            limit=int(args.get("limit", 500)),
        ),
    )
    _register_once(
        registry,
        name="file_write",
        description=(
            "Create or replace a UTF-8 text file. Parent directories are created automatically. "
            "Prefer this over terminal commands for writing markdown, code, config, and notes."
        ),
        toolset="file",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        handler=lambda args: write_file(str(args.get("path", "")), str(args.get("content", ""))),
    )
    _register_once(
        registry,
        name="file_patch",
        description="Replace exactly one text fragment in a file.",
        toolset="file",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string"},
                "new": {"type": "string"},
            },
            "required": ["path", "old", "new"],
            "additionalProperties": False,
        },
        handler=lambda args: patch_file(
            str(args.get("path", "")),
            str(args.get("old", "")),
            str(args.get("new", "")),
        ),
    )
    _register_once(
        registry,
        name="file_search",
        description="Search file names or text content.",
        toolset="file",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "target": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        handler=lambda args: search_files(
            str(args.get("pattern", "")),
            path=str(args.get("path", ".")),
            target=str(args.get("target", "content")),
            limit=int(args.get("limit", 50)),
        ),
    )


def _walk_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def _resolve_file(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Path is not a file: {resolved}")
    return resolved


def _register_once(registry: Any, **kwargs: Any) -> None:
    try:
        registry.register(**kwargs)
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise
