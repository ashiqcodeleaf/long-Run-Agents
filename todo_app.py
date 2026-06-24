"""Standalone to-do list app for LongRun Agent MVP.

Run this file directly to open a simple prompt-based to-do list.
"""

from __future__ import annotations

from longrun_agent.cli.todo import add_todo, clear_todos, complete_todo, list_todos


def render_todos() -> None:
    items = list_todos()
    print("\nCurrent to-dos:")
    if not items:
        print("  (none)")
        return
    for item in items:
        mark = "x" if item.done else " "
        print(f"  [{mark}] {item.id}: {item.title}")


def main() -> int:
    print("LongRun To-Do App")
    print("Type a task and press Enter to add it.")
    print("Commands: done <id>, list, clear, quit")

    while True:
        render_todos()
        text = input("\nAdd task or command> ").strip()
        if not text:
            continue
        lower = text.lower()
        if lower in {"quit", "exit", "q"}:
            print("Goodbye.")
            return 0
        if lower == "list":
            continue
        if lower == "clear":
            removed = clear_todos()
            print(f"Cleared {removed} todo(s).")
            continue
        if lower.startswith("done "):
            try:
                todo_id = int(text.split(maxsplit=1)[1])
                item = complete_todo(todo_id)
                print(f"Completed: {item.id} {item.title}")
            except (ValueError, KeyError):
                print("Invalid todo id.")
            continue

        item = add_todo(text)
        print(f"Added: {item.id} {item.title}")


if __name__ == "__main__":
    raise SystemExit(main())
