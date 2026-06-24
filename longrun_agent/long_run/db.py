"""SQLite-backed Long-Run task boards."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from longrun_agent.config import ensure_home, long_run_boards_dir

DEFAULT_BOARD = "default"
READY_STATUSES = {"ready", "blocked"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ready',
    assignee TEXT,
    claimed_by TEXT,
    result TEXT,
    block_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    PRIMARY KEY (task_id, depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    worker TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    log TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS heartbeats (
    worker TEXT PRIMARY KEY,
    task_id TEXT,
    status TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def init_board(board: str = DEFAULT_BOARD) -> dict[str, Any]:
    """Create a board database and worker log directory."""

    path = board_db_path(board)
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "worker-logs").mkdir(parents=True, exist_ok=True)
    with connect(board) as conn:
        conn.execute("SELECT 1")
    return {"board": _clean_board(board), "db_path": str(path), "worker_logs": str(path.parent / "worker-logs")}


def board_db_path(board: str = DEFAULT_BOARD) -> Path:
    ensure_home()
    clean_board = _clean_board(board)
    return long_run_boards_dir() / clean_board / "longrun.db"


def connect(board: str = DEFAULT_BOARD) -> sqlite3.Connection:
    path = board_db_path(board)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def create_task(
    title: str,
    *,
    description: str = "",
    assignee: str | None = None,
    board: str = DEFAULT_BOARD,
) -> dict[str, Any]:
    """Create one ready Long-Run task."""

    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Task title cannot be empty")
    task_id = f"lr-{uuid.uuid4().hex[:10]}"
    with connect(board) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, description, assignee)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, clean_title, description.strip(), assignee),
        )
        conn.commit()
    task = get_task(task_id, board=board)
    if task is None:
        raise RuntimeError("Long-Run task creation failed")
    return task


def list_tasks(*, board: str = DEFAULT_BOARD, status: str | None = None) -> list[dict[str, Any]]:
    """List tasks newest-first."""

    if status:
        sql = """
            SELECT *
            FROM tasks
            WHERE status = ?
            ORDER BY created_at DESC
        """
        params: tuple[Any, ...] = (status,)
    else:
        sql = "SELECT * FROM tasks ORDER BY created_at DESC"
        params = ()
    with connect(board) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_task(task_id: str, *, board: str = DEFAULT_BOARD) -> dict[str, Any] | None:
    """Return one task."""

    with connect(board) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def assign_task(task_id: str, assignee: str, *, board: str = DEFAULT_BOARD) -> dict[str, Any]:
    return update_task(task_id, board=board, assignee=assignee.strip() or None)


def claim_next_task(worker: str, *, board: str = DEFAULT_BOARD) -> dict[str, Any] | None:
    """Atomically claim the oldest ready unblocked task."""

    clean_worker = _clean_worker(worker)
    with connect(board) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT id
            FROM tasks
            WHERE status = 'ready'
              AND id NOT IN (
                SELECT d.task_id
                FROM task_dependencies d
                JOIN tasks t ON t.id = d.depends_on_task_id
                WHERE t.status != 'completed'
              )
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        task_id = str(row["id"])
        run_id = f"run-{uuid.uuid4().hex[:10]}"
        conn.execute(
            """
            UPDATE tasks
            SET status = 'running', claimed_by = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (clean_worker, task_id),
        )
        conn.execute(
            """
            INSERT INTO runs (id, task_id, worker, status)
            VALUES (?, ?, ?, 'running')
            """,
            (run_id, task_id, clean_worker),
        )
        conn.commit()
    heartbeat(clean_worker, task_id=task_id, status="running", board=board)
    return get_task(task_id, board=board)


def complete_task(task_id: str, result: str, *, board: str = DEFAULT_BOARD) -> dict[str, Any]:
    task = update_task(task_id, board=board, status="completed", result=result, block_reason=None)
    _finish_latest_run(task_id, board=board, status="completed", log=result)
    return task


def block_task(task_id: str, reason: str, *, board: str = DEFAULT_BOARD) -> dict[str, Any]:
    return update_task(task_id, board=board, status="blocked", block_reason=reason, claimed_by=None)


def unblock_task(task_id: str, *, board: str = DEFAULT_BOARD) -> dict[str, Any]:
    return update_task(task_id, board=board, status="ready", block_reason=None, claimed_by=None)


def comment_task(
    task_id: str,
    body: str,
    *,
    author: str = "cli",
    board: str = DEFAULT_BOARD,
) -> dict[str, Any]:
    """Add one task comment."""

    if get_task(task_id, board=board) is None:
        raise ValueError(f"Long-Run task not found: {task_id}")
    clean_body = body.strip()
    if not clean_body:
        raise ValueError("Comment cannot be empty")
    with connect(board) as conn:
        cursor = conn.execute(
            """
            INSERT INTO comments (task_id, author, body)
            VALUES (?, ?, ?)
            """,
            (task_id, author.strip() or "cli", clean_body),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def task_comments(task_id: str, *, board: str = DEFAULT_BOARD) -> list[dict[str, Any]]:
    with connect(board) as conn:
        rows = conn.execute(
            "SELECT * FROM comments WHERE task_id = ? ORDER BY id ASC",
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def heartbeat(
    worker: str,
    *,
    task_id: str | None = None,
    status: str = "alive",
    board: str = DEFAULT_BOARD,
) -> dict[str, Any]:
    """Record or update a worker heartbeat."""

    clean_worker = _clean_worker(worker)
    with connect(board) as conn:
        conn.execute(
            """
            INSERT INTO heartbeats (worker, task_id, status)
            VALUES (?, ?, ?)
            ON CONFLICT(worker) DO UPDATE SET
                task_id = excluded.task_id,
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP
            """,
            (clean_worker, task_id, status),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM heartbeats WHERE worker = ?", (clean_worker,)).fetchone()
    return dict(row)


def stats(*, board: str = DEFAULT_BOARD) -> dict[str, Any]:
    with connect(board) as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status").fetchall()
        run_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        heartbeat_count = conn.execute("SELECT COUNT(*) FROM heartbeats").fetchone()[0]
    return {
        "board": _clean_board(board),
        "tasks": {row["status"]: row["count"] for row in rows},
        "runs": run_count,
        "workers": heartbeat_count,
    }


def list_runs(*, board: str = DEFAULT_BOARD) -> list[dict[str, Any]]:
    with connect(board) as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()
    return [dict(row) for row in rows]


def task_log(task_id: str, *, board: str = DEFAULT_BOARD) -> dict[str, Any]:
    task = get_task(task_id, board=board)
    if task is None:
        raise ValueError(f"Long-Run task not found: {task_id}")
    return {
        "task": task,
        "comments": task_comments(task_id, board=board),
        "runs": [run for run in list_runs(board=board) if run["task_id"] == task_id],
    }


def update_task(task_id: str, *, board: str = DEFAULT_BOARD, **fields: Any) -> dict[str, Any]:
    """Update allowed task fields."""

    allowed = {"status", "assignee", "claimed_by", "result", "block_reason"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if get_task(task_id, board=board) is None:
        raise ValueError(f"Long-Run task not found: {task_id}")
    if not updates:
        task = get_task(task_id, board=board)
        if task is None:
            raise RuntimeError("Long-Run task lookup failed")
        return task
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values())
    values.append(task_id)
    with connect(board) as conn:
        conn.execute(
            f"""
            UPDATE tasks
            SET {assignments}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            values,
        )
        conn.commit()
    task = get_task(task_id, board=board)
    if task is None:
        raise RuntimeError("Long-Run task update failed")
    return task


def _finish_latest_run(task_id: str, *, board: str, status: str, log: str) -> None:
    with connect(board) as conn:
        row = conn.execute(
            """
            SELECT id
            FROM runs
            WHERE task_id = ? AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            return
        conn.execute(
            """
            UPDATE runs
            SET status = ?, finished_at = CURRENT_TIMESTAMP, log = ?
            WHERE id = ?
            """,
            (status, log, row["id"]),
        )
        conn.commit()


def _clean_board(board: str) -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in board.strip())
    return clean.strip("-_") or DEFAULT_BOARD


def _clean_worker(worker: str) -> str:
    clean = worker.strip()
    if not clean:
        raise ValueError("Worker name cannot be empty")
    return clean
