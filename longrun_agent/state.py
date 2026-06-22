"""SQLite state helpers for LongRun Agent."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Literal

from longrun_agent.config import ensure_home, state_db_path

MessageRole = Literal["user", "assistant", "system", "tool"]
VALID_MESSAGE_ROLES = {"user", "assistant", "system", "tool"}


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS prompt_snapshots (
    session_id TEXT PRIMARY KEY,
    system_prompt TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the Stage 0 SQLite database and ensure base tables exist."""

    ensure_home()
    path = db_path or state_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_state_summary() -> dict[str, str | int]:
    """Return a small status snapshot for the CLI."""

    path = state_db_path()
    with connect(path) as conn:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    return {
        "db_path": str(path),
        "sessions": session_count,
        "messages": message_count,
    }


def create_session(title: str | None = None) -> dict[str, str]:
    """Create a durable conversation session."""

    session_id = f"session-{uuid.uuid4().hex[:12]}"
    session_title = title or "Untitled session"
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title) VALUES (?, ?)",
            (session_id, session_title),
        )
        conn.commit()
    session = get_session(session_id)
    if session is None:
        raise RuntimeError("Session creation failed")
    return session


def get_session(session_id: str) -> dict[str, str] | None:
    """Return one session by id."""

    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def list_sessions(limit: int = 20) -> list[dict[str, str | int]]:
    """List recent sessions with message counts."""

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.title,
                s.created_at,
                s.updated_at,
                COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def touch_session(session_id: str) -> None:
    """Update a session timestamp after message changes."""

    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        conn.commit()


def add_message(session_id: str, role: MessageRole, content: str) -> dict[str, str | int]:
    """Add one message to a session."""

    if role not in VALID_MESSAGE_ROLES:
        raise ValueError(f"Invalid message role: {role}")
    if not content.strip():
        raise ValueError("Message content cannot be empty")
    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")

    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM messages
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


def list_messages(session_id: str, limit: int | None = None) -> list[dict[str, str | int]]:
    """List messages for a session oldest-first."""

    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")

    sql = """
        SELECT id, session_id, role, content, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY id ASC
    """
    params: tuple[str] | tuple[str, int]
    if limit is None:
        params = (session_id,)
    else:
        sql += " LIMIT ?"
        params = (session_id, limit)

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def clear_messages(session_id: str) -> int:
    """Delete all messages for a session while keeping the session row."""

    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")

    with connect() as conn:
        cursor = conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        deleted = cursor.rowcount
        conn.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        conn.commit()
    return deleted


def save_transcript(session_id: str, output_path: Path) -> Path:
    """Save a session transcript as Markdown."""

    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id}")

    messages = list_messages(session_id)
    lines = [
        f"# {session['title']}",
        "",
        f"Session: `{session['id']}`",
        "",
    ]

    if not messages:
        lines.append("_No messages._")
    for message in messages:
        lines.extend(
            [
                f"## {str(message['role']).title()}",
                "",
                str(message["content"]),
                "",
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path
