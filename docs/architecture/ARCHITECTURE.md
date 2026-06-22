# LongRun Agent MVP Architecture

## High-Level Flow

```text
CLI input
  -> slash command router or chat prompt
  -> session loader
  -> turn context builder
  -> cached system prompt restore/build
  -> token estimate and compression check
  -> OpenAI or Codex model transport
  -> tool call executor
  -> state persistence
  -> final CLI output
```

## Core Packages

```text
longrun_agent/
  cli/
  agent/
  tools/
  safety/
  plugins/
  mcp/
  long_run/
  config.py
  auth.py
  state.py
  hooks.py
  logging.py
```

## Runtime Responsibilities

`cli/`

- Owns user interaction.
- Parses slash commands.
- Starts chat turns.
- Prints model responses and tool activity.

`agent/`

- Owns `AIAgent`.
- Owns conversation loop.
- Owns model transport abstraction.
- Owns context management.
- Owns compression.

`tools/`

- Owns model-callable tools.
- Registers schemas and handlers.
- Does not decide approval policy by itself.

`safety/`

- Owns approval decisions.
- Owns command/file guardrails.
- Owns checkpoints and rollback.

`plugins/`

- Loads local plugins.
- Lets plugins register tools and hooks.
- Does not allow plugins to patch core files.

`mcp/`

- Starts configured MCP servers.
- Imports MCP tools into the tool registry.
- Isolates failed servers.

`long_run/`

- Owns durable task board storage.
- Owns dispatcher and worker lifecycle.
- Replaces the original source repo's Kanban naming.

## Required Invariant

All model tool calls must go through one executor path:

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

No tool gets a private bypass.

