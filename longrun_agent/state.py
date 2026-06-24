"""SQLite state helpers for LongRun Agent."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Literal

from longrun_agent.config import ensure_home, state_db_path

MessageRole = Literal["user", "assistant", "system", "tool"]
VALID_MESSAGE_ROLES = {"user", "assistant", "system", "tool"}
AUTO_TITLE_PLACEHOLDERS = {"Untitled session", "Interactive LongRun session"}


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
    metadata TEXT NOT NULL DEFAULT '{}',
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

CREATE TABLE IF NOT EXISTS context_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_message_count INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS agent_jobs (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    session_id TEXT,
    process_id TEXT,
    result TEXT,
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the Stage 0 SQLite database and ensure base tables exist."""

    ensure_home()
    path = db_path or state_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
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


def ensure_session(session_id: str | None = None, title: str | None = None) -> dict[str, str]:
    """Return an existing session or create a new one."""

    if session_id:
        session = get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        return session
    return create_session(title)


def update_session_title(session_id: str, title: str) -> dict[str, str]:
    """Set a session title."""

    clean_title = _normalize_session_title(title)
    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")
    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (clean_title, session_id),
        )
        conn.commit()
    session = get_session(session_id)
    if session is None:
        raise RuntimeError("Session title update failed")
    return session


def maybe_auto_title_session(session_id: str, user_message: str) -> dict[str, str]:
    """Rename generic sessions from the first useful user message."""

    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id}")
    if str(session.get("title") or "") not in AUTO_TITLE_PLACEHOLDERS:
        return session
    existing_messages = list_messages(session_id)
    user_messages = [message for message in existing_messages if message["role"] == "user"]
    if len(user_messages) > 1:
        return session
    title = infer_session_title(user_message)
    if not title:
        return session
    return update_session_title(session_id, title)


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


def add_message(
    session_id: str,
    role: MessageRole,
    content: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add one message to a session."""

    if role not in VALID_MESSAGE_ROLES:
        raise ValueError(f"Invalid message role: {role}")
    message_metadata = metadata or {}
    if not content.strip() and not message_metadata:
        raise ValueError("Message content cannot be empty")
    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")

    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (session_id, role, content, json.dumps(message_metadata, sort_keys=True)),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, session_id, role, content, metadata, created_at
            FROM messages
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return _row_to_message(row)


def list_messages(session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    """List messages for a session oldest-first."""

    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")

    sql = """
        SELECT id, session_id, role, content, metadata, created_at
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
    return [_row_to_message(row) for row in rows]


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


def get_prompt_snapshot(session_id: str) -> dict[str, str] | None:
    """Return the cached system prompt for a session."""

    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT session_id, system_prompt, created_at, updated_at
            FROM prompt_snapshots
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def set_prompt_snapshot(session_id: str, system_prompt: str) -> dict[str, str]:
    """Persist or replace the cached system prompt for a session."""

    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")
    if not system_prompt.strip():
        raise ValueError("System prompt cannot be empty")

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO prompt_snapshots (session_id, system_prompt)
            VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                system_prompt = excluded.system_prompt,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, system_prompt),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT session_id, system_prompt, created_at, updated_at
            FROM prompt_snapshots
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    return dict(row)


def get_latest_context_summary(session_id: str) -> dict[str, str | int] | None:
    """Return the newest stored context summary for a session."""

    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, session_id, summary, source_message_count, created_at
            FROM context_summaries
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def add_context_summary(
    session_id: str,
    summary: str,
    source_message_count: int,
) -> dict[str, str | int]:
    """Store a deterministic context summary."""

    if get_session(session_id) is None:
        raise ValueError(f"Session not found: {session_id}")
    if not summary.strip():
        raise ValueError("Context summary cannot be empty")

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO context_summaries (session_id, summary, source_message_count)
            VALUES (?, ?, ?)
            """,
            (session_id, summary, source_message_count),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, session_id, summary, source_message_count, created_at
            FROM context_summaries
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


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


def create_agent_job(prompt: str, *, status: str = "queued") -> dict[str, Any]:
    """Create a durable subagent/background job."""

    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("Job prompt cannot be empty")
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_jobs (id, prompt, status)
            VALUES (?, ?, ?)
            """,
            (job_id, clean_prompt, status),
        )
        conn.commit()
    job = get_agent_job(job_id)
    if job is None:
        raise RuntimeError("Job creation failed")
    return job


def get_agent_job(job_id: str) -> dict[str, Any] | None:
    """Return one durable agent job."""

    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, prompt, status, session_id, process_id, result, error, created_at, updated_at
            FROM agent_jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def list_agent_jobs(status: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
    """List durable agent jobs."""

    if status:
        sql = """
            SELECT id, prompt, status, session_id, process_id, result, error, created_at, updated_at
            FROM agent_jobs
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        params: tuple[Any, ...] = (status, limit)
    else:
        sql = """
            SELECT id, prompt, status, session_id, process_id, result, error, created_at, updated_at
            FROM agent_jobs
            ORDER BY created_at DESC
            LIMIT ?
        """
        params = (limit,)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def update_agent_job(job_id: str, **fields: Any) -> dict[str, Any]:
    """Update selected fields on one durable agent job."""

    allowed = {"status", "session_id", "process_id", "result", "error"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        job = get_agent_job(job_id)
        if job is None:
            raise ValueError(f"Agent job not found: {job_id}")
        return job
    if get_agent_job(job_id) is None:
        raise ValueError(f"Agent job not found: {job_id}")

    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values())
    values.append(job_id)
    with connect() as conn:
        conn.execute(
            f"""
            UPDATE agent_jobs
            SET {assignments}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            values,
        )
        conn.commit()
    job = get_agent_job(job_id)
    if job is None:
        raise RuntimeError("Agent job update failed")
    return job


def claim_next_agent_job() -> dict[str, Any] | None:
    """Atomically claim the oldest queued job in this local SQLite DB."""

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT id
            FROM agent_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        job_id = str(row["id"])
        conn.execute(
            """
            UPDATE agent_jobs
            SET status = 'claimed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (job_id,),
        )
        conn.commit()
    return get_agent_job(job_id)


def search_messages(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search persisted session messages with a simple LIKE query."""

    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Search query cannot be empty")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    pattern = f"%{clean_query}%"
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                m.id,
                m.session_id,
                s.title,
                m.role,
                m.content,
                m.metadata,
                m.created_at
            FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE m.content LIKE ?
            ORDER BY m.id DESC
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()
    return [_row_to_search_result(row, clean_query) for row in rows]


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply small additive migrations for existing MVP databases."""

    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(messages)").fetchall()
    }
    if "metadata" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")


def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
    message = dict(row)
    message["metadata"] = _parse_metadata(str(message.get("metadata", "{}")))
    return message


def _row_to_search_result(row: sqlite3.Row, query: str) -> dict[str, Any]:
    result = _row_to_message(row)
    content = str(result["content"])
    lowered = content.lower()
    index = lowered.find(query.lower())
    if index < 0:
        snippet = content[:220]
    else:
        start = max(0, index - 80)
        end = min(len(content), index + len(query) + 140)
        snippet = content[start:end]
    result["snippet"] = " ".join(snippet.split())
    return result


def _parse_metadata(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def infer_session_title(user_message: str, *, max_chars: int = 64) -> str:
    """Create a compact title from the first user message."""

    text = _strip_goal_wrapper(user_message)
    text = " ".join(text.split()).strip(" .,:;!?")
    if not text:
        return ""
    prefixes = (
        "uv run longrun ",
        "longrun ",
        "please ",
        "can you ",
        "could you ",
        "i want ",
        "i need ",
    )
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip(" -_/.,:;") + "…"


def _normalize_session_title(title: str) -> str:
    clean = " ".join(str(title or "").split()).strip()
    if not clean:
        return "Untitled session"
    return clean[:80].rstrip(" -_/.,:;")


def _strip_goal_wrapper(user_message: str) -> str:
    text = str(user_message or "")
    marker = "User message:\n"
    if marker in text:
        return text.split(marker, 1)[1]
    return text
