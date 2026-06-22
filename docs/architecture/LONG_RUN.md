# Long-Run Workflow

Long-Run is the durable multi-agent workflow. It is renamed from the source
repo's Kanban system.

Use Long-Run when work should survive beyond one chat turn.

## User-Facing Commands

```text
/long-run init
/long-run create
/long-run list
/long-run show
/long-run assign
/long-run claim
/long-run complete
/long-run block
/long-run unblock
/long-run comment
/long-run dispatch
/long-run tail
/long-run stats
/long-run runs
/long-run heartbeat
```

## Storage

```text
~/.longrun-agent/
  long-run/
    boards/
      <board>/
        long_run.db
        worker-logs/
```

## Core Tables

Minimum tables:

- boards.
- tasks.
- task_dependencies.
- comments.
- attempts.
- worker_runs.
- worker_heartbeats.
- attachments.

## Task Fields

Each task needs:

- id.
- title.
- description.
- status.
- priority.
- assignee.
- parent id.
- dependency state.
- claim owner.
- claim timestamp.
- worker pid.
- attempt count.
- created timestamp.
- updated timestamp.
- completed timestamp.
- blocked reason.

## Dispatcher Flow

```text
load board
  -> release stale claims
  -> detect crashed workers
  -> find ready tasks
  -> atomically claim task
  -> spawn worker process
  -> record worker run
  -> stream logs to worker-logs
```

## Worker Flow

```text
start worker
  -> load task context
  -> start CLI agent run
  -> heartbeat while running
  -> complete or block task
  -> write final log
```

## Tool Gating

Long-Run tools should only be visible when the agent is in one of these modes:

- Long-Run orchestrator.
- Long-Run worker.

Normal chat sessions should not carry Long-Run tools unless explicitly enabled.

## Smoke Test

1. `/long-run init`
2. `/long-run create "write a hello file"`
3. `/long-run dispatch --once`
4. worker claims task.
5. worker writes heartbeat.
6. worker completes task.
7. `/long-run tail <task>`
8. logs show the worker action.

