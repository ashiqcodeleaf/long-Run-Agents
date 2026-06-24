"""System prompt builder for LongRun Agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from longrun_agent.config import get_longrun_home
from longrun_agent.tools.memory import memory_snapshot
from longrun_agent.tools.catalog import TOOLSET_CATALOG

CONTEXT_FILE_NAMES = ("AGENTS.md", "MYAGENT.md", "CLAUDE.md", ".cursorrules")


@dataclass(frozen=True)
class PromptBuildResult:
    """Built prompt plus inspectable metadata."""

    system_prompt: str
    context_files: tuple[str, ...]


def build_system_prompt(
    *,
    workspace: Path | None = None,
    config: dict[str, Any] | None = None,
) -> PromptBuildResult:
    """Build the cached system prompt for a new session."""

    root = (workspace or Path.cwd()).resolve()
    max_chars = int((config or {}).get("context", {}).get("context_file_max_chars", 12000))
    context_blocks, loaded_files = load_context_file_blocks(root, max_chars=max_chars)

    parts = [
        "You are LongRun Agent, a CLI-only coding agent.",
        "",
        "Core rules:",
        "- Preserve the user's working files unless explicitly asked to change them.",
        "- Explain each implementation stage before moving to the next one.",
        "- Keep the system prompt stable for the life of the session.",
        "- Use tools only through the central executor when tools are available.",
        "- Prefer file_write for creating or replacing text files; it creates parent directories automatically.",
        "- Use terminal_run for commands and verification, not for multi-line file creation unless no file tool can do the job.",
        "- After using a tool, inspect the tool result. If a command exit_code is non-zero, treat it as failed and fix it.",
        "",
        "Current MVP capabilities:",
        "- persistent sessions",
        "- cached system prompt snapshots",
        "- context file loading",
        "- local shell, background process, file, memory, session-search, skills, todo, clarify, code-execution, subagent, and long-run tools",
        "- skills as both user-turn slash commands and model-callable skill discovery/view tools",
        "",
        "Toolset map:",
        *_toolset_prompt_lines(),
        "",
        "Unavailable in this CLI-only MVP unless explicitly added later:",
        "- gateway/messaging platforms",
        "- desktop app, web dashboard, browser automation, computer-use, voice, image/video generation",
        "",
        f"LongRun home: {get_longrun_home()}",
        f"Workspace: {root}",
        "",
        "Memory snapshot:",
        memory_snapshot(),
    ]

    if context_blocks:
        parts.extend(["", "Project instructions:", "", *context_blocks])
    else:
        parts.extend(["", "Project instructions: none found."])

    return PromptBuildResult(
        system_prompt="\n".join(parts).strip() + "\n",
        context_files=tuple(loaded_files),
    )


def _toolset_prompt_lines() -> list[str]:
    lines: list[str] = []
    for item in TOOLSET_CATALOG:
        if item.mvp_status in {"imported", "mvp-only", "dynamic"}:
            lines.append(f"- {item.name} ({item.category}): {item.description}")
    return lines


def load_context_file_blocks(workspace: Path, *, max_chars: int) -> tuple[list[str], list[str]]:
    """Load known project instruction files from the workspace root upward."""

    blocks: list[str] = []
    loaded_files: list[str] = []

    for path in _candidate_context_files(workspace):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        truncated = text[:max_chars]
        if len(text) > max_chars:
            truncated += "\n\n[LongRun truncated this context file for the MVP prompt budget.]"

        loaded_files.append(str(path))
        blocks.append(f"## {path.name}\n\n{truncated.strip()}")

    return blocks, loaded_files


def _candidate_context_files(workspace: Path) -> list[Path]:
    """Return nearest context files without broad recursive scanning."""

    candidates: list[Path] = []
    current = workspace.resolve()
    seen: set[Path] = set()

    while True:
        for name in CONTEXT_FILE_NAMES:
            path = current / name
            if path.exists() and path.is_file() and path not in seen:
                seen.add(path)
                candidates.append(path)
        if current.parent == current:
            break
        current = current.parent
    return candidates
