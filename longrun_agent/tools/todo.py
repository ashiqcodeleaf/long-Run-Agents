"""Session todo tool, adapted from MyAgent's todo tool for LongRun."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from longrun_agent.config import ensure_home
from longrun_agent.tools.runtime_context import get_tool_context

VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}
MAX_TODO_ITEMS = 256
MAX_TODO_CONTENT_CHARS = 4000
TRUNCATION_MARKER = "... [truncated]"


class TodoStore:
    """Ordered task list. List position is priority."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._items = self._load()

    def read(self) -> list[dict[str, str]]:
        return [item.copy() for item in self._items]

    def write(self, todos: list[dict[str, Any]], *, merge: bool = False) -> list[dict[str, str]]:
        if not merge:
            self._items = [self._validate(item) for item in self._dedupe_by_id(todos)]
        else:
            existing = {item["id"]: item for item in self._items}
            for raw in self._dedupe_by_id(todos):
                item_id = str(raw.get("id", "")).strip()
                if not item_id:
                    continue
                if item_id in existing:
                    if "content" in raw and str(raw["content"]).strip():
                        existing[item_id]["content"] = self._cap_content(str(raw["content"]).strip())
                    if "status" in raw:
                        status = str(raw["status"]).strip().lower()
                        if status in VALID_STATUSES:
                            existing[item_id]["status"] = status
                else:
                    validated = self._validate(raw)
                    existing[validated["id"]] = validated
                    self._items.append(validated)
            rebuilt: list[dict[str, str]] = []
            seen: set[str] = set()
            for item in self._items:
                current = existing.get(item["id"], item)
                if current["id"] not in seen:
                    rebuilt.append(current)
                    seen.add(current["id"])
            self._items = rebuilt

        if len(self._items) > MAX_TODO_ITEMS:
            self._items = self._items[:MAX_TODO_ITEMS]
        self._save()
        return self.read()

    def _load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = data.get("todos") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [self._validate(item if isinstance(item, dict) else {}) for item in items]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"todos": self._items}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _cap_content(content: str) -> str:
        if len(content) <= MAX_TODO_CONTENT_CHARS:
            return content
        keep = MAX_TODO_CONTENT_CHARS - len(TRUNCATION_MARKER)
        return content[:keep] + TRUNCATION_MARKER

    @classmethod
    def _validate(cls, item: dict[str, Any]) -> dict[str, str]:
        item_id = str(item.get("id", "")).strip() or "?"
        content = str(item.get("content", "")).strip() or "(no description)"
        status = str(item.get("status", "pending")).strip().lower()
        if status not in VALID_STATUSES:
            status = "pending"
        return {"id": item_id, "content": cls._cap_content(content), "status": status}

    @staticmethod
    def _dedupe_by_id(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        last_index: dict[str, int] = {}
        for index, item in enumerate(todos):
            item_id = str(item.get("id", "")).strip() or "?"
            last_index[item_id] = index
        return [todos[index] for index in sorted(last_index.values())]


def todo_path(session_id: str | None) -> Path:
    safe_session = (session_id or "global").replace("/", "_").replace("\\", "_")
    return ensure_home() / "todos" / f"{safe_session}.json"


def todo_tool(todos: list[dict[str, Any]] | None = None, *, merge: bool = False) -> dict[str, Any]:
    context = get_tool_context()
    store = TodoStore(todo_path(context.session_id))
    if todos is not None:
        if not isinstance(todos, list):
            raise ValueError("todos must be an array")
        items = store.write(todos, merge=merge)
    else:
        items = store.read()
    return {
        "todos": items,
        "summary": {
            "total": len(items),
            "pending": sum(1 for item in items if item["status"] == "pending"),
            "in_progress": sum(1 for item in items if item["status"] == "in_progress"),
            "completed": sum(1 for item in items if item["status"] == "completed"),
            "cancelled": sum(1 for item in items if item["status"] == "cancelled"),
        },
        "session_id": context.session_id,
        "path": str(todo_path(context.session_id)),
    }


def register_todo_tools(registry: Any) -> None:
    try:
        registry.register(
            name="todo",
            description=(
                "Manage the current session task list. Call with no parameters to read. "
                "Provide todos=[{id, content, status}] to replace or merge items. "
                "Use for multi-step tasks and keep only one item in_progress."
            ),
            toolset="todo",
            parameters={
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                                },
                            },
                            "required": ["id", "content", "status"],
                        },
                    },
                    "merge": {"type": "boolean"},
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda args: todo_tool(args.get("todos"), merge=bool(args.get("merge", False))),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise

