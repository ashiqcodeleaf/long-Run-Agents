# Stage 6 Completion Notes

Stage 6 adds foreground terminal execution and persistent background process
tracking through the central tool registry/executor path.

## Implemented Files

- `longrun_agent/tools/terminal.py`
- `longrun_agent/tools/processes.py`
- `longrun_agent/tools/registry.py`
- `longrun_agent/config.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Implemented Behavior

- `terminal_run` tool.
- `process_start` tool.
- `process_poll` tool.
- `process_kill` tool.
- `process_list` tool.
- `longrun terminal run ...`.
- `longrun process start ...`.
- `longrun process poll <id>`.
- `longrun process kill <id>`.
- `longrun process list`.
- process metadata stored in `~/.longrun-agent/processes/processes.json`.
- process stdout/stderr logs stored in `~/.longrun-agent/processes/logs/`.

## Smoke-Test Evidence

Commands were run with:

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

Tool registry:

```powershell
uv run longrun tools list
```

Observed output included:

```text
process_kill | toolset=process | Kill a background process.
process_list | toolset=process | List tracked background processes.
process_poll | toolset=process | Poll a background process.
process_start | toolset=process | Start a background shell command.
terminal_run | toolset=terminal | Run a local foreground shell command and capture output.
```

Foreground terminal:

```powershell
uv run longrun terminal run echo hello-terminal
```

Observed output included:

```json
{
  "name": "terminal_run",
  "ok": true,
  "result": {
    "command": "echo hello-terminal",
    "exit_code": 0,
    "stdout": "hello-terminal\n",
    "timed_out": false
  }
}
```

Background process start/poll/list:

```powershell
uv run longrun process start ping 127.0.0.1 -n 8
uv run longrun process poll <process_id>
uv run longrun process list
```

Observed behavior:

- process id was created.
- status was `running` while ping was active.
- stdout showed ping output.
- final list showed the process as `exited` with exit code `0`.

Kill behavior:

```powershell
uv run longrun process start ping 127.0.0.1 -n 30
uv run longrun process kill <process_id>
uv run longrun process poll <process_id>
```

Observed output included:

```text
status: killed
```

## Current Limitations

- Terminal commands are not approval-gated yet.
- Terminal commands do not create checkpoints yet.
- No dangerous command detector yet.
- No tool hooks yet.
- No model-driven tool loop yet.

## Next Stage

Stage 7 should add file tools, file-state tracking, checkpoints, approvals, and
guardrails. That is the safety layer that must wrap terminal/file mutation.

