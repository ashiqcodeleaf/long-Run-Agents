# LongRun Agents, Cron, And Long-Run Workflow

This document maps the CLI-only long-running-agent pieces in the MVP.

## Available Agent Types

LongRun has seven agent execution surfaces:

| Surface | Command | Use |
| --- | --- | --- |
| Interactive foreground agent | `uv run longrun` | Main MyAgent-style shell with slash commands, goal mode, tools, memory, skills, MCP, and plugins. |
| One-shot agent | `uv run longrun chat "task"` | Run a single task and exit. Useful for scripts and background wrappers. |
| Synchronous subagent | `uv run longrun agents delegate "task"` | Parent creates one child `AIAgent` and receives the child result as a tool/CLI result. |
| Background agent process | `uv run longrun background start "task"` | Starts a child LongRun process and tracks it as a local job. |
| Durable queue job | `uv run longrun queue add "task"` | Stores local agent work in SQLite so another process can claim/complete/fail it. |
| Long-Run board worker | `uv run longrun long-run ...` | Kanban-style durable task board for multi-step work with claims, heartbeats, comments, and runs. |
| Cron-triggered agent | `uv run longrun cron ...` | Stores scheduled jobs and runs them in fresh isolated agent sessions. |

## How Subagents Are Created

Source file: `longrun_agent/tools/delegate.py`

Flow:

1. The model calls `delegate_task`.
2. The tool checks the current `_SUBAGENT_DEPTH` context variable.
3. Default `max_depth` is `1`, so a child cannot recursively create another child unless explicitly allowed.
4. The tool creates a child `AIAgent(title=...)`.
5. The child runs `run_conversation(prompt)` with inherited config/auth behavior.
6. The parent receives a normal tool result containing `session_id`, `final_response`, `provider`, `model`, iteration count, and depth.

Guardrail:

- Recursive delegation is disabled by default.
- Child memory mutation is not specially allowed in this MVP.
- The parent sees child output as data; the child does not take over the parent loop.

## Cron Usage

Cron is copied in spirit from MyAgent's `cron/jobs.py`, `cron/scheduler.py`,
and `tools/cronjob_tools.py`, but reduced for CLI-only LongRun.

Storage:

```text
~/.longrun-agent/
  cron/
    jobs.json
    output/
```

Commands:

```bash
uv run longrun cron add weekly-summary "summarize this repo status" --schedule manual
uv run longrun cron list
uv run longrun cron show <job-id>
uv run longrun cron preview <job-id>
uv run longrun cron trigger <job-id>
uv run longrun cron run <job-id>
uv run longrun cron tick
uv run longrun cron pause <job-id> --reason "not needed"
uv run longrun cron resume <job-id>
uv run longrun cron remove <job-id>
```

Schedule forms:

- `manual`: stored but not due until triggered.
- `30m`, `every 2h`, `1d`: interval schedules.
- `0 9 * * *`: simple daily cron expression support.
- `2026-06-24T09:00:00+00:00`: one-shot ISO timestamp.

Model tool:

The model gets one compressed tool named `cronjob` in the `cronjob` toolset.
It supports actions:

```text
create, list, show, pause, resume, remove, trigger
```

Important limitation:

- This MVP does not install a daemon or gateway ticker.
- `cron tick` runs due jobs when you call it.
- `cron run <job-id>` triggers and runs one job immediately.
- No Telegram, WhatsApp, Slack, Discord, or gateway delivery exists here.

## Long-Run Usage

Long-Run is the public name for the Kanban-style durable board.

Storage:

```text
~/.longrun-agent/
  long-run/
    boards/
      <board>/
        kanban.db
        worker-logs/
```

Commands:

```bash
uv run longrun long-run init
uv run longrun long-run create "build todo app" --description "create files and tests"
uv run longrun long-run list
uv run longrun long-run show <task-id>
uv run longrun long-run assign <task-id> worker-1
uv run longrun long-run claim worker-1
uv run longrun long-run heartbeat worker-1 --task-id <task-id> --status running
uv run longrun long-run comment <task-id> "started implementation"
uv run longrun long-run complete <task-id> "finished and tested"
uv run longrun long-run block <task-id> "missing requirement"
uv run longrun long-run unblock <task-id>
uv run longrun long-run stats
uv run longrun long-run runs
uv run longrun long-run tail <task-id>
```

Alias:

```bash
uv run longrun kanban list
```

## Cron vs Queue vs Long-Run

| Mechanism | Durable | Runs model automatically | Best for |
| --- | --- | --- | --- |
| `background` | Partly | Yes, starts a process immediately | Fire-and-poll local work. |
| `queue` | Yes | No | Simple durable job handoff. |
| `cron` | Yes | Yes when `cron run` or `cron tick` is called | Repeated or scheduled isolated agent runs. |
| `long-run` | Yes | Worker/orchestrator driven | Multi-agent task boards with claims, status, comments, and heartbeats. |

## MyAgent Sources Studied

- `cron/jobs.py`: JSON job storage, schedules, pause/resume/trigger.
- `cron/scheduler.py`: runs jobs in isolated agent sessions.
- `tools/cronjob_tools.py`: one compressed model tool for cron management.
- `myagent_cli/kanban_db.py`: durable board, claim, worker heartbeat, dispatch behavior.
- `tools/kanban_tools.py`: model tools for board lifecycle.
- `tools/delegate_tool.py`: subagent creation and recursion control.
