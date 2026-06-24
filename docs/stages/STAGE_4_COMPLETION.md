# Stage 4 Completion Notes

Stage 4 adds context management, prompt caching, project instruction loading,
rough token estimates, context inspection, and a deterministic compression
scaffold.

## Implemented Files

- `longrun_agent/agent/context.py`
- `longrun_agent/agent/prompt.py`
- `longrun_agent/agent/compression.py`
- `longrun_agent/agent/model_metadata.py`
- `longrun_agent/state.py`
- `longrun_agent/config.py`
- `longrun_agent/agent/runtime.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Implemented Behavior

- `build_turn_context()` restores or creates the prompt snapshot.
- `build_system_prompt()` creates the first cached prompt.
- Project instruction files are loaded from the workspace root upward.
- `prompt_snapshots` stores one cached system prompt per session.
- `context_summaries` stores deterministic compression summaries.
- `estimate_tokens_rough()` and `estimate_messages_tokens_rough()` provide
  tokenizer-free rough estimates.
- `compress_messages_if_needed()` compresses only when it reduces estimated
  request size.
- `longrun context show <session_id>` prints context metadata.
- `longrun context compress <session_id>` creates a deterministic summary when
  useful.
- `AIAgent.run_conversation()` now sends the cached system prompt as the first
  model message.

## Prompt Cache Proof

Commands were run from the project root with:

```powershell
$env:LONGRUN_AGENT_HOME = Join-Path (Get-Location) '.longrun-agent-test'
```

Fake transport check:

```powershell
from longrun_agent.agent.runtime import AIAgent
from longrun_agent.agent.transports.base import ModelResponse
from longrun_agent.state import get_prompt_snapshot, list_messages

class CapturingTransport:
    def __init__(self):
        self.prompts = []
        self.calls = 0
    def complete(self, messages):
        self.calls += 1
        self.prompts.append(messages[0]["content"])
        return ModelResponse(content=f"reply {self.calls}")

transport = CapturingTransport()
agent = AIAgent(title="Stage 4 prompt cache", transport=transport)
first = agent.run_conversation("first turn")
second = agent.run_conversation("second turn")
snapshot = get_prompt_snapshot(first.session_id)
print(first.session_id)
print(first.prompt_created, second.prompt_created)
print(transport.prompts[0] == transport.prompts[1])
print(snapshot is not None)
print(len(snapshot["system_prompt"]))
print(len(list_messages(first.session_id)))
```

Observed output:

```text
session-82be4b78d34c
True False
True
True
17178
4
```

Meaning:

- first turn created the prompt.
- second turn reused the prompt.
- the two prompt byte strings matched exactly.
- the prompt snapshot existed in SQLite.
- four chat messages were persisted after two turns.

## Context CLI Proof

Context show:

```powershell
uv run longrun context show session-82be4b78d34c
```

Observed output before compression included:

```text
has_prompt_snapshot: True
system_prompt_chars: 17178
message_count: 24
estimated_tokens: 10518
context_window: 1047576
latest_summary_id: None
```

Manual compression:

```powershell
uv run longrun context compress session-82be4b78d34c
```

Observed output:

```text
compressed: True
estimated_tokens_before: 10518
estimated_tokens_after: 8538
summary:
The conversation contained older messages that were compressed before the model call.
```

Context show after compression:

```text
latest_summary_id: 1
```

## Syntax Check

```powershell
python -m compileall longrun_agent
```

Observed result:

```text
compileall completed without syntax errors
```

## Current Limitations

- No memory snapshot injection.
- No skills manifest injection.
- No tool instructions yet.
- No LLM-generated summaries.
- No automatic context overflow retry path yet.
- No plugin hook injection yet.

## Next Stage

Stage 5 should add the tool registry:

- `ToolRegistry`.
- tool schema listing.
- handler registration.
- gated tools.
- one central execution path for all future tools.

