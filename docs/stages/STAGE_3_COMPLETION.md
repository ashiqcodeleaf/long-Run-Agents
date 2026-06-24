# Stage 3 Completion Notes

Stage 3 adds the first no-tool `AIAgent` and the `longrun chat` command. It
does not implement tools, prompt caching, or context compression yet.

## Implemented Files

- `longrun_agent/agent/runtime.py`
- `longrun_agent/agent/loop.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`
- `longrun_agent/state.py`

## Implemented Behavior

- `AIAgent.chat(message)` returns assistant text.
- `AIAgent.run_conversation(user_message)` returns an `AgentResult`.
- `longrun chat "message"` runs one no-tool chat turn.
- Existing session can be selected with `--session-id`.
- New session title can be set with `--title`.
- Provider/model can be overridden for one run with `--provider` and `--model`.
- OpenAI auth is checked before session/message persistence.
- Missing auth returns a clear CLI error.
- Successful fake-transport turn persists:
  - one user message.
  - one assistant message.

## Runtime Flow

```text
longrun chat "hello"
  -> AIAgent(...)
  -> build provider transport
  -> ensure session
  -> load previous messages
  -> append current user message to model request
  -> persist user message
  -> run_no_tool_turn(...)
  -> persist assistant response
  -> print response and session id
```

## Smoke-Test Evidence

Commands were run from the project root with:

```powershell
$env:LONGRUN_AGENT_HOME = Join-Path (Get-Location) '.longrun-agent-test'
```

Syntax check:

```powershell
python -m compileall longrun_agent
```

Observed result:

```text
compileall completed without syntax errors
```

Missing-auth CLI check:

```powershell
uv run longrun chat hello
```

Observed output:

```text
Chat failed: OpenAI API key is not configured. Use `longrun auth set-openai-key` or set OPENAI_API_KEY in the environment or .env file.
```

State check after missing auth:

```powershell
uv run longrun status
```

Observed output included:

```text
Sessions: 0
Messages: 0
```

Fake transport persistence check:

```powershell
@'
from longrun_agent.agent.runtime import AIAgent
from longrun_agent.agent.transports.base import ModelResponse
from longrun_agent.state import list_messages, get_state_summary

class FakeTransport:
    def complete(self, messages):
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "hello fake"
        return ModelResponse(content="fake assistant reply")

agent = AIAgent(title="Stage 3 fake", transport=FakeTransport())
result = agent.run_conversation("hello fake")
print(result.session_id)
print(result.final_response)
messages = list_messages(result.session_id)
print(len(messages))
print(messages[0]["role"], messages[0]["content"])
print(messages[1]["role"], messages[1]["content"])
print(get_state_summary()["sessions"], get_state_summary()["messages"])
'@ | python -
```

Observed output:

```text
session-aa742b0935a1
fake assistant reply
2
user hello fake
assistant fake assistant reply
1 2
```

## Current Limitations

- No tool calling.
- No streaming.
- No prompt cache.
- No context file loading.
- No compression.
- No memory injection.
- Codex transport still has storage boundary only.

## Next Stage

Stage 4 should add context management:

- cached system prompt table usage.
- prompt builder.
- `AGENTS.md` loading.
- stable prompt snapshot per session.
- token estimate.
- manual `/context` or `longrun context` inspection command.
- compression scaffold.

