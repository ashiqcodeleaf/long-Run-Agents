"""MyAgent-style slash command registry for the LongRun interactive CLI."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

try:
    from prompt_toolkit.completion import Completer, Completion
except ImportError:  # pragma: no cover - prompt_toolkit is optional outside the CLI.
    Completer = object  # type: ignore[assignment,misc]
    Completion = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CommandDef:
    name: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()
    args_hint: str = ""

    @property
    def display(self) -> str:
        suffix = f" {self.args_hint}" if self.args_hint else ""
        return f"/{self.name}{suffix}"


COMMAND_REGISTRY: tuple[CommandDef, ...] = (
    CommandDef("help", "Show this help screen.", "Info", aliases=("?",)),
    CommandDef("usage", "Show session/model usage counters.", "Info"),
    CommandDef("debug", "Show diagnostic state.", "Info"),
    CommandDef("quit", "Exit LongRun.", "Exit", aliases=("exit", "q")),
    CommandDef("new", "Start a new session.", "Session", args_hint="[title]"),
    CommandDef("clear", "Clear the current session messages.", "Session"),
    CommandDef("history", "Show current session history.", "Session"),
    CommandDef("resume", "Resume a previous session.", "Session", args_hint="<session-id>"),
    CommandDef("sessions", "List recent sessions.", "Session"),
    CommandDef("save", "Save the current session transcript.", "Session", args_hint="[path]"),
    CommandDef("retry", "Retry the previous user turn when available.", "Session"),
    CommandDef("undo", "Undo the last local session message when available.", "Session"),
    CommandDef("status", "Show workspace, config, auth, and state status.", "Session"),
    CommandDef("stop", "Stop the current foreground action.", "Session"),
    CommandDef("plan", "Create a structured plan for a task.", "Session", args_hint="<task>"),
    CommandDef("goal", "Set, run, pause, or inspect a standing goal.", "Session", args_hint="[text | run | pause | resume | clear | status]"),
    CommandDef("subgoal", "Set or inspect a focused subgoal.", "Session", args_hint="[text | clear | status]"),
    CommandDef("compress", "Compress the current session context.", "Session"),
    CommandDef("rollback", "Rollback a checkpoint.", "Session", args_hint="[checkpoint-id]"),
    CommandDef("model", "Show or set the active model.", "Configuration", args_hint="[model]"),
    CommandDef("config", "Show config or set a config value.", "Configuration", args_hint="[key value]"),
    CommandDef("reasoning", "Show or set reasoning effort.", "Configuration", args_hint="[minimal|low|medium|high]"),
    CommandDef("yolo", "Toggle approval bypass mode for trusted local work.", "Configuration", args_hint="[on|off|status]"),
    CommandDef("verbose", "Show or toggle verbose mode.", "Configuration", args_hint="[on|off]"),
    CommandDef("tools", "List registered tools.", "Tools & Skills"),
    CommandDef("toolsets", "List registered toolsets.", "Tools & Skills"),
    CommandDef("skills", "List installed and bundled skills.", "Tools & Skills"),
    CommandDef("memory", "List saved memory.", "Tools & Skills"),
    CommandDef("plugins", "List plugins.", "Tools & Skills"),
    CommandDef("mcp", "List MCP servers.", "Tools & Skills"),
    CommandDef("reload", "Reload plugins and MCP tool cache.", "Tools & Skills"),
    CommandDef("reload-mcp", "Reload MCP tools.", "Tools & Skills"),
    CommandDef("reload-skills", "Refresh skill inventory.", "Tools & Skills"),
    CommandDef("agents", "Show subagent defaults and jobs.", "Multi-Agent"),
    CommandDef("background", "List or manage background jobs.", "Multi-Agent", args_hint="[list|show|poll|kill]"),
    CommandDef("queue", "List or manage durable queued jobs.", "Multi-Agent", args_hint="[list|claim|add]"),
    CommandDef("cron", "Manage scheduled agent jobs.", "Long-Run", args_hint="[add|list|run|tick|...]"),
    CommandDef("long-run", "Manage durable Long-Run boards.", "Long-Run", aliases=("kanban",), args_hint="[init|list|create|...]"),
)


COMMANDS_BY_CATEGORY: dict[str, list[CommandDef]] = defaultdict(list)
for command in COMMAND_REGISTRY:
    COMMANDS_BY_CATEGORY[command.category].append(command)

COMMANDS: dict[str, CommandDef] = {}
for command in COMMAND_REGISTRY:
    COMMANDS[command.name] = command
    for alias in command.aliases:
        COMMANDS[alias] = command


def resolve_command(name: str) -> CommandDef | None:
    return COMMANDS.get(name.strip().lower().lstrip("/"))


def command_names() -> list[str]:
    return sorted(COMMANDS)


class SlashCommandCompleter(Completer):
    """Autocomplete slash commands and installed skill commands."""

    def __init__(
        self,
        *,
        skill_commands_provider: Callable[[], Mapping[str, dict[str, Any]]] | None = None,
    ) -> None:
        self._skill_commands_provider = skill_commands_provider

    def get_completions(self, document: Any, complete_event: Any) -> Any:
        if Completion is None:
            return
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        if " " in text:
            return

        word = text[1:].lower()
        for name, command in sorted(COMMANDS.items()):
            if not name.startswith(word):
                continue
            display = f"/{name}"
            meta = command.description
            replacement = name if name != word else f"{name} "
            yield Completion(
                replacement,
                start_position=-len(word),
                display=display,
                display_meta=meta,
            )

        for name, info in self._skill_commands().items():
            if not name.startswith(word):
                continue
            yield Completion(
                name if name != word else f"{name} ",
                start_position=-len(word),
                display=f"/{name}",
                display_meta=str(info.get("description") or "skill command"),
            )

    def _skill_commands(self) -> Mapping[str, dict[str, Any]]:
        if self._skill_commands_provider is None:
            return {}
        try:
            return self._skill_commands_provider() or {}
        except Exception:
            return {}
