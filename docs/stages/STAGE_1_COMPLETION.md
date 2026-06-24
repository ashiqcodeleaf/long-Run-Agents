# Stage 1 Completion Notes

Stage 1 is implemented as the local storage/session layer. It still does not
call a model and does not execute tools.

## Implemented Files

- `longrun_agent/config.py`
- `longrun_agent/state.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`
- `longrun_agent/logging.py`

## Implemented Behavior

- LongRun home directory resolution with `LONGRUN_AGENT_HOME` override.
- Home layout creation:
  - `logs/`
  - `skills/`
  - `plugins/`
  - `mcp/`
  - `checkpoints/`
  - `long-run/`
- Basic config defaults.
- Config rendering and simple config parsing.
- Config init/show commands.
- SQLite `state.db` initialization.
- Session creation.
- Session listing.
- Message insertion.
- Message history reading.
- Session clearing.
- Markdown transcript export.
- Runtime status output.

## Smoke-Test Evidence

Commands were run from the project root with:

```powershell
$env:LONGRUN_AGENT_HOME = Join-Path (Get-Location) '.longrun-agent-test'
```

Version check:

```powershell
python -m longrun_agent.cli.main --version
```

Observed output:

```text
LongRun Agent 0.1.0
```

Status check:

```powershell
python -m longrun_agent.cli.main status
```

Observed output included:

```text
LongRun Agent 0.1.0
Home: ...\longrun-agent-mvp\.longrun-agent-test
Config: ...\longrun-agent-mvp\.longrun-agent-test\config.yaml
State DB: ...\longrun-agent-mvp\.longrun-agent-test\state.db
Sessions: 0
Messages: 0
Default model: gpt-4.1-mini
```

Config check:

```powershell
python -m longrun_agent.cli.main config show
```

Observed output:

```yaml
model: gpt-4.1-mini
max_iterations: 90
approvals:
  mode: default
```

Session storage check:

```powershell
python -m longrun_agent.cli.main session new Stage 1 smoke
python -m longrun_agent.cli.main session add-message <session_id> user hello
python -m longrun_agent.cli.main session add-message <session_id> assistant hi
python -m longrun_agent.cli.main session history <session_id>
python -m longrun_agent.cli.main session save <session_id> .\stage1-smoke-transcript.md
```

Observed output included:

```text
Created session: session-265aebad8d26
Title: Stage 1 smoke
Added message 1 to session-265aebad8d26
Added message 2 to session-265aebad8d26
[1] user: hello
[2] assistant: hi
Saved transcript: stage1-smoke-transcript.md
```

## Current Limitations

- No interactive chat loop yet.
- No model calls yet.
- No auth yet.
- No prompt/context builder yet.
- No tools yet.
- No Long-Run worker logic yet.

## Next Stage

Stage 2 should add auth and model transports:

- OpenAI API key loading.
- ChatGPT/Codex OAuth token storage shape.
- One no-tool model call path.
- `/auth` and `/model` command foundation.

