# Stage 0 Function Walkthrough

Stage 0 creates the runnable skeleton only. It does not include sessions,
auth, model calls, tools, subagents, or Long-Run workers yet.

The goal of this stage is to prove:

- the package imports.
- the `longrun` CLI entrypoint works.
- the LongRun home folder can be created.
- logs can be initialized.
- SQLite can create the base tables.

## `pyproject.toml`

### `[build-system]`

Why it exists:

Python build tools need to know how to package this project.

How it is used:

`uv run longrun ...` reads this section and builds the package locally.

When it is used:

- local CLI runs through `uv`.
- future installs.
- future CI test runs.

### `[project]`

Why it exists:

This declares the package name, version, Python version, and dependencies.

How it is used:

Build/install tools use it as project metadata.

When it is used:

- `uv run longrun --version`
- packaging.
- dependency resolution.

### `[project.scripts]`

Why it exists:

This creates the real CLI command:

```text
longrun
```

How it is used:

It points the command to:

```text
longrun_agent.cli.main:main
```

When it is used:

Every time the user runs:

```powershell
uv run longrun status
```

## `longrun_agent/__init__.py`

### `__version__`

Why it exists:

The app needs one source of truth for the current package version.

How it is used:

`cli/main.py` imports it and prints it.

When it is used:

- `longrun --version`
- `longrun status`
- future diagnostics and bug reports.

## `longrun_agent/config.py`

This module owns paths and default settings. It is deliberately small in Stage 0.
Real YAML config reading starts in Stage 1.

### `DEFAULT_CONFIG`

Why it exists:

The app needs safe defaults before the user has a `config.yaml`.

How it is used:

`load_config()` returns a copy of it.

When it is used:

- Stage 0 `status`.
- fallback defaults in Stage 1.
- future startup when config keys are missing.

Current defaults:

- model: `gpt-4.1-mini`
- max iterations: `90`
- approval mode: `default`

### `get_longrun_home()`

Why it exists:

The app needs one stable home directory for its local state.

How it is used:

Other functions call it to build paths for config, logs, database, plugins,
skills, MCP, checkpoints, and Long-Run data.

When it is used:

- every CLI startup.
- tests that override `LONGRUN_AGENT_HOME`.
- future profile or workspace isolation.

Normal output:

```text
C:\Users\<user>\.longrun-agent
```

Test/dev override:

```powershell
$env:LONGRUN_AGENT_HOME = "C:\temp\longrun-test"
```

### `ensure_home()`

Why it exists:

Before LongRun can write logs, SQLite data, checkpoints, plugins, or Long-Run
board files, the folders must exist.

How it is used:

It creates the basic home layout and returns the home path.

When it is used:

- `longrun status`.
- logging setup.
- SQLite connection setup.
- future commands that need local storage.

Folders it creates:

```text
~/.longrun-agent/
  logs/
  skills/
  plugins/
  mcp/
  checkpoints/
  long-run/
```

### `config_path()`

Why it exists:

The code should not repeat the config path manually in many places.

How it is used:

Stage 1 will use it to read and write:

```text
~/.longrun-agent/config.yaml
```

When it is used:

- `longrun config show`
- `longrun config set`
- normal startup config loading.

### `env_path()`

Why it exists:

Secrets need a single official `.env` path.

How it is used:

Stage 2 auth will use it to load API-key secrets.

When it is used:

- OpenAI API key auth.
- future secret loading.

Rule:

`.env` is for secrets only. Behavior settings go in `config.yaml`.

### `state_db_path()`

Why it exists:

SQLite needs a single official database path.

How it is used:

`state.connect()` uses it when no explicit database path is passed.

When it is used:

- session storage.
- message storage.
- prompt snapshots.
- future summaries and search.

### `load_config()`

Why it exists:

Other modules need a config object even before real config parsing exists.

How it is used:

Stage 0 returns a copy of `DEFAULT_CONFIG`.

When it is used:

- `longrun status`.
- future CLI startup.

Why it returns a copy:

Returning a copy prevents one caller from accidentally mutating the global
defaults for the whole process.

## `longrun_agent/logging.py`

This module owns app logging. It does not print to the terminal directly.

### `setup_logging()`

Why it exists:

The CLI needs durable log files for later debugging.

How it is used:

It creates the home folder, configures the `longrun_agent` logger, and writes
logs to:

```text
~/.longrun-agent/logs/agent.log
~/.longrun-agent/logs/errors.log
```

When it is used:

- `longrun status`.
- future CLI startup.
- future model/tool/session debugging.

Important behavior:

- `agent.log` receives INFO and above.
- `errors.log` receives WARNING and above.
- existing logger handlers are cleared first so repeated setup does not
  duplicate log lines.

## `longrun_agent/state.py`

This module owns the first SQLite schema. Stage 0 only creates enough tables to
prove storage works.

### `SCHEMA`

Why it exists:

The app needs durable tables for sessions, messages, and cached system prompts.

How it is used:

`connect()` runs this schema with `CREATE TABLE IF NOT EXISTS`.

When it is used:

- first CLI status run.
- every later database connection.
- future migrations can build on this base.

Tables:

- `sessions`: one row per conversation.
- `messages`: user, assistant, and future tool messages.
- `prompt_snapshots`: cached system prompt per session.

Why `prompt_snapshots` exists already:

Prompt caching is a core invariant. Even though Stage 0 does not build prompts
yet, the storage table exists so later stages have the correct shape.

### `connect(db_path=None)`

Why it exists:

All database users need one safe way to open SQLite and ensure tables exist.

How it is used:

`get_state_summary()` calls it. Future session commands will call it too.

When it is used:

- `longrun status`.
- Stage 1 session creation.
- Stage 4 prompt caching.

Why `db_path` is optional:

Normal app code uses the default path. Tests can pass a temporary database path
without touching the user's real state.

### `get_state_summary()`

Why it exists:

The Stage 0 CLI needs a simple proof that SQLite is working.

How it is used:

`cli/main.py` calls it from `print_status()`.

When it is used:

- `longrun status`.
- future diagnostics.

Current output:

- database path.
- session count.
- message count.

## `longrun_agent/cli/commands.py`

This module is the beginning of the command registry.

### `CommandDef`

Why it exists:

Commands should have structured metadata instead of being loose strings.

How it is used:

Stage 0 stores command name and description.

When it is used:

- help text.
- future slash command registry.
- future autocomplete.

Why it is frozen:

Command definitions should not be mutated at runtime.

### `COMMANDS`

Why it exists:

The CLI needs one list of known commands.

How it is used:

Stage 0 only registers `status`.

When it is used:

- future `/help`.
- future command dispatch.
- future validation.

### `command_names()`

Why it exists:

Some code will need just the command names, not full metadata.

How it is used:

Currently available for future CLI help and tests.

When it is used:

- command validation.
- autocomplete.
- help output.

## `longrun_agent/cli/main.py`

This is the CLI entrypoint.

### `build_parser()`

Why it exists:

The CLI needs one place to define command-line arguments.

How it is used:

`main()` calls it before parsing user input.

When it is used:

- every CLI invocation.
- `longrun --version`.
- `longrun status`.

Why `argparse` is used:

It is built into Python and enough for Stage 0. Richer CLI behavior can come
later if needed.

### `print_status()`

Why it exists:

Stage 0 needs a visible proof command.

How it is used:

It initializes home/logging/state and prints a compact runtime summary.

When it is used:

```powershell
uv run longrun status
```

What it proves:

- home path resolution works.
- home folders can be created.
- logging can initialize.
- SQLite can initialize.
- default config can load.

### `main(argv=None)`

Why it exists:

This is the public CLI entrypoint used by `pyproject.toml`.

How it is used:

`longrun` calls this function through:

```text
longrun_agent.cli.main:main
```

When it is used:

- direct module execution.
- console script execution.
- future tests that pass a custom `argv` list.

Why it accepts `argv`:

Tests can call `main(["status"])` without starting a new process.

### `if __name__ == "__main__"`

Why it exists:

It lets the module run directly with Python.

How it is used:

```powershell
python -m longrun_agent.cli.main status
```

When it is used:

- development.
- smoke tests.
- debugging CLI behavior before installation.

## Stage 0 Completion Proof

The phase is complete when these pass:

```powershell
uv run longrun --version
uv run longrun status
python -m compileall longrun_agent
```

Expected behavior:

- version prints `LongRun Agent 0.1.0`.
- status prints home path, config path, state DB path, session count, message
  count, and default model.
- compileall finishes without syntax errors.

