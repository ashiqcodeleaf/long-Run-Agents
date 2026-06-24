# Stage 5 Function Plan

Stage 5 adds the central tool registry and executor. This stage does not add
terminal or file tools yet.

## Source Anchors

Study these MyAgent files:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\registry.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\model_tools.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\tool_executor.py`

Important source symbols:

- `ToolRegistry`
- `register()`
- `get_definitions()`
- `handle_function_call()`
- tool executor path

## Files Added

- `longrun_agent/tools/registry.py`
- `longrun_agent/agent/tool_executor.py`

## Files Modified

- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Required Behavior

- Register tools with schema, handler, toolset, and optional availability check.
- List available tool definitions.
- Dispatch by name through one central executor.
- Normalize success and failure into one result shape.
- Provide a diagnostic tool so the path can be tested before real tools exist.

## Diagnostic Tool

`diagnostic_echo` exists only to prove the registry and executor path:

```powershell
longrun tools call diagnostic_echo --arg text=hello
```

It returns:

```json
{
  "text": "hello"
}
```

## Current Limitations

- No model tool-calling loop yet.
- No hooks.
- No approvals.
- No guardrails.
- No checkpoints.
- No terminal/file tools.

Those stages will insert behavior into `execute_tool_call()`.
