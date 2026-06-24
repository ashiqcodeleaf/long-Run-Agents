# LongRun Durable Workflow

Long-Run is the renamed Kanban-style workflow for durable agent work.

## Current MVP

- Board/task SQLite storage.
- CLI commands under `longrun long-run`.
- Alias: `longrun kanban`.
- Model tools under the `long-run` toolset.
- Task create/list/show/assign/claim/complete/block/unblock/comment/dispatch/tail/stats/runs/heartbeat.

## Intended Flow

1. Orchestrator creates tasks.
2. Worker claims a ready task atomically.
3. Worker launches a LongRun agent with task context.
4. Worker heartbeats while active.
5. Worker completes or blocks with a reason.
6. Orchestrator reviews output and dispatches next tasks.

## Commands

```bash
uv run longrun long-run init
uv run longrun long-run create "build todo app" --description "write code and tests"
uv run longrun long-run list
uv run longrun long-run claim worker-1
uv run longrun long-run heartbeat worker-1 --task-id <task-id> --status running
uv run longrun long-run complete <task-id> "done"
uv run longrun long-run block <task-id> "blocked reason"
uv run longrun long-run stats
```

## Tool Flow

The model can call:

- `long_run_create`
- `long_run_list`
- `long_run_claim`
- `long_run_complete`
- `long_run_heartbeat`

These are intentionally smaller than the full MyAgent Kanban toolset. The
CLI exposes the extra manual operations like assign, block, unblock, comment,
tail, stats, and runs.

## Difference From Cron

- Cron runs isolated scheduled jobs.
- Long-Run coordinates durable multi-step work with workers.
- Queue stores simple durable jobs without board semantics.
