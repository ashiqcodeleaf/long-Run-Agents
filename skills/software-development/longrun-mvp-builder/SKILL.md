---
name: longrun-mvp-builder
description: "Improve LongRun itself by preserving the CLI-only MVP scope and MyAgent-style agent flow."
version: 1.0.0
platforms: [windows, linux, macos]
---

# LongRun MVP Builder

Use this skill when modifying the LongRun project.

## Scope

Keep:

- CLI shell,
- OpenAI API key and Codex OAuth,
- sessions and SQLite state,
- prompt caching and compression,
- local file/terminal/process tools,
- memory, skills, plugins, hooks, MCP,
- subagents and Long-Run durable workflow.

Exclude:

- gateway platforms,
- desktop app,
- web dashboard,
- TUI,
- browser automation,
- computer-use,
- voice,
- image/video generation,
- non-OpenAI providers.

## Implementation Rules

- Read `SOURCE_MAP.md`, `ARCHITECTURE.md`, `TOOLS_AND_SAFETY.md`, and `CONTEXT_MANAGEMENT.md` before touching core files.
- Add focused tests for new behavior.
- Use the central tool registry and executor.
- Keep slash commands in `longrun_agent/cli/commands.py`.
- Keep visual rendering in `longrun_agent/cli/banner.py`.
- Keep prompt cache stable across normal turns.

