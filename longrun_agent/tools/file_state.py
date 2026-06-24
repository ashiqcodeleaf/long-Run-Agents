"""File read/write freshness tracking."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from longrun_agent.config import ensure_home, file_state_path


def record_read(path: str | Path) -> dict[str, Any]:
    """Record the current fingerprint for a read file."""

    resolved = _resolve_file(path)
    fingerprint = fingerprint_path(resolved)
    store = _load_store()
    store["files"][str(resolved)] = {
        "path": str(resolved),
        "fingerprint": fingerprint,
        "read_at": _now_iso(),
    }
    _save_store(store)
    return store["files"][str(resolved)]


def record_write(path: str | Path) -> dict[str, Any]:
    """Record the current fingerprint after a write."""

    resolved = Path(path).expanduser().resolve()
    fingerprint = fingerprint_path(resolved)
    store = _load_store()
    entry = store["files"].setdefault(str(resolved), {"path": str(resolved)})
    entry.update(
        {
            "fingerprint": fingerprint,
            "write_at": _now_iso(),
        }
    )
    _save_store(store)
    return entry


def stale_reason(path: str | Path) -> str | None:
    """Return why a file is stale compared with the last read, if known."""

    resolved = Path(path).expanduser().resolve()
    store = _load_store()
    entry = store["files"].get(str(resolved))
    if not entry:
        return None

    current = fingerprint_path(resolved)
    previous = entry.get("fingerprint")
    if current != previous:
        return (
            f"File changed since last read: {resolved}. "
            f"previous={previous} current={current}"
        )
    return None


def fingerprint_path(path: Path) -> dict[str, Any]:
    """Return a stable fingerprint for an existing or missing path."""

    if not path.exists():
        return {"exists": False, "size": 0, "mtime_ns": None, "sha256": None}
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    data = path.read_bytes()
    stat = path.stat()
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _resolve_file(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Path is not a file: {resolved}")
    return resolved


def _load_store() -> dict[str, Any]:
    ensure_home()
    path = file_state_path()
    if not path.exists():
        return {"files": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("files", {})
    return data


def _save_store(store: dict[str, Any]) -> Path:
    ensure_home()
    path = file_state_path()
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

