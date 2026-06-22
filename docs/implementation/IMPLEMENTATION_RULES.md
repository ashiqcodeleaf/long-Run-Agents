# Implementation Rules

These rules control how the MVP should be built.

## Work In Stages

Do not build everything at once.

For each stage:

1. State the source file being studied.
2. Explain the block of behavior.
3. Write or copy the smallest version.
4. Run the smoke test.
5. Stop and review before the next stage.

## Copying Code From MyAgent

Copy code only when:

- the source behavior is understood.
- the code is needed for the current stage.
- unrelated platform support is removed.
- gateway, desktop, TUI, browser, image, voice, and non-OpenAI provider code is not pulled in.

Generate new code when:

- the original file is too large.
- the original behavior is simple enough to rewrite.
- the MVP needs a smaller interface.

## Naming Rules

- Project: LongRun Agent.
- Package: `longrun_agent`.
- Durable workflow: Long-Run.
- Python module for durable workflow: `long_run`.
- CLI command namespace: `/long-run`.

Avoid user-facing `kanban` wording in the MVP.

## Prompt Cache Rule

Per-conversation prompt caching is mandatory.

Do not add behavior that rebuilds the system prompt every turn.

Do not put volatile plugin, memory, or skill-command output into the cached
system prompt.

## Core Tool Rule

Keep the core tool surface narrow.

Default core tools:

- terminal.
- process.
- file.
- memory.
- session search.
- skills.
- delegate task.
- Long-Run tools when gated.

Everything else should be plugin or MCP.

## Config Rule

`.env` is for secrets only.

Use `config.yaml` for:

- model.
- max iterations.
- approvals.
- checkpoint settings.
- enabled tools.
- plugin settings.
- MCP servers.
- Long-Run settings.

## Required Proof Before Moving On

A stage is not done until there is proof:

- command output.
- test result.
- database row.
- file written.
- prompt snapshot comparison.
- rollback verification.
- worker log.

The proof should be recorded in the stage notes or final answer for that stage.

