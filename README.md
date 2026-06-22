# LongRun Agent MVP

LongRun Agent is a CLI-only personal agent MVP based on the MyAgent core design.
It keeps the useful agent kernel and removes the platform surfaces that are not
needed for the first build.

This folder is a planning and implementation guide. It does not contain the
finished product yet. The build should happen in stages so each block of code is
understood before the next block is written.

## What We Are Building

- CLI chat interface.
- OpenAI API key auth.
- ChatGPT/Codex OAuth auth.
- Persistent sessions.
- Prompt caching.
- Context management and compression.
- Local shell tools.
- File read/write/patch/search tools.
- Memory and session search.
- Skills.
- Plugins.
- Hooks.
- MCP tool connections.
- Subagents.
- Long-Run durable task workflow.
- Approvals, guardrails, checkpoints, and rollback.

## What We Are Not Building

- Web dashboard.
- Electron desktop app.
- TUI.
- Telegram, WhatsApp, Slack, Discord, or any messaging gateway.
- Browser automation.
- Computer-use automation.
- Voice.
- Image generation.
- Non-OpenAI model providers.
- Cron scheduler in the first MVP.

## Naming

Project name: **LongRun Agent**

Directory name: `longrun-agent-mvp`

The source repo calls the durable board workflow `kanban`. In this MVP, that
feature is renamed to **Long-Run**:

- CLI namespace: `/long-run`
- Python package area: `long_run/`
- Database folder: `~/.longrun-agent/long-run/`
- User-facing wording: Long-Run tasks, Long-Run workers, Long-Run dispatcher

## Build Rule

Do not copy huge files blindly. For every stage:

1. Read the source file from the MyAgent directory.
2. Explain the block being copied or rewritten.
3. Write the smallest usable version.
4. Run a smoke test.
5. Only then move to the next stage.

The user decides when to move from one stage to the next.

