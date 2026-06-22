"""Stage 0 command definitions for the LongRun CLI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandDef:
    name: str
    description: str


COMMANDS: tuple[CommandDef, ...] = (
    CommandDef("status", "Show LongRun Agent home, database, and version."),
)


def command_names() -> list[str]:
    return [command.name for command in COMMANDS]
