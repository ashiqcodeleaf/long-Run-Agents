# LongRun Implementation Rules

LongRun is a CLI-only agent MVP inspired by MyAgent. Keep the core narrow and put optional capability behind skills, plugins, MCP, or staged toolsets.

## Rules

- Do not add gateway, desktop, web dashboard, browser automation, computer-use, voice, image, or video features to core.
- Keep OpenAI API key and Codex OAuth as the only auth paths for now.
- All model tools must execute through `longrun_agent.agent.tool_executor.execute_tool_call`.
- Prefer `file_write` for creating files. Use `terminal_run` for verification commands.
- Preserve cached system prompts across normal turns.
- Add focused tests for every CLI, tool, transport, or context behavior change.
- Keep commands and slash commands discoverable from one registry where possible.

