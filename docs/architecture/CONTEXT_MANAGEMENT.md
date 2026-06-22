# Context Management Plan

Context management is one of the most important parts of the MVP. Without it,
the CLI may work for short chats but fail during real coding sessions.

## Core Rule

The system prompt is built once per session and reused byte-for-byte across
normal turns.

Only context compression may rebuild the active context.

## Per-Turn Flow

```text
user input
  -> load session
  -> build_turn_context()
  -> restore cached system prompt
  -> build prompt only if no cached prompt exists
  -> estimate context tokens
  -> compress if needed
  -> inject volatile hook context into current user turn
  -> call model
```

## System Prompt Inputs

The first prompt snapshot includes:

- base LongRun Agent instructions.
- enabled tool instructions.
- project instruction files.
- skills manifest.
- frozen memory snapshot.
- environment and workspace hints.

Project instruction files:

- `AGENTS.md`
- `MYAGENT.md`
- `CLAUDE.md`
- `.cursorrules`

## What Must Not Mutate The Prompt

These actions must not rebuild the cached system prompt mid-session:

- memory writes.
- plugin hook output.
- skill slash command execution.
- normal tool result.
- normal user message.

Skill commands must become user messages.

Plugin `pre_llm_call` output must be injected into the current turn, not the
system prompt.

## Compression Rules

Compression runs before context overflow. It must preserve:

- system prompt.
- important head messages.
- recent tail messages.
- latest user request.
- latest assistant response.
- valid assistant tool calls.
- matching tool result messages.

Compression must remove or fix:

- orphaned tool result messages.
- assistant tool calls with missing tool results.
- repeated stale summaries.
- secrets in generated summaries.

## Acceptance Tests

Test 1: prompt cache stability.

1. Create a session.
2. Send one prompt.
3. Store the exact system prompt bytes.
4. Send a second prompt.
5. Verify the system prompt bytes are identical.

Test 2: memory does not mutate prompt.

1. Create a session.
2. Send one prompt.
3. Write memory.
4. Send another prompt.
5. Verify the active system prompt did not change.

Test 3: compression is the only rebuild path.

1. Create a long history.
2. Trigger compression.
3. Verify a summary message was inserted.
4. Verify tool-call/tool-result order is valid.

