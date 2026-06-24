# LongRun Build Stages

## Stage 1: CLI Shell

Interactive `uv run longrun`, slash commands, help, setup, status, auth, model display, and colored activity.

## Stage 2: Agent Core

OpenAI/Codex transport, prompt caching, context building, model loop, tool calls, tool result persistence, and usage display.

## Stage 3: Workspace Tools

File, terminal, process, memory, session search, skills, plugins, hooks, MCP, checkpoints, and rollback.

## Stage 4: Goal Loop

`/goal` stores a standing objective and immediately runs an agent iteration. Later turns include the active goal until paused or cleared.

## Stage 5: Long-Run

Durable board/task workflow, renamed from Kanban. This is for long-running coordinated work after the CLI/agent core is stable.

## Stage 6: Multi-Agent

Parent/child agent delegation, background jobs, durable queue, and Long-Run workers.

