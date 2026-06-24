"""LongRun tool catalog and MyAgent import map."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolsetInfo:
    name: str
    category: str
    description: str
    mvp_status: str
    myagent_source: str


TOOLSET_CATALOG: tuple[ToolsetInfo, ...] = (
    ToolsetInfo(
        "file",
        "Core Workspace",
        "Read, write, patch, and search local workspace files with file-state tracking.",
        "imported",
        "MyAgent file toolset: read_file/write_file/patch/search_files",
    ),
    ToolsetInfo(
        "terminal",
        "Core Workspace",
        "Run local foreground shell commands and capture stdout, stderr, and exit code.",
        "imported",
        "MyAgent terminal toolset: terminal",
    ),
    ToolsetInfo(
        "process",
        "Core Workspace",
        "Start, poll, list, and kill background shell processes.",
        "imported",
        "MyAgent terminal toolset: process",
    ),
    ToolsetInfo(
        "memory",
        "Context",
        "Store and retrieve local user/session memory.",
        "imported",
        "MyAgent memory toolset",
    ),
    ToolsetInfo(
        "session",
        "Context",
        "Search previous LongRun session messages.",
        "imported",
        "MyAgent session_search toolset",
    ),
    ToolsetInfo(
        "subagent",
        "Agents",
        "Create a child LongRun agent for a focused task with recursion disabled by default.",
        "imported",
        "MyAgent delegation toolset",
    ),
    ToolsetInfo(
        "long-run",
        "Agents",
        "Durable task coordination renamed from Kanban for CLI-only long-running workflows.",
        "imported",
        "MyAgent kanban plugin, reduced for LongRun",
    ),
    ToolsetInfo(
        "diagnostic",
        "Diagnostics",
        "Small proof tools used to validate model-to-tool execution.",
        "mvp-only",
        "LongRun local diagnostic tool",
    ),
    ToolsetInfo(
        "skills",
        "Context",
        "List and read skill documents as user-turn context.",
        "imported",
        "MyAgent skills_list/skill_view/skill_manage",
    ),
    ToolsetInfo(
        "todo",
        "Planning",
        "Structured task planning/tracking for multi-step work.",
        "imported",
        "MyAgent todo toolset",
    ),
    ToolsetInfo(
        "clarify",
        "Interaction",
        "Ask the user a clarification question from inside the agent loop.",
        "imported",
        "MyAgent clarify toolset",
    ),
    ToolsetInfo(
        "code_execution",
        "Execution",
        "Run Python scripts that call tools programmatically to reduce model round trips.",
        "imported",
        "MyAgent execute_code toolset",
    ),
    ToolsetInfo(
        "cronjob",
        "Long-Run",
        "Create and manage CLI-only scheduled agent jobs.",
        "imported",
        "MyAgent cronjob toolset, reduced to local CLI job storage and manual/tick execution",
    ),
    ToolsetInfo(
        "web",
        "Research",
        "Web search/content extraction.",
        "excluded-now",
        "MyAgent web/search toolsets; excluded from the OpenAI-only CLI MVP for now",
    ),
    ToolsetInfo(
        "browser",
        "Research",
        "Browser automation for navigation, click, type, scroll, snapshots, and console.",
        "excluded-now",
        "MyAgent browser toolset from the attached tool list; intentionally not wired yet",
    ),
    ToolsetInfo(
        "computer_use",
        "Computer Use",
        "OS desktop control and screenshots.",
        "excluded-now",
        "MyAgent computer_use toolset; explicitly out of CLI-only MVP scope",
    ),
    ToolsetInfo(
        "image_gen",
        "Media",
        "Image generation.",
        "excluded-now",
        "MyAgent image_gen toolset; explicitly out of scope",
    ),
    ToolsetInfo(
        "vision",
        "Media",
        "Image analysis.",
        "excluded-now",
        "MyAgent vision toolset; can be reconsidered after core CLI stabilizes",
    ),
    ToolsetInfo(
        "tts",
        "Media",
        "Text-to-speech output.",
        "excluded-now",
        "MyAgent tts toolset; explicitly out of scope",
    ),
    ToolsetInfo(
        "gateway-platforms",
        "Gateway",
        "Telegram, WhatsApp, Slack, Discord, Email, SMS, Matrix, Feishu, WeCom, Yuanbao, and similar adapters.",
        "excluded",
        "MyAgent gateway platform toolsets; explicitly out of scope",
    ),
)


def catalog_by_name() -> dict[str, ToolsetInfo]:
    return {item.name: item for item in TOOLSET_CATALOG}


def classify_toolset(name: str) -> ToolsetInfo:
    catalog = catalog_by_name()
    if name in catalog:
        return catalog[name]
    return ToolsetInfo(
        name=name,
        category="Plugin/MCP",
        description="Runtime toolset registered by a plugin or MCP server.",
        mvp_status="dynamic",
        myagent_source="LongRun plugin/MCP registry",
    )


def group_tool_definitions(definitions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for definition in definitions:
        info = classify_toolset(str(definition.get("toolset", "default")))
        grouped.setdefault(info.category, []).append(definition)
    return dict(sorted(grouped.items()))
