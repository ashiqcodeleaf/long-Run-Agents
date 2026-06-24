"""Previous-session search tool."""

from __future__ import annotations

from typing import Any

from longrun_agent.state import search_messages


def search_session_messages(query: str, *, limit: int = 20) -> dict[str, Any]:
    """Search saved session messages."""

    rows = search_messages(query, limit=limit)
    return {
        "query": query,
        "matches": [
            {
                "message_id": row["id"],
                "session_id": row["session_id"],
                "title": row["title"],
                "role": row["role"],
                "created_at": row["created_at"],
                "snippet": row["snippet"],
            }
            for row in rows
        ],
    }


def register_session_search_tools(registry: Any) -> None:
    """Register session search with the central registry."""

    try:
        registry.register(
            name="session_search",
            description="Search previous LongRun session messages.",
            toolset="session",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=lambda args: search_session_messages(
                str(args.get("query", "")),
                limit=int(args.get("limit", 20)),
            ),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise
