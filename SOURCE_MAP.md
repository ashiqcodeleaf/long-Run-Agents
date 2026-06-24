# LongRun Source Map

## CLI

- `longrun_agent/cli/main.py`: argparse entrypoint and top-level commands.
- `longrun_agent/cli/interactive.py`: interactive shell, prompt_toolkit integration, slash dispatch, `/goal` loop.
- `longrun_agent/cli/commands.py`: slash command registry and completer.
- `longrun_agent/cli/banner.py`: Rich panels, activity lines, help rendering.

## Agent

- `longrun_agent/agent/runtime.py`: `AIAgent`, session setup, context setup, transport selection.
- `longrun_agent/agent/loop.py`: model/tool iteration loop.
- `longrun_agent/agent/context.py`: prompt cache, token estimate, compression trigger.
- `longrun_agent/agent/prompt.py`: cached system prompt builder.
- `longrun_agent/agent/transports/codex.py`: Codex OAuth Responses transport.
- `longrun_agent/agent/transports/openai.py`: OpenAI API transport.

## Tools

- `longrun_agent/tools/registry.py`: central tool registration and dispatch.
- `longrun_agent/tools/catalog.py`: MyAgent-derived tool category map.
- `longrun_agent/tools/files.py`: file read/write/patch/search.
- `longrun_agent/tools/terminal.py`: foreground shell command execution.
- `longrun_agent/tools/processes.py`: background shell sessions.
- `longrun_agent/tools/delegate.py`: child agent delegation.
- `longrun_agent/tools/long_run.py`: Long-Run model tools.

