# Stage 1 Function Plan

Stage 1 adds config, storage, and sessions. It still does not call a model and
does not run tools.

The purpose is to make the CLI remember local conversations before any AI logic
exists.

## Stage 1 User Behaviors

By the end of Stage 1, the user should be able to:

- create a session.
- list sessions.
- resume a session.
- add a local fake message.
- read message history.
- clear a session's messages.
- save/export a session transcript.
- show config defaults.
- write a simple `config.yaml`.

## Files We Will Modify

- `longrun_agent/config.py`
- `longrun_agent/state.py`
- `longrun_agent/cli/commands.py`
- `longrun_agent/cli/main.py`

## Files We May Add

- `longrun_agent/cli/session_commands.py`

Why this optional file may exist:

`main.py` should stay small. If session command handling starts making
`main.py` hard to read, we move session behavior into this separate module.

## Config Functions

### `write_default_config_if_missing()`

Why it exists:

Users need a real `config.yaml` file they can inspect and edit. Stage 0 only
returned in-memory defaults.

How it is used:

The CLI calls this during startup or `longrun config init`.

When it is used:

- first run.
- user deletes config and wants it recreated.
- setup flow later.

Expected behavior:

- If `config.yaml` does not exist, write defaults.
- If it already exists, do not overwrite it.

### `load_config()`

Why it exists:

Every later subsystem needs behavior settings from one place.

How it is used:

The CLI and future agent runtime call it before work starts.

When it is used:

- `longrun status`.
- `longrun config show`.
- future model setup.
- future approvals/checkpoints/tool settings.

Stage 1 behavior:

- load defaults.
- read `config.yaml` if present.
- merge file values over defaults.

Important rule:

Missing keys should fall back to defaults.

### `save_config(config)`

Why it exists:

The CLI needs a safe way to persist behavior settings.

How it is used:

Config commands call it after changing settings.

When it is used:

- future `longrun config set model ...`.
- future setup wizard.
- tests that verify config persistence.

### `merge_config(defaults, overrides)`

Why it exists:

Nested config sections must merge safely. Replacing the entire config would
delete default sections.

How it is used:

`load_config()` uses it after parsing `config.yaml`.

When it is used:

- loading partial user config.
- adding future config sections without breaking old config files.

Example:

If defaults have:

```yaml
approvals:
  mode: default
```

and user config only has:

```yaml
model: gpt-4.1
```

the final config should still include `approvals.mode`.

### `get_config_value(config, dotted_key)`

Why it exists:

CLI commands need to read nested settings with simple names.

How it is used:

Future command handlers can call:

```text
get_config_value(config, "approvals.mode")
```

When it is used:

- config display.
- config get command.
- future feature gates.

### `set_config_value(config, dotted_key, value)`

Why it exists:

Users need to change nested config settings without editing YAML manually.

How it is used:

Future command handlers can call:

```text
set_config_value(config, "model", "gpt-4.1")
set_config_value(config, "approvals.mode", "strict")
```

When it is used:

- config set command.
- setup flow.

## Session Storage Functions

### `create_session(title=None)`

Why it exists:

Each conversation needs a durable session id.

How it is used:

The CLI calls it when the user runs `/new` or starts the first session.

When it is used:

- `longrun session new`
- future interactive `/new`
- Long-Run worker sessions later.

Expected behavior:

- generate a unique session id.
- store title.
- store created/updated timestamps.
- return the created session row or id.

### `get_session(session_id)`

Why it exists:

Commands need to verify a session exists before reading or writing messages.

How it is used:

Resume, history, save, and add-message commands call it.

When it is used:

- `longrun session resume <id>`
- history reads.
- future prompt runs.

Expected behavior:

- return session data if found.
- return `None` or raise a clear error if missing.

### `list_sessions(limit=20)`

Why it exists:

Users need to see previous sessions.

How it is used:

The CLI calls it for session list output.

When it is used:

- `longrun session list`
- future `/sessions`.
- startup resume picker later.

Expected behavior:

- newest updated sessions first.
- include id, title, created time, updated time, and message count.

### `touch_session(session_id)`

Why it exists:

When messages are added or cleared, the session's `updated_at` should change.

How it is used:

Message write functions call it after changes.

When it is used:

- add message.
- clear messages.
- future prompt response save.

### `add_message(session_id, role, content)`

Why it exists:

Conversation history is made of messages.

How it is used:

The CLI calls it in Stage 1 with fake/local messages. Later the agent runtime
will call it for user, assistant, and tool messages.

When it is used:

- `longrun session add-message <id> user "hello"`
- future chat turns.
- future tool result persistence.

Validation:

- role must be one of the allowed message roles.
- content must not be empty.
- session must exist.

Allowed roles in Stage 1:

- `user`
- `assistant`
- `system`
- `tool`

### `list_messages(session_id, limit=None)`

Why it exists:

Users need to inspect conversation history.

How it is used:

The CLI calls it for history output and saving transcripts.

When it is used:

- `longrun session history <id>`
- `longrun session save <id>`
- future context builder.

Expected behavior:

- oldest messages first.
- optional limit.

### `clear_messages(session_id)`

Why it exists:

The user needs a way to reset a session without deleting the session row.

How it is used:

The CLI calls it for clear behavior.

When it is used:

- `longrun session clear <id>`
- future `/clear`.

Expected behavior:

- delete messages for the session.
- keep the session id.
- update `updated_at`.

### `save_transcript(session_id, output_path)`

Why it exists:

Users need to export session history to a readable file.

How it is used:

The CLI calls it for save/export behavior.

When it is used:

- `longrun session save <id> transcript.md`
- future `/save`.

Expected output:

Markdown with session title, id, and messages.

### `delete_session(session_id)`

Why it may exist:

Deleting sessions is useful, but it is more destructive than clear.

Decision for Stage 1:

Do not implement deletion yet unless needed. Implement `clear_messages()` first.

Reason:

Keeping the session row makes early testing easier and avoids accidental data
loss.

## CLI Commands For Stage 1

Use subcommands first. Slash commands come later when the interactive loop
exists.

### `longrun config show`

Why it exists:

The user needs to see the active config.

How it is used:

Reads config and prints the merged result.

When it is used:

- verifying defaults.
- checking config file changes.

### `longrun config init`

Why it exists:

The user needs a simple way to create `config.yaml`.

How it is used:

Calls `write_default_config_if_missing()`.

When it is used:

- first setup.
- repairing missing config.

### `longrun session new [title]`

Why it exists:

Creates a new empty conversation.

How it is used:

Calls `create_session(title)`.

When it is used:

- starting a conversation.
- testing storage.

### `longrun session list`

Why it exists:

Shows saved conversations.

How it is used:

Calls `list_sessions()`.

When it is used:

- finding a session id to resume.

### `longrun session history <session_id>`

Why it exists:

Shows the messages in a session.

How it is used:

Calls `list_messages(session_id)`.

When it is used:

- verifying messages persisted.
- reading previous conversation state.

### `longrun session add-message <session_id> <role> <content>`

Why it exists:

Stage 1 has no model yet, so we need a local way to prove message storage.

How it is used:

Calls `add_message(session_id, role, content)`.

When it is used:

- smoke test.
- database verification.

### `longrun session clear <session_id>`

Why it exists:

Resets messages while keeping the session id.

How it is used:

Calls `clear_messages(session_id)`.

When it is used:

- smoke test.
- user cleanup.

### `longrun session save <session_id> <output_path>`

Why it exists:

Exports a session transcript.

How it is used:

Calls `save_transcript(session_id, output_path)`.

When it is used:

- proof artifact.
- sharing conversation history later.

## Stage 1 Smoke Test

The Stage 1 smoke test should be:

```powershell
uv run longrun config init
uv run longrun config show
uv run longrun session new "first local session"
uv run longrun session list
uv run longrun session add-message <session_id> user "hello from stage 1"
uv run longrun session history <session_id>
uv run longrun session save <session_id> stage1-transcript.md
uv run longrun session clear <session_id>
uv run longrun session history <session_id>
```

Expected proof:

- `config.yaml` exists.
- session row exists.
- message row exists after add-message.
- transcript file exists.
- history is empty after clear.

## What We Are Not Adding In Stage 1

Do not add:

- model calls.
- OpenAI auth.
- Codex auth.
- tool registry.
- terminal tools.
- file tools.
- memory tool.
- prompt builder.
- context compression.
- subagents.
- Long-Run workers.

Those come in later stages.

