"""Small local to-do list storage for the LongRun CLI MVP."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from longrun_agent.config import ensure_home, get_longrun_home

_TODO_FILENAME = "todo.json"


@dataclass(frozen=True)
class TodoItem:
    id: int
    title: str
    done: bool
    created_at: str
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


def todo_path() -> Path:
    ensure_home()
    return get_longrun_home() / _TODO_FILENAME


def load_todos() -> list[TodoItem]:
    path = todo_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    items: list[TodoItem] = []
    for raw in data:
        items.append(
            TodoItem(
                id=int(raw["id"]),
                title=str(raw["title"]),
                done=bool(raw.get("done", False)),
                created_at=str(raw.get("created_at", _now_iso())),
                completed_at=raw.get("completed_at"),
            )
        )
    return items


def save_todos(items: list[TodoItem]) -> Path:
    path = todo_path()
    payload = [item.to_dict() for item in items]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def add_todo(title: str) -> TodoItem:
    items = load_todos()
    next_id = 1 if not items else max(item.id for item in items) + 1
    item = TodoItem(id=next_id, title=title.strip(), done=False, created_at=_now_iso())
    items.append(item)
    save_todos(items)
    return item


def list_todos() -> list[TodoItem]:
    return load_todos()


def complete_todo(todo_id: int) -> TodoItem:
    items = load_todos()
    updated: list[TodoItem] = []
    found: TodoItem | None = None
    for item in items:
        if item.id == todo_id:
            found = TodoItem(
                id=item.id,
                title=item.title,
                done=True,
                created_at=item.created_at,
                completed_at=_now_iso(),
            )
            updated.append(found)
        else:
            updated.append(item)
    if found is None:
        raise KeyError(f"Todo not found: {todo_id}")
    save_todos(updated)
    return found


def clear_todos() -> int:
    path = todo_path()
    if not path.exists():
        return 0
    removed = len(load_todos())
    path.write_text("[]\n", encoding="utf-8")
    return removed


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
