"""Banner, panels, activity lines, and help rendering for LongRun CLI."""

from __future__ import annotations

import shutil
import sys
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from rich import box
    from rich.console import Console
    from rich.markup import escape as rich_escape
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - plain fallback for minimal installs.
    box = None  # type: ignore[assignment]
    Console = None  # type: ignore[assignment]
    rich_escape = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]

from longrun_agent import __version__
from longrun_agent.cli.commands import COMMANDS_BY_CATEGORY
from longrun_agent.config import config_path, get_longrun_home, load_config
from longrun_agent.state import get_state_summary, list_agent_jobs
from longrun_agent.tools.registry import registry
from longrun_agent.tools.skills import list_skills
from longrun_agent.workspace import workspace_status

_CONSOLE = Console(highlight=False) if Console is not None else None


def print_banner(*, session_id: str | None = None) -> None:
    config = load_config()
    local = workspace_status()
    state = get_state_summary()
    tools = registry.get_definitions()
    skills = list_skills(source="all")
    toolsets = sorted({str(tool["toolset"]) for tool in tools})
    skill_groups = _skill_groups(skills)
    subagent_tools = [str(tool["name"]) for tool in tools if str(tool.get("toolset")) == "subagent"]
    agent_jobs = list_agent_jobs(limit=25)

    if _CONSOLE is not None and Table is not None and Panel is not None:
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(justify="right", style="cyan", width=10)
        table.add_column(style="white")
        table.add_row("model", f"{config['model']} [dim]({config['provider']})[/]")
        table.add_row("session", session_id or "[dim]new on first model turn[/]")
        table.add_row("project", _short_path(local["workspace"]))
        table.add_row("home", _short_path(str(get_longrun_home())))
        table.add_row("state", f"{state['sessions']} sessions | {state['messages']} messages")
        table.add_row("tools", f"{len(tools)} tools across {len(toolsets)} toolsets")
        table.add_row("", _truncate(", ".join(toolsets), 76))
        table.add_row("agents", _agent_status(subagent_tools, len(agent_jobs)))
        table.add_row("skills", f"{len(skills)} skills across {len(skill_groups)} groups")
        table.add_row("", _truncate(_format_skill_groups(skill_groups), 76))
        table.add_row("next", "/help | /plan <task> | /goal <objective> | /quit")
        _CONSOLE.print()
        _CONSOLE.print(
            Panel(
                table,
                title=f"[bold cyan]LongRun v{__version__}[/] [dim]CLI agent workspace[/]",
                subtitle="[dim]agent core ready[/]",
                border_style="cyan",
                box=box.ROUNDED if box is not None else None,
            )
        )
        _CONSOLE.print()
        return

    print("")
    print_box(
        "LongRun online",
        [
            f"LongRun v{__version__} | CLI-only agent workspace",
            "",
            f"  model     {config['model']} | {config['provider']}",
            f"  session   {session_id or 'new on first model turn'}",
            f"  project   {_short_path(local['workspace'])}",
            f"  home      {_short_path(str(get_longrun_home()))}",
            f"  state     {state['sessions']} sessions | {state['messages']} messages",
            "",
            f"  tools     {len(tools)} tools across {len(toolsets)} toolsets",
            f"            {_truncate(', '.join(toolsets), 58)}",
            f"  agents    {_agent_status(subagent_tools, len(agent_jobs))}",
            f"  skills    {len(skills)} skills across {len(skill_groups)} groups",
            f"            {_truncate(_format_skill_groups(skill_groups), 58)}",
            "",
            "  /help for commands | /plan <task> | /goal <objective> | /quit",
        ],
    )
    print("")


def print_setup_guidance() -> None:
    print_box(
        "Setup",
        [
            "LongRun can run slash commands now, but model chat needs auth.",
            "",
            "Configure one of:",
            "  longrun setup",
            "  longrun auth set-openai-key",
            "  longrun auth login-codex",
            "  longrun auth import-codex-cli",
            "",
            f"Config: {config_path()}",
        ],
    )


def print_slash_help() -> None:
    if _CONSOLE is not None and Table is not None and Panel is not None:
        rows = Table.grid(expand=True, padding=(0, 2))
        rows.add_column(style="bold cyan", width=34)
        rows.add_column(style="white")
        rows.add_column(style="dim", width=12)
        for category, commands in COMMANDS_BY_CATEGORY.items():
            rows.add_row(category, "", "")
            for command in commands:
                aliases = ", ".join("/" + alias for alias in command.aliases)
                command_text = f"/{command.name} {command.args_hint}".strip()
                if rich_escape is not None:
                    command_text = rich_escape(command_text)
                    description = rich_escape(command.description)
                    aliases = rich_escape(aliases)
                else:
                    description = command.description
                rows.add_row(f"  {command_text}", description, aliases)
            rows.add_row("", "", "")
        _CONSOLE.print(
            Panel(
                rows,
                title="[bold cyan]LongRun slash commands[/]",
                subtitle="[dim]type / to open the command popup[/]",
                border_style="cyan",
                box=box.ROUNDED if box is not None else None,
            )
        )
        return

    lines: list[str] = []
    for category, commands in COMMANDS_BY_CATEGORY.items():
        if lines:
            lines.append("")
        lines.append(category)
        for command in commands:
            aliases = f" ({', '.join('/' + alias for alias in command.aliases)})" if command.aliases else ""
            lines.append(f"  {command.display:<34} {command.description}{aliases}")
    print_box("LongRun slash commands", lines)


def print_response_box(title: str, body: str, *, footer: list[str] | None = None) -> None:
    if _CONSOLE is not None and Panel is not None and Text is not None:
        text = Text()
        text.append(body.rstrip() or "(empty)")
        if footer:
            text.append("\n\n")
            for index, line in enumerate(footer):
                if index:
                    text.append("\n")
                text.append(line, style="dim")
        _CONSOLE.print(
            Panel(
                text,
                title=f"[bold cyan]{title}[/]",
                border_style="cyan",
                box=box.ROUNDED if box is not None else None,
            )
        )
        return

    lines = _wrap_lines(body)
    if footer:
        lines.append("")
        lines.extend(footer)
    print_box(title, lines)


def print_activity(message: str, *, status: str = "info") -> None:
    """Print one compact activity line."""

    styles = {
        "info": "dim cyan",
        "ok": "green",
        "warn": "yellow",
        "error": "red",
        "model": "magenta",
        "tool": "blue",
    }
    labels = {
        "info": "INFO",
        "ok": "OK",
        "warn": "WARN",
        "error": "ERROR",
        "model": "MODEL",
        "tool": "TOOL",
    }
    if _CONSOLE is not None:
        clean = rich_escape(message) if rich_escape is not None else message
        label = labels.get(status, "INFO")
        _CONSOLE.print(f"[dim]|[/] [{styles.get(status, 'dim')}]{label:<5}[/] [dim]-[/] {clean}")
    else:
        print(f"| {labels.get(status, 'INFO'):<5} - {message}")


def print_agent_bootstrap(rows: dict[str, Any]) -> None:
    if _CONSOLE is not None and Table is not None and Panel is not None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", justify="right")
        table.add_column(style="white")
        for key, value in rows.items():
            table.add_row(str(key), str(value))
        _CONSOLE.print(
            Panel(
                table,
                title="[bold cyan]Agent initializing[/]",
                border_style="blue",
                box=box.ROUNDED if box is not None else None,
            )
        )
        return
    print_box("Agent initializing", [f"{key}: {value}" for key, value in rows.items()])


def print_box(title: str, lines: list[str]) -> None:
    width = min(max(shutil.get_terminal_size((100, 24)).columns, 72), 110)
    inner = width - 4
    heading = f" {title} "
    top = "+" + heading + "-" * max(0, width - 2 - len(heading)) + "+"
    print(top)
    for line in lines:
        for wrapped in _wrap_line(line, inner):
            print(f"| {wrapped:<{inner}} |")
    print("+" + "-" * (width - 2) + "+")


def _wrap_lines(text: str) -> list[str]:
    rows: list[str] = []
    for raw in text.splitlines() or [""]:
        rows.extend(_wrap_line(raw, min(max(shutil.get_terminal_size((100, 24)).columns, 72), 110) - 4))
    return rows


def _wrap_line(line: str, width: int) -> list[str]:
    if not line:
        return [""]
    return textwrap.wrap(line, width=width, replace_whitespace=False, drop_whitespace=False) or [line[:width]]


def _skill_groups(skills: list[dict[str, str]]) -> dict[str, int]:
    groups: dict[str, int] = defaultdict(int)
    for skill in skills:
        path = Path(skill["path"])
        group = path.parent.parent.name if path.parent.name else "skills"
        groups[group] += 1
    return dict(sorted(groups.items()))


def _format_skill_groups(groups: dict[str, int]) -> str:
    return ", ".join(f"{name}:{count}" for name, count in groups.items())


def _agent_status(subagent_tools: list[str], job_count: int) -> str:
    if subagent_tools:
        return f"delegate tool enabled | {job_count} stored jobs"
    return f"no delegate tool loaded | {job_count} stored jobs"


def _short_path(path: str) -> str:
    text = str(path)
    home = str(Path.home())
    if text.startswith(home):
        text = "~" + text[len(home):]
    return _truncate(text, 62)


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(0, width - 3)] + "..."
