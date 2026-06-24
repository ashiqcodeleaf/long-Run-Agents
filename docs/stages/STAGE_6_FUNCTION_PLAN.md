# Stage 6 Function Plan

Stage 6 adds local terminal execution and background process sessions. These
tools are still pre-safety; approvals, guardrails, and checkpoints are added in
later stages.

## Source Anchors

Study these MyAgent files:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\terminal_tool.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\process_registry.py`

Important source symbols:

- `terminal_tool()`
- `ProcessRegistry`
- `spawn_local()`
- `poll()`
- `kill_process()`

## Files Added

- `longrun_agent/tools/terminal.py`
- `longrun_agent/tools/processes.py`

## Files Modified

- `longrun_agent/config.py`
- `longrun_agent/tools/registry.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Required Behavior

Foreground terminal:

- run local shell command.
- capture stdout.
- capture stderr.
- capture exit code.
- capture timeout.
- return working directory and duration.

Background process:

- start command in a wrapper process.
- persist metadata under `~/.longrun-agent/processes/processes.json`.
- write stdout/stderr under `~/.longrun-agent/processes/logs/`.
- poll process status across CLI invocations.
- kill process tree where possible.
- list tracked processes.

## CLI Commands

Foreground:

```powershell
longrun terminal run echo hello
```

Background:

```powershell
longrun process start ping 127.0.0.1 -n 30
longrun process poll <process_id>
longrun process kill <process_id>
longrun process list
```

## Registered Tools

- `terminal_run`
- `process_start`
- `process_poll`
- `process_kill`
- `process_list`

## Current Limitations

- No dangerous command approvals yet.
- No guardrails yet.
- No checkpoints before terminal commands yet.
- No model tool-calling loop yet.
- Background process tracking records wrapper process metadata.

Those are addressed in later stages.

