# CLI Command Audit

Date: 2026-06-23

This audit checks the revised CLI-only MVP command list against the current
LongRun Agent implementation.

## Implemented Command Surface

Session aliases:

- `longrun new`
- `longrun resume`
- `longrun sessions`
- `longrun history`
- `longrun clear`
- `longrun save`
- `longrun compress`
- `longrun status`
- `longrun stop`
- `longrun quit`

Session namespace:

- `longrun session new`
- `longrun session list`
- `longrun session history`
- `longrun session add-message`
- `longrun session clear`
- `longrun session save`

Auth/config/model:

- `longrun auth status`
- `longrun auth set-openai-key`
- `longrun auth set-codex-tokens`
- `longrun auth import-codex-cli`
- `longrun auth logout`
- `longrun config init`
- `longrun config show`
- `longrun model show`
- `longrun model set`
- `longrun reasoning show`
- `longrun reasoning set`
- `longrun verbose show`
- `longrun verbose on`
- `longrun verbose off`

Tools/extensions:

- `longrun tools list`
- `longrun tools call`
- `longrun toolsets list`
- `longrun skills list`
- `longrun skills view`
- `longrun skills import-bundled`
- `longrun plugins list`
- `longrun plugins hooks`
- `longrun plugins reload`
- `longrun plugins enable`
- `longrun plugins disable`
- `longrun mcp list`
- `longrun mcp add-stdio`
- `longrun mcp remove`
- `longrun mcp reload`
- `longrun mcp tools`
- `longrun reload`
- `longrun reload-skills`
- `longrun reload-mcp`

Memory/context:

- `longrun memory list`
- `longrun memory get`
- `longrun memory set`
- `longrun memory delete`
- `longrun memory clear`
- `longrun context show`
- `longrun context compress`
- `longrun session-search`

Safety:

- `longrun checkpoints`
- `longrun rollback`
- `longrun debug`

Local execution:

- `longrun terminal run`
- `longrun process start`
- `longrun process poll`
- `longrun process kill`
- `longrun process list`

Multi-agent:

- `longrun agents list`
- `longrun agents delegate`
- `longrun background start`
- `longrun background list`
- `longrun background show`
- `longrun background poll`
- `longrun background kill`
- `longrun queue add`
- `longrun queue list`
- `longrun queue show`
- `longrun queue claim`
- `longrun queue complete`
- `longrun queue fail`

Long-Run workflow:

- `longrun long-run init`
- `longrun long-run create`
- `longrun long-run list`
- `longrun long-run show`
- `longrun long-run assign`
- `longrun long-run claim`
- `longrun long-run complete`
- `longrun long-run block`
- `longrun long-run unblock`
- `longrun long-run comment`
- `longrun long-run dispatch`
- `longrun long-run tail`
- `longrun long-run stats`
- `longrun long-run runs`
- `longrun long-run heartbeat`

## Implemented Core Behind The Commands

- Model-driven tool loop for OpenAI Chat Completions.
- Central tool execution path with hooks, guardrails, approvals, stale-file checks, checkpoints, registry dispatch, and post-tool hooks.
- Durable message metadata for assistant tool calls and tool results.
- Memory store in `~/.longrun-agent/memory.json`.
- Session search over persisted SQLite messages.
- Plugin loader from `~/.longrun-agent/plugins/<name>/`.
- Deterministic hook lifecycle.
- Stdio MCP server config, reload, cached tool registration, and tool call bridge.
- Subagent delegate tool with default recursion guard.
- Subagent memory-mutation guard.
- Durable queue/background job table in `state.db`.
- Long-Run board SQLite DBs under `~/.longrun-agent/long-run/boards/<board>/`.

## Verified Smoke Tests

- `python -m compileall longrun_agent`
- Memory commands plus `session-search`.
- Fake model tool-call loop through `diagnostic_echo`.
- Plugin tool and hook mutation.
- MCP stdio fake server discovery and tool call.
- Subagent depth guard and subagent memory guard.
- Queue add, claim, and complete.
- Long-Run init, create, assign, claim, heartbeat, comment, complete, tail, stats, runs.
- Session alias, reasoning, verbose, toolsets, reload, debug, stop, and quit commands.

## Remaining Non-Command Gaps

The command surface is now covered, but the MVP is not fully complete until
these deeper behaviors are finished and verified:

- Interactive slash-command REPL is still not implemented; current surface is
  argparse subcommands.
- Codex Responses transport still has text-only calls; Codex tool-call/result
  bridging is not proven.
- OpenAI reasoning config is persisted but not passed into model requests yet.
- Long-Run `dispatch` claims work durably, but does not yet launch and monitor
  a real worker agent process by itself.
- Background child agent jobs launch real chat processes, but live network/model
  execution has not been smoke-tested in this command audit.
- Skill slash commands are list/read/import only; slash command injection into a
  user turn is not implemented.
- Checkpointing covers file mutation; terminal mutation checkpoints are not
  meaningfully represented yet.
- No full pytest suite exists yet; verification is smoke-test based.
