# Stage 4 Function Plan

Stage 4 adds the first real context-management layer. This is the missing piece
that keeps LongRun Agent aligned with the MyAgent design.

## Source Anchors

Study these MyAgent files:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\turn_context.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\system_prompt.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\prompt_builder.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\context_compressor.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\model_metadata.py`

Important source symbols:

- `build_turn_context()`
- `build_system_prompt()`
- `build_context_files_prompt()`
- `ContextCompressor`
- `estimate_tokens_rough()`
- `estimate_messages_tokens_rough()`

## Files Added

- `longrun_agent/agent/context.py`
- `longrun_agent/agent/prompt.py`
- `longrun_agent/agent/compression.py`
- `longrun_agent/agent/model_metadata.py`

## Files Modified

- `longrun_agent/state.py`
- `longrun_agent/config.py`
- `longrun_agent/agent/runtime.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`

## Required Invariants

- Build the system prompt once per session.
- Persist the prompt in `prompt_snapshots`.
- Reuse the exact same prompt bytes on later turns.
- Load project instruction files without broad recursive scanning.
- Keep compression deterministic in the MVP.
- Do not count compression as successful if the compressed request is larger.

## Context Files

The prompt builder looks for these files from the workspace root upward:

- `AGENTS.md`
- `MYAGENT.md`
- `CLAUDE.md`
- `.cursorrules`

Each file is truncated to `context.context_file_max_chars`.

## Context Commands

Show context metadata:

```powershell
longrun context show <session_id>
```

Create a deterministic summary if it reduces estimated context:

```powershell
longrun context compress <session_id>
```

## Current Limitations

- Compression is static and deterministic, not LLM-generated.
- Memory snapshots are not injected yet.
- Skills manifest is not injected yet.
- Tool schemas are not in the prompt yet because tools are not implemented.
- There is no plugin `pre_llm_call` hook yet.

Those belong to later stages.

