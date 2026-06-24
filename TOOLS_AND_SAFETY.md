# LongRun Tools And Safety

## Imported MVP Toolsets

- `file`: read, write, patch, search.
- `terminal`: foreground shell command execution.
- `process`: background shell processes.
- `memory`: local memory store.
- `session`: session search.
- `skills`: list and read skill documents as tools.
- `todo`: session task planning and progress tracking.
- `clarify`: model-triggered user clarification in the interactive CLI.
- `code_execution`: local Python scripts that can call LongRun tools through `longrun_tools`.
- `subagent`: child agent delegation.
- `long-run`: durable task workflow.
- `diagnostic`: tool-path proof helpers.

## Staged Toolsets

- `skill_manage`: skill creation/editing is still kept outside model tools for this MVP.

## Excluded For Now

Browser automation, computer-use, image/video generation, voice, web dashboard, desktop app, and messaging gateways are not part of the CLI-only MVP.

## Execution Path

Every model tool call should pass through:

```text
model tool call -> hook/guardrail/approval/checkpoint -> registry dispatch -> result persistence
```
