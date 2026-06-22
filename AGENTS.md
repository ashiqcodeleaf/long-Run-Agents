# AGENTS.md - LongRun Agent MVP

Instructions for AI coding assistants working inside this folder.

## Project Identity

This project is **LongRun Agent**, a CLI-only MVP inspired by the MyAgent codebase.

The goal is to rebuild the useful agent core slowly and visibly:

- CLI chat.
- OpenAI API key auth.
- ChatGPT/Codex OAuth auth.
- persistent sessions.
- prompt caching.
- context management and compression.
- local shell tools.
- file tools.
- memory.
- skills.
- plugins.
- hooks.
- MCP.
- subagents.
- Long-Run durable task workflow.
- approvals, guardrails, checkpoints, and rollback.

## Hard Scope Boundary

Do not build these for the MVP:

- web dashboard.
- desktop app.
- TUI.
- Telegram, WhatsApp, Slack, Discord, or any messaging gateway.
- browser automation.
- computer-use automation.
- voice.
- image generation.
- non-OpenAI providers.
- cron scheduler unless the user explicitly brings it back.

## Naming Rules

Use these names consistently:

- Project: `LongRun Agent`
- Folder: `longrun-agent-mvp`
- Python package: `longrun_agent`
- Durable workflow: `Long-Run`
- Durable workflow module: `long_run`
- Durable workflow CLI namespace: `/long-run`

The source MyAgent repo calls the durable workflow `kanban`. In this MVP, do not
use `kanban` as user-facing terminology. Use `kanban` only when pointing to the
source file names in MyAgent.

## Required Reading Order

Before writing source code, read these docs in this folder:

1. `README.md`
2. `IMPLEMENTATION_RULES.md`
3. `STAGES.md`
4. `ARCHITECTURE.md`
5. `SOURCE_MAP.md`
6. `CONTEXT_MANAGEMENT.md`
7. `TOOLS_AND_SAFETY.md`
8. `LONG_RUN.md`

When working on a specific stage, read only the source files needed for that
stage from the MyAgent directory.

## Build Process

Work in stages. Do not jump ahead.

For every stage:

1. State the stage being worked on.
2. State the MyAgent source files being studied.
3. Explain the block of behavior in plain language.
4. Write or copy the smallest usable code.
5. Remove unrelated platform support while copying.
6. Run the stage smoke test.
7. Report the proof before moving on.

The user wants to understand every block of code. Do not silently copy large
files.

## Copying From MyAgent

The MyAgent source directory is the reference implementation. Use it for design
and code, but copy selectively.

Allowed:

- copying small, understood functions.
- rewriting large files into smaller MVP modules.
- adapting schemas and storage layout.
- preserving proven safety/context behavior.

Not allowed:

- copying huge files blindly.
- bringing gateway, desktop, TUI, browser, voice, image, or non-OpenAI provider
  code into the MVP.
- changing the original MyAgent source tree unless the user explicitly asks.

## Prompt Cache Rule

Prompt caching is mandatory.

The system prompt is built once per session and reused byte-for-byte across
normal turns.

Do not rebuild the system prompt because of:

- memory writes.
- plugin hook output.
- skill command execution.
- normal tool results.
- normal user messages.

Only context compression may rebuild the active context.

## Tool Execution Rule

Every model tool call must go through one executor path:

```text
parse tool call
  -> pre_tool_call hook
  -> scope validation
  -> guardrails
  -> approval check
  -> checkpoint if mutating
  -> registry dispatch
  -> file-state tracking
  -> post_tool_call hook
  -> append tool result
  -> persist state
```

No tool gets a bypass path.

## Storage Rule

Use this MVP home layout:

```text
~/.longrun-agent/
  config.yaml
  .env
  auth.json
  state.db
  memory.json
  logs/
  skills/
  plugins/
  mcp/
  checkpoints/
  long-run/
```

`.env` is for secrets only. Put behavior settings in `config.yaml`.

## Stage Discipline

Stage 0 is only the project skeleton. Do not implement the full agent loop in
Stage 0.

Stage 1 is config, storage, and sessions. Do not call a model yet.

Stage 2 is auth and transports. Do not add tools yet.

Stage 3 is the basic agent loop without tools.

Stage 4 is context management.

Stage 5 and later add tools, safety, extensions, subagents, and Long-Run.

## Proof Required

A stage is not done until there is visible proof, such as:

- command output.
- a passing smoke test.
- a database row.
- a prompt snapshot comparison.
- a checkpoint file.
- a rollback result.
- a Long-Run worker log.

Always report the proof clearly.

