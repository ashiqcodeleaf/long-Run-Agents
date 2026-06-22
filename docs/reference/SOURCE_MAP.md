# Source Map From MyAgent To LongRun Agent

Use this map while implementing. Read the source file first, then copy only the
needed behavior into the MVP.

## Agent Runtime

Source:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\run_agent.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\conversation_loop.py`

MVP target:

- `longrun_agent/agent/runtime.py`
- `longrun_agent/agent/loop.py`

Functions/classes to understand:

- `AIAgent`
- `chat()`
- `run_conversation()`
- model call loop
- tool-call iteration
- max-iteration handling

## Context Management

Source:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\turn_context.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\system_prompt.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\prompt_builder.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\context_compressor.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\conversation_compression.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\model_metadata.py`

MVP target:

- `longrun_agent/agent/context.py`
- `longrun_agent/agent/prompt.py`
- `longrun_agent/agent/compression.py`
- `longrun_agent/agent/model_metadata.py`

Behavior to keep:

- cached system prompt.
- prompt snapshot persisted in session storage.
- context file loading.
- skills manifest.
- frozen memory snapshot.
- token estimation.
- compression before overflow.
- valid tool-call/tool-result cleanup.

## Auth And Transports

Source:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\myagent_cli\auth.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\transports\chat_completions.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\transports\codex.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\codex_responses_adapter.py`

MVP target:

- `longrun_agent/auth.py`
- `longrun_agent/agent/transports/openai.py`
- `longrun_agent/agent/transports/codex.py`

Behavior to keep:

- OpenAI API key provider.
- Codex OAuth provider.
- token refresh.
- model selection.

Behavior to remove:

- non-OpenAI providers.
- gateway/platform auth surfaces.

## Tools

Source:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\model_tools.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\registry.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\terminal_tool.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\process_registry.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\file_tools.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\file_state.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\memory_tool.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\session_search_tool.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\skills_tool.py`

MVP target:

- `longrun_agent/tools/registry.py`
- `longrun_agent/tools/terminal.py`
- `longrun_agent/tools/processes.py`
- `longrun_agent/tools/files.py`
- `longrun_agent/tools/file_state.py`
- `longrun_agent/tools/memory.py`
- `longrun_agent/tools/session_search.py`
- `longrun_agent/tools/skills.py`

Behavior to keep:

- central registry.
- foreground terminal.
- background process sessions.
- read/write/patch/search.
- stale-write protection.
- memory tool.
- session search.
- full skill read.

## Safety

Source:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\tool_executor.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\approval.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\agent\tool_guardrails.py`

MVP target:

- `longrun_agent/safety/approval.py`
- `longrun_agent/safety/guardrails.py`
- `longrun_agent/safety/checkpoints.py`

Behavior to keep:

- dangerous command detection.
- approval state.
- mutating-tool checkpoints.
- rollback.
- guardrail decision object.

## Subagents

Source:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\delegate_tool.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\async_delegation.py`

MVP target:

- `longrun_agent/tools/delegate.py`

Behavior to keep:

- child `AIAgent` creation.
- depth limit.
- blocked child tools.
- child timeout.
- background delegation registry.

## Long-Run

Source:

- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\myagent_cli\kanban_db.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\myagent_cli\kanban.py`
- `C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\tools\kanban_tools.py`

MVP target:

- `longrun_agent/long_run/db.py`
- `longrun_agent/long_run/cli.py`
- `longrun_agent/tools/long_run.py`

Rename rule:

- Source term `kanban` becomes user-facing term `long-run`.
- Internal names should prefer `long_run`.
- Only mention `kanban` in source-map comments when pointing back to MyAgent.

