"""User memory tools for LongRun Agent."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from longrun_agent.config import ensure_home, memory_path


def list_memory() -> dict[str, Any]:
    """Return all stored memory entries."""

    store = _load_store()
    return {"items": [store["items"][key] for key in sorted(store["items"])]}


def get_memory(key: str) -> dict[str, Any]:
    """Return one memory entry by key."""

    clean_key = _clean_key(key)
    store = _load_store()
    item = store["items"].get(clean_key)
    if item is None:
        raise KeyError(f"Memory not found: {clean_key}")
    return item


def set_memory(key: str, value: str) -> dict[str, Any]:
    """Create or update one memory entry."""

    clean_key = _clean_key(key)
    clean_value = value.strip()
    if not clean_value:
        raise ValueError("Memory value cannot be empty")

    store = _load_store()
    now = _now_iso()
    existing = store["items"].get(clean_key, {})
    item = {
        "key": clean_key,
        "value": clean_value,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    store["items"][clean_key] = item
    _save_store(store)
    return item


def delete_memory(key: str) -> dict[str, Any]:
    """Delete one memory entry."""

    clean_key = _clean_key(key)
    store = _load_store()
    existed = clean_key in store["items"]
    store["items"].pop(clean_key, None)
    _save_store(store)
    return {"key": clean_key, "deleted": existed}


def clear_memory() -> dict[str, Any]:
    """Delete all memory entries."""

    store = _load_store()
    count = len(store["items"])
    store["items"] = {}
    _save_store(store)
    return {"deleted": count}


def memory_snapshot(max_items: int = 20) -> str:
    """Return a compact prompt-ready memory snapshot."""

    items = list_memory()["items"][:max_items]
    if not items:
        return "No saved memory."
    return "\n".join(f"- {item['key']}: {item['value']}" for item in items)


def register_memory_tools(registry: Any) -> None:
    """Register memory tools with the central registry."""

    _register_once(
        registry,
        name="memory_list",
        description="List saved user memory entries.",
        toolset="memory",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda args: list_memory(),
    )
    _register_once(
        registry,
        name="memory_get",
        description="Read one saved memory entry by key.",
        toolset="memory",
        parameters={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
        handler=lambda args: get_memory(str(args.get("key", ""))),
    )
    _register_once(
        registry,
        name="memory_set",
        description="Create or update one saved user memory entry.",
        toolset="memory",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        },
        handler=lambda args: set_memory(str(args.get("key", "")), str(args.get("value", ""))),
    )
    _register_once(
        registry,
        name="memory_delete",
        description="Delete one saved user memory entry.",
        toolset="memory",
        parameters={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
        handler=lambda args: delete_memory(str(args.get("key", ""))),
    )


def _load_store() -> dict[str, Any]:
    ensure_home()
    path = memory_path()
    if not path.exists():
        return {"items": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"items": {}}
    items = data.get("items", {})
    data["items"] = items if isinstance(items, dict) else {}
    return data


def _save_store(store: dict[str, Any]) -> None:
    ensure_home()
    memory_path().write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clean_key(key: str) -> str:
    clean_key = key.strip()
    if not clean_key:
        raise ValueError("Memory key cannot be empty")
    return clean_key


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _register_once(registry: Any, **kwargs: Any) -> None:
    try:
        registry.register(**kwargs)
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise
