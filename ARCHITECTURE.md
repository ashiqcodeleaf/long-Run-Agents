# LongRun Architecture

```text
longrun_agent/
  cli/                 entrypoint, argparse commands, interactive slash shell
  agent/               AIAgent runtime, context builder, prompt, loop, transports
  tools/               model-callable tools and central registry
  safety/              approvals, guardrails, checkpoints
  plugins/             local plugin loader
  mcp/                 MCP stdio tool bridge
  long_run/            durable Long-Run board database
  state.py             SQLite sessions, messages, agent jobs, prompt snapshots
```

## Main Flow

1. CLI receives text or slash command.
2. Slash command either handles locally or dispatches to argparse command handlers.
3. Normal text creates an `AIAgent`.
4. `AIAgent` builds turn context and reuses cached prompt snapshots.
5. The loop sends messages and tool schemas to the configured transport.
6. Tool calls execute through the central executor.
7. Tool results and assistant responses are persisted to SQLite.

