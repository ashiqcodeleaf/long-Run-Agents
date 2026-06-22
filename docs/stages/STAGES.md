# LongRun Agent MVP Stages

This project must be built slowly. Each stage should leave the CLI usable or at
least testable.

## Stage 0 - Project Skeleton

Goal: create the new Python project without agent logic.

Create:

```text
longrun_agent/
  __init__.py
  cli/
    __init__.py
    main.py
    commands.py
  config.py
  logging.py
  state.py
```

Implement:

- `pyproject.toml`.
- CLI entry command, for example `longrun`.
- Home directory resolver for `~/.longrun-agent/`.
- Empty config loader.
- Basic logging to `logs/agent.log` and `logs/errors.log`.
- SQLite connection creation.

Smoke test:

```bash
longrun --version
longrun status
```

## Stage 1 - Config, Storage, And Sessions

Goal: store conversations before any model calls exist.

Implement:

- `config.yaml` for behavior settings.
- `.env` for secrets only.
- `state.db` for sessions and messages.
- Session create, resume, list, history, save, clear.

Required commands:

- `/new`
- `/resume`
- `/sessions`
- `/history`
- `/clear`
- `/save`
- `/status`
- `/quit`

Smoke test:

- Start CLI.
- Create a session.
- Add a local fake user message.
- Exit.
- Resume and verify history still exists.

## Stage 2 - Auth And Model Transports

Goal: call a model with no tools.

Implement:

- OpenAI API key auth.
- ChatGPT/Codex OAuth auth.
- OpenAI Chat Completions transport.
- Codex Responses-compatible transport.
- `/auth`
- `/model`
- `/config`

Smoke test:

- `longrun auth status`
- one simple chat turn with OpenAI API key.
- one simple chat turn with Codex auth if available.

## Stage 3 - Agent Loop Without Tools

Goal: build the core `AIAgent` shape.

Implement:

- `AIAgent.chat()`.
- `AIAgent.run_conversation()`.
- max iterations.
- interrupt handling.
- final response persistence.

Smoke test:

- Ask a simple question.
- Verify user and assistant messages are stored in `state.db`.

## Stage 4 - Context Management

Goal: make long sessions stable and cheap.

Implement:

- turn context builder.
- cached system prompt.
- prompt builder.
- context file loading.
- skills manifest placeholder.
- memory snapshot placeholder.
- token estimate.
- context compression.

Required command:

- `/compress`
- `/context`

Acceptance test:

- Two normal turns must reuse byte-identical system prompt content.

## Stage 5 - Tool Registry

Goal: centralize all tool schemas and handlers.

Implement:

- `ToolRegistry`.
- tool schema listing.
- handler registration.
- gated tools.
- one execution path for all tools.

Smoke test:

- Register a fake `echo` tool.
- Simulate a tool call.
- Verify result message is persisted.

## Stage 6 - Terminal And Process Tools

Goal: local shell execution.

Implement:

- foreground command execution.
- background command sessions.
- poll and kill process.
- stdout, stderr, exit code capture.

Required commands/tools:

- terminal run.
- process poll.
- process kill.

Smoke test:

- run `echo hello`.
- start a background process.
- poll it.
- kill it.

## Stage 7 - File Tools, Safety, And Rollback

Goal: allow code edits safely.

Implement:

- read file.
- write file.
- patch file.
- search files.
- file-state tracking.
- stale-write detection.
- checkpoints.
- rollback.
- approvals.
- guardrails.

Required commands:

- `/checkpoints`
- `/rollback`
- `/debug`

Smoke test:

- read a file.
- patch it.
- verify checkpoint exists.
- rollback.
- verify original content returns.

## Stage 8 - Memory, Skills, Plugins, MCP

Goal: add extension surfaces without growing the core.

Implement:

- memory tool.
- session search.
- skill list/read.
- plugin loader.
- hook runtime.
- MCP client bridge.

Required commands:

- `/memory`
- `/session-search`
- `/skills`
- `/plugins`
- `/mcp`
- `/reload`
- `/reload-skills`
- `/reload-mcp`

Smoke test:

- install a local test skill.
- read full `SKILL.md`.
- load a test plugin.
- expose a fake plugin tool.

## Stage 9 - Subagents

Goal: parent agent can delegate work to child agents.

Implement:

- `delegate_task`.
- child `AIAgent` creation.
- depth limit.
- child tool restrictions.
- active child registry.
- background child tasks.

Required commands:

- `/agents`
- `/background`
- `/queue`

Smoke test:

- parent delegates one simple task.
- child returns a result.
- child cannot recursively delegate by default.

## Stage 10 - Long-Run Workflow

Goal: durable task orchestration.

Implement:

- Long-Run board database.
- tasks.
- dependencies.
- claims.
- attempts.
- worker heartbeat.
- worker logs.
- dispatcher.
- crashed worker detection.

Required commands:

- `/long-run init`
- `/long-run create`
- `/long-run list`
- `/long-run show`
- `/long-run assign`
- `/long-run claim`
- `/long-run complete`
- `/long-run block`
- `/long-run unblock`
- `/long-run comment`
- `/long-run dispatch`
- `/long-run tail`
- `/long-run stats`
- `/long-run runs`
- `/long-run heartbeat`

Smoke test:

- create a task.
- dispatch one worker.
- worker claims task.
- worker completes task.
- log is readable with `/long-run tail`.

