# Stage 2 Completion Notes

Stage 2 adds the auth/model boundary. It still does not run a full chat turn
through `AIAgent`.

## Implemented Files

- `longrun_agent/auth.py`
- `longrun_agent/agent/transports/base.py`
- `longrun_agent/agent/transports/openai.py`
- `longrun_agent/agent/transports/codex.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/config.py`
- `pyproject.toml`
- `uv.lock`

## Implemented Behavior

- OpenAI API key storage in `auth.json`.
- OpenAI API key resolution from:
  - `OPENAI_API_KEY`
  - `.env`
  - `auth.json`
- Codex OAuth token storage shape.
- Redacted auth status output.
- Provider logout.
- Model provider config.
- OpenAI no-tool Chat Completions transport boundary.
- Codex Responses transport boundary.

## Smoke-Test Evidence

Commands were run from the project root with:

```powershell
$env:LONGRUN_AGENT_HOME = Join-Path (Get-Location) '.longrun-agent-test'
```

Auth status before credentials:

```powershell
python -m longrun_agent.cli.main auth status
```

Observed output:

```text
openai-api: missing
openai-codex: missing
```

Model status:

```powershell
python -m longrun_agent.cli.main model show
```

Observed output:

```text
Provider: openai-api
Model: gpt-4.1-mini
```

Config output:

```powershell
python -m longrun_agent.cli.main config show
```

Observed output included:

```yaml
provider: openai-api
model: gpt-4.1-mini
max_iterations: 90
approvals:
  mode: default
openai:
  base_url: 'https://api.openai.com/v1'
codex:
  base_url: 'https://chatgpt.com/backend-api/codex'
```

Fake credential storage check:

```powershell
python -m longrun_agent.cli.main auth set-openai-key sk-test-1234567890
python -m longrun_agent.cli.main auth set-codex-tokens --access-token codex-test-token --refresh-token refresh-test --account-id acct-test --expires-at 2099-01-01T00:00:00Z
python -m longrun_agent.cli.main auth status
```

Observed output included:

```text
openai-api: configured source=auth.json detail=sk-t...7890
openai-codex: configured source=auth.json detail=expires_at=2099-01-01T00:00:00Z
```

Model set check:

```powershell
python -m longrun_agent.cli.main model set gpt-4.1-mini --provider openai-api
python -m longrun_agent.cli.main model show
```

Observed output:

```text
Provider: openai-api
Model: gpt-4.1-mini
```

Dependency lock:

```powershell
uv lock
```

Observed result:

```text
Resolved 18 packages
```

Syntax check:

```powershell
python -m compileall longrun_agent
```

Observed result:

```text
compileall completed without syntax errors
```

## Current Limitations

- Codex stores token shape but does not yet perform browser/device login.
- Codex transport raises a clear "not implemented yet" error instead of making
  the network call.
- `AIAgent.chat()` does not exist yet.
- No session persistence around model calls yet.
- No tools yet.

## Next Stage

Stage 3 should add the first no-tool `AIAgent`:

- `longrun_agent/agent/runtime.py`
- `longrun_agent/agent/loop.py`
- `longrun chat "<message>"`
- persist user and assistant messages in `state.db`.
- use OpenAI transport when `provider=openai-api`.
- return a clear setup error when auth is missing.

