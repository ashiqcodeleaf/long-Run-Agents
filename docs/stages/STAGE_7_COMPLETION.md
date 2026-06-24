# Stage 7 Completion Notes

Stage 7 adds file tools, stale-write tracking, checkpoints, rollback,
approvals, and guardrails.

## Implemented Files

- `longrun_agent/tools/files.py`
- `longrun_agent/tools/file_state.py`
- `longrun_agent/safety/checkpoints.py`
- `longrun_agent/safety/approval.py`
- `longrun_agent/safety/guardrails.py`
- `longrun_agent/agent/tool_executor.py`
- `longrun_agent/tools/registry.py`
- `longrun_agent/config.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Implemented Behavior

- `file_read` reads UTF-8 text and records a fingerprint.
- `file_write` writes text and records the new fingerprint.
- `file_patch` replaces one exact text fragment and records the new fingerprint.
- `file_search` searches names or content.
- `file_write` and `file_patch` create checkpoints before mutation.
- stale reads block later writes/patches when the file changed externally.
- `checkpoints list` prints checkpoint metadata.
- `rollback <id>` restores checkpoint content.
- guardrails block direct access to LongRun `.env` and `auth.json`.
- dangerous terminal/process commands require `--approve`.

## Smoke-Test Evidence

Commands were run with:

```powershell
$env:LONGRUN_AGENT_HOME = Join-Path (Get-Location) '.longrun-agent-test'
```

Tool registry:

```powershell
uv run longrun tools list
```

Observed output included:

```text
file_patch | toolset=file | Replace exactly one text fragment in a file.
file_read | toolset=file | Read a text file and record its freshness fingerprint.
file_search | toolset=file | Search file names or text content.
file_write | toolset=file | Write a text file after stale-write checks and checkpointing.
```

File write:

```powershell
uv run longrun file write .longrun-stage7-test\sample.txt --content "alpha beta"
```

Observed output included:

```text
"ok": true
"checkpoint_id": "chk-afef757f0557"
"bytes": 10
```

File read:

```powershell
uv run longrun file read .longrun-stage7-test\sample.txt
```

Observed output included:

```text
"content": "alpha beta"
```

Patch:

```powershell
uv run longrun file patch .longrun-stage7-test\sample.txt --old alpha --new gamma
```

Observed output included:

```text
"ok": true
"checkpoint_id": "chk-7b38e720b214"
"replacements": 1
```

Search:

```powershell
uv run longrun file search gamma --path .longrun-stage7-test
```

Observed output included:

```text
"text": "gamma beta"
```

Rollback:

```powershell
uv run longrun rollback chk-7b38e720b214
uv run longrun file read .longrun-stage7-test\sample.txt
```

Observed output:

```text
"action": "restored"
"content": "alpha beta"
```

Stale-write block:

```powershell
uv run longrun file read .longrun-stage7-test\sample.txt
Set-Content .longrun-stage7-test\sample.txt "external edit"
uv run longrun file patch .longrun-stage7-test\sample.txt --old external --new internal
```

Observed output:

```text
"ok": false
"error": "File changed since last read: ..."
```

Dangerous command approval block:

```powershell
uv run longrun terminal run Remove-Item -Recurse -Force .longrun-stage7-test
```

Observed output:

```text
"ok": false
"error": "Approval required for terminal_run: dangerous command marker `remove-item`..."
```

Sensitive file guardrail:

```powershell
uv run longrun file read .longrun-agent-test\.env
```

Observed output:

```text
"ok": false
"error": "Refusing to access sensitive LongRun file: ...\\.env"
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

- Approval is CLI-flag based, not an interactive prompt yet.
- File patch is exact-fragment replacement, not a full unified diff engine.
- Terminal commands do not create checkpoints yet.
- Model-driven tool calls are not wired into the agent loop yet.
- Plugin hooks are not inserted into the executor yet.

## Next Stage

Stage 8 should add memory, session search, skills, plugins, hooks, and MCP
scaffolding. Hooks should wrap the executor path created in Stages 5-7.

