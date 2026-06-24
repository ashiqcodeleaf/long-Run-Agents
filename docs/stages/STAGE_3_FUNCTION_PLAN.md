# Stage 3 Function Plan

Stage 3 adds the first no-tool `AIAgent`. It is intentionally smaller than the
source MyAgent runtime, but it keeps the same public shape:

- `AIAgent.chat(message)`
- `AIAgent.run_conversation(user_message)`

## Source Anchors

Source files to study:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\run_agent.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\conversation_loop.py`

Important source symbols:

- `class AIAgent`
- `run_conversation()`
- `chat()`

## Files Added

- `longrun_agent/agent/runtime.py`
- `longrun_agent/agent/loop.py`

## Files Modified

- `longrun_agent/state.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Runtime Behavior

The Stage 3 flow is:

```text
longrun chat "message"
  -> AIAgent(...)
  -> validate auth/provider
  -> create or load session
  -> load previous messages
  -> append current user message to model request
  -> persist user message
  -> call no-tool transport
  -> persist assistant response
  -> print assistant response and session id
```

## Why Auth Is Checked Before Persistence

For OpenAI and Codex, the agent builds the transport before creating/writing the
session. That prevents a missing API key from creating half-finished chat rows.

## Current Limitations

- No streaming.
- No tools.
- No prompt cache yet.
- No context compression yet.
- No system prompt builder yet.
- Codex network call is still scaffold-only.

Those belong to later stages.

