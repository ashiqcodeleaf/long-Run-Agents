# Tools And Safety Plan

Every tool call must use the same execution path. The model should not be able
to bypass hooks, guardrails, approvals, or checkpoints.

## Tool Executor Order

```text
parse tool call
  -> pre_tool_call hook
  -> scope validation
  -> guardrails
  -> approval check
  -> checkpoint if mutating
  -> registry dispatch
  -> file-state tracking
  -> post_tool_call hook
  -> append tool result
  -> persist state
```

## Required Tool Categories

Terminal:

- run foreground command.
- start background command.
- poll background command.
- kill background command.

Files:

- read file.
- write file.
- patch file.
- search files.

Agent:

- memory.
- session search.
- skills list.
- skill read.
- delegate task.
- Long-Run task tools.

## File-State Tracking

The MVP must record:

- file reads.
- file writes.
- file modification time.
- file hash or comparable content fingerprint.
- task/session that read or wrote the path.

Before writing or patching:

- verify the file was not changed after read.
- reject stale writes.
- explain which file changed and why the write was blocked.

## Checkpoints

Before mutating tools run, create a checkpoint.

Mutating tools:

- file write.
- file patch.
- terminal commands that may modify files.

Checkpoint must store:

- file path.
- previous content.
- timestamp.
- session id.
- tool call id.

Rollback must:

- list checkpoints.
- restore selected checkpoint.
- record the rollback as a session event.

## Approvals

Dangerous commands require approval unless config explicitly disables it.

Examples:

- recursive delete.
- formatting drives.
- changing permissions broadly.
- killing broad process groups.
- commands touching auth files.
- commands touching agent home secrets.

Approval hooks:

- `pre_approval_request`
- `post_approval_response`

## Guardrails

Guardrails return one of:

- allow.
- block.
- require approval.

Guardrails must run before execution and after plugin `pre_tool_call`.

## Smoke Tests

- `echo hello` returns stdout.
- background process can be polled.
- background process can be killed.
- stale file patch is blocked.
- checkpoint is created before patch.
- rollback restores original file.
- dangerous command requests approval.

