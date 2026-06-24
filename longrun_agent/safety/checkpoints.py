"""File checkpoints and rollback."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from longrun_agent.config import checkpoints_dir, checkpoints_manifest_path, ensure_home


def create_file_checkpoint(path: str | Path, *, reason: str) -> dict[str, Any]:
    """Snapshot a file before mutation."""

    ensure_home()
    resolved = Path(path).expanduser().resolve()
    checkpoint_id = f"chk-{uuid.uuid4().hex[:12]}"
    existed = resolved.exists()
    content_path: Path | None = None

    if existed:
        if not resolved.is_file():
            raise ValueError(f"Cannot checkpoint non-file path: {resolved}")
        content_path = checkpoints_dir() / f"{checkpoint_id}.content"
        content_path.write_bytes(resolved.read_bytes())

    record = {
        "id": checkpoint_id,
        "path": str(resolved),
        "reason": reason,
        "existed": existed,
        "content_path": str(content_path) if content_path else None,
        "created_at": _now_iso(),
    }
    store = _load_store()
    store["checkpoints"][checkpoint_id] = record
    _save_store(store)
    return record


def checkpoint_for_tool(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Create a checkpoint for mutating file tools."""

    if name not in {"file_write", "file_patch"}:
        return None
    path = args.get("path")
    if not path:
        raise ValueError(f"{name} requires path before checkpoint")
    return create_file_checkpoint(str(path), reason=name)


def list_checkpoints() -> list[dict[str, Any]]:
    """Return checkpoints newest-first."""

    store = _load_store()
    return sorted(
        store["checkpoints"].values(),
        key=lambda item: str(item.get("created_at", "")),
        reverse=True,
    )


def rollback_checkpoint(checkpoint_id: str) -> dict[str, Any]:
    """Restore or remove the file captured by a checkpoint."""

    store = _load_store()
    try:
        record = store["checkpoints"][checkpoint_id]
    except KeyError as exc:
        raise KeyError(f"Unknown checkpoint: {checkpoint_id}") from exc

    target = Path(record["path"]).resolve()
    if record["existed"]:
        content_path = Path(record["content_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content_path.read_bytes())
        action = "restored"
    else:
        if target.exists():
            if not target.is_file():
                raise ValueError(f"Refusing to remove non-file during rollback: {target}")
            target.unlink()
        action = "removed_created_file"

    record["rolled_back_at"] = _now_iso()
    _save_store(store)
    return {
        "id": checkpoint_id,
        "path": str(target),
        "action": action,
    }


def _load_store() -> dict[str, Any]:
    ensure_home()
    path = checkpoints_manifest_path()
    if not path.exists():
        return {"checkpoints": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("checkpoints", {})
    return data


def _save_store(store: dict[str, Any]) -> Path:
    ensure_home()
    path = checkpoints_manifest_path()
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

