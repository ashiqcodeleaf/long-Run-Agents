# Stage 7 Function Plan

Stage 7 adds file tools and the first safety layer around the central executor.

## Source Anchors

Study these MyAgent files:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\file_tools.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\file_state.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\approval.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\tool_guardrails.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\tool_executor.py`

Important source symbols:

- `read_file_tool()`
- `write_file_tool()`
- `patch_tool()`
- `search_tool()`
- `FileStateRegistry`
- `record_read()`
- `check_stale()`
- `detect_dangerous_command()`
- `ToolGuardrailDecision`

## Files Added

- `longrun_agent/tools/files.py`
- `longrun_agent/tools/file_state.py`
- `longrun_agent/safety/checkpoints.py`
- `longrun_agent/safety/approval.py`
- `longrun_agent/safety/guardrails.py`

## Files Modified

- `longrun_agent/agent/tool_executor.py`
- `longrun_agent/tools/registry.py`
- `longrun_agent/config.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Required Behavior

File tools:

- `file_read`
- `file_write`
- `file_patch`
- `file_search`

Safety:

- read records a file fingerprint.
- write/patch check for stale file state before mutation.
- write/patch create a checkpoint before mutation.
- rollback restores previous content or removes a file created after checkpoint.
- sensitive credential files are blocked by guardrails.
- dangerous terminal/process commands require explicit approval.

## Executor Order

The Stage 7 executor order is:

```text
validate args
  -> guardrails
  -> approval
  -> stale-write check
  -> checkpoint if needed
  -> registry dispatch
  -> attach checkpoint id to result
```

Later stages will add plugin hooks around this same path.

## CLI Commands

File:

```powershell
longrun file read <path>
longrun file write <path> --content "text"
longrun file patch <path> --old "before" --new "after"
longrun file search <pattern> --path <dir>
```

Safety:

```powershell
longrun checkpoints list
longrun rollback <checkpoint_id>
longrun terminal run --approve <dangerous command>
longrun process start --approve <dangerous command>
```

## Current Limitations

- Approval is non-interactive. The user must pass `--approve` from the CLI.
- File patch supports exact one-fragment replacement, not unified diff patches.
- Stale tracking is path-based and local.
- Terminal checkpoints are not implemented yet.
- Plugin hooks are not implemented yet.

