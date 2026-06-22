"""SQLite state helpers for LongRun Agent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from longrun_agent.config import ensure_home, state_db_path


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
