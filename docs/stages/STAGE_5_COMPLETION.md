# Stage 5 Completion Notes

Stage 5 adds the central tool registry and one central executor path. It does
not yet connect model tool calls to the agent loop.

## Implemented Files

- `longrun_agent/tools/registry.py`
- `longrun_agent/agent/tool_executor.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Implemented Behavior

- `ToolRegistry.register()` stores schema, handler, toolset, and optional gate.
- `ToolRegistry.get_definitions()` lists available tool schemas.
- `ToolRegistry.dispatch()` calls the registered handler.
- `execute_tool_call()` is the central executor path.
- `ToolExecutionResult` normalizes success and failure.
- `longrun tools list` shows available tools.
- `longrun tools call <name>` calls a tool for diagnostics.
- `--arg key=value` gives a PowerShell-friendly way to pass simple arguments.
- `--json` remains available for structured arguments when shell quoting allows
  it.

## Diagnostic Tool

`diagnostic_echo` proves the tool path:

```powershell
uv run longrun tools call diagnostic_echo --arg text="hello tools"
```

Observed output:

```json
{
  "error": null,
  "name": "diagnostic_echo",
  "ok": true,
  "result": {
    "text": "hello tools"
  }
}
```

## Smoke-Test Evidence

Syntax check:

```powershell
python -m compileall longrun_agent
```

Observed result:

```text
compileall completed without syntax errors
```

Tool list:

```powershell
uv run longrun tools list
```

Observed output:

```text
diagnostic_echo | toolset=diagnostic | Return the provided text. Used to prove the tool path.
```

Tool call:

```powershell
uv run longrun tools call diagnostic_echo --arg text="hello tools"
```

Observed output showed `ok: true` and returned `text: hello tools`.

## Current Limitations

- No model-driven tool calls yet.
- No tool result messages in `state.db` yet.
- No hooks.
- No approvals.
- No guardrails.
- No checkpoints.
- No terminal or file tools.

## Next Stage

Stage 6 should add terminal and process tools:

- foreground local command execution.
- background process sessions.
- process poll.
- process kill.
- stdout/stderr/exit code capture.
- later safety hooks inserted into `execute_tool_call()`.

