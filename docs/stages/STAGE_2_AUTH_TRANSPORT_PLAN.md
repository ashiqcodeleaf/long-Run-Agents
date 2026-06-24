# Stage 2 Auth And Transport Notes

Stage 2 starts the model boundary without tools.

## Implemented In This Slice

- `longrun_agent/auth.py`
- `longrun_agent/agent/transports/base.py`
- `longrun_agent/agent/transports/openai.py`
- `longrun_agent/agent/transports/codex.py`
- `longrun auth ...`
- `longrun model ...`

## Auth Store

Credentials are stored in:

```text
~/.longrun-agent/auth.json
```

Supported provider ids:

- `openai-api`
- `openai-codex`

OpenAI API key resolution order:

1. `OPENAI_API_KEY` environment variable.
2. `~/.longrun-agent/.env`.
3. `~/.longrun-agent/auth.json`.

## Commands

Show auth status:

```powershell
python -m longrun_agent.cli.main auth status
```

Store OpenAI API key:

```powershell
python -m longrun_agent.cli.main auth set-openai-key
```

Store Codex token shape from an external login flow:

```powershell
python -m longrun_agent.cli.main auth set-codex-tokens --access-token <token>
```

Show active model:

```powershell
python -m longrun_agent.cli.main model show
```

Set active model:

```powershell
python -m longrun_agent.cli.main model set gpt-4.1-mini --provider openai-api
```

## Transport Boundary

OpenAI:

- `OpenAIChatTransport.complete(messages)` performs a no-tool Chat Completions
  request.

Codex:

- `CodexResponsesTransport` exists as the boundary.
- Token storage exists.
- The actual Codex Responses network call is intentionally not implemented in
  this slice because it depends on the full OAuth refresh/login exchange.

## Next Required Work

The next slice should add:

- real Codex OAuth login/refresh.
- a no-tool `AIAgent.chat()` using the transport boundary.
- session persistence around the model call.

