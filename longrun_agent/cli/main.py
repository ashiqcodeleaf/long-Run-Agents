"""Command-line entry point for LongRun Agent."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from getpass import getpass
from pathlib import Path
from typing import Any, Sequence

from longrun_agent import __version__
from longrun_agent.agent.context import inspect_session_context, manual_compress_session
from longrun_agent.agent.model_metadata import CODEX_CONTEXT_LENGTHS, MODEL_CONTEXT_LENGTHS
from longrun_agent.agent.runtime import AIAgent
from longrun_agent.auth import (
    CODEX_PROVIDER,
    OPENAI_API_PROVIDER,
    clear_provider,
    get_provider_statuses,
    import_codex_cli_tokens,
    login_codex_device_code,
    load_auth_store,
    save_auth_store,
    set_codex_tokens,
    set_openai_api_key,
)
from longrun_agent.config import (
    DEFAULT_CODEX_MODEL,
    auth_path,
    config_path,
    env_path,
    ensure_home,
    format_config,
    get_longrun_home,
    load_config,
    memory_path,
    save_config,
    set_config_value,
    write_default_config_if_missing,
)
from longrun_agent.cron import jobs as cron_jobs
from longrun_agent.cron.runner import preview_job, tick as cron_tick, trigger_and_run
from longrun_agent.hooks import hook_manager
from longrun_agent.long_run import db as long_run_db
from longrun_agent.logging import setup_logging
from longrun_agent.mcp.client import (
    add_stdio_server,
    cached_mcp_tools,
    list_mcp_servers,
    reload_mcp_tools,
    remove_mcp_server,
)
from longrun_agent.plugins.loader import list_plugins, reload_plugins, set_plugin_enabled
from longrun_agent.safety.checkpoints import list_checkpoints, rollback_checkpoint
from longrun_agent.state import (
    add_message,
    clear_messages,
    claim_next_agent_job,
    create_agent_job,
    create_session,
    get_agent_job,
    get_state_summary,
    get_session,
    list_agent_jobs,
    list_messages,
    list_sessions,
    save_transcript,
    update_agent_job,
)
from longrun_agent.tools.memory import clear_memory
from longrun_agent.tools.registry import registry
from longrun_agent.tools.catalog import TOOLSET_CATALOG, classify_toolset, group_tool_definitions
from longrun_agent.agent.tool_executor import execute_tool_call
from longrun_agent.tools.skills import import_bundled_skills, list_skills, read_skill
from longrun_agent.cli.todo import add_todo, clear_todos, complete_todo, list_todos, todo_path
from longrun_agent.workspace import (
    build_plan,
    create_run,
    init_workspace,
    list_workspace_logs,
    read_workspace_log,
    workspace_status,
)

try:
    from rich import box
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover
    box = None  # type: ignore[assignment]
    Console = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]

_RICH_CONSOLE = Console(highlight=False) if Console is not None else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="longrun",
        description=(
            "LongRun is a CLI-first agentic workspace tool. It records tasks, "
            "plans runs, manages local tools/workers, and grows toward durable "
            "long-running agent workflows."
        ),
        epilog=(
            "Examples:\n"
            "  longrun\n"
            "  longrun setup\n"
            "  longrun chat \"explain this repo\"\n"
            "  longrun plan \"refactor the CLI\"\n"
            "  longrun status\n"
            "  longrun tools list\n"
            "  longrun cron list\n"
            "  longrun long-run init\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init", help="Create the local .longrun workspace")
    run_parser = subparsers.add_parser("run", help="Create a planned MVP run for a task")
    run_parser.add_argument("task", nargs="+", help="Task prompt to record")

    plan_parser = subparsers.add_parser("plan", help="Print a structured plan for a task")
    plan_parser.add_argument("task", nargs="+", help="Task prompt to plan")
    plan_parser.add_argument("--json", action="store_true", help="Print the raw plan JSON")

    subparsers.add_parser("status", help="Show Stage 0 runtime status")
    subparsers.add_parser("debug", help="Show diagnostic state")
    subparsers.add_parser("doctor", help="Run local health checks")
    subparsers.add_parser("version", help="Print version and exit")

    todo_parser = subparsers.add_parser("todo", help="Manage a local to-do list")
    todo_subparsers = todo_parser.add_subparsers(dest="todo_command")
    todo_add = todo_subparsers.add_parser("add", help="Add a to-do item")
    todo_add.add_argument("title", nargs="+")
    todo_subparsers.add_parser("list", help="List to-do items")
    todo_done = todo_subparsers.add_parser("done", help="Mark one to-do item complete")
    todo_done.add_argument("id", type=int)
    todo_subparsers.add_parser("clear", help="Clear the to-do list")

    subparsers.add_parser("quit", help="Exit successfully in non-interactive CLI mode")
    subparsers.add_parser("stop", help="Stop the current non-interactive command")
    subparsers.add_parser("reload", help="Reload plugins and MCP tool cache")
    subparsers.add_parser("reload-mcp", help="Reload MCP server tools")
    subparsers.add_parser("reload-skills", help="Show refreshed skill inventory")

    setup_parser = subparsers.add_parser("setup", help="Configure LongRun auth, model, and workspace")
    setup_parser.add_argument("--non-interactive", action="store_true", help="Create files and print next steps only")
    setup_parser.add_argument("--openai-key", help="Store an OpenAI API key in auth.json")
    setup_parser.add_argument("--codex-login", action="store_true", help="Sign in to ChatGPT/Codex in the browser")
    setup_parser.add_argument("--codex-import", action="store_true", help="Import existing Codex CLI OAuth tokens")
    setup_parser.add_argument("--no-browser", action="store_true", help="For --codex-login, print URL/code but do not open a browser")
    setup_parser.add_argument("--model", help="Default model to save in config.yaml")
    setup_parser.add_argument("--provider", choices=(OPENAI_API_PROVIDER, CODEX_PROVIDER), help="Default provider")

    logout_parser = subparsers.add_parser("logout", help="Remove stored provider credentials")
    logout_parser.add_argument("provider", nargs="?", default="all", choices=(OPENAI_API_PROVIDER, CODEX_PROVIDER, "all"))

    subparsers.add_parser("hooks", help="List registered hooks")

    models_parser = subparsers.add_parser("models", help="List or update model configuration")
    models_subparsers = models_parser.add_subparsers(dest="models_command")
    models_subparsers.add_parser("show", help="Show active model/provider")
    models_subparsers.add_parser("list", help="List known MVP model metadata")
    models_set = models_subparsers.add_parser("set", help="Set active model/provider")
    models_set.add_argument("model")
    models_set.add_argument("--provider", choices=(OPENAI_API_PROVIDER, CODEX_PROVIDER))

    workers_parser = subparsers.add_parser("workers", help="Show worker and background-job status")
    workers_subparsers = workers_parser.add_subparsers(dest="workers_command")
    workers_subparsers.add_parser("list", help="List workers and background jobs")

    logs_parser = subparsers.add_parser("logs", help="View local .longrun logs")
    logs_parser.add_argument("log_name", nargs="?", default="longrun.log")
    logs_parser.add_argument("-n", "--lines", type=int, default=50)
    logs_parser.add_argument("--list", action="store_true", help="List log files")

    new_parser = subparsers.add_parser("new", help="Create a new session")
    new_parser.add_argument("title", nargs="*")

    resume_parser = subparsers.add_parser("resume", help="Show a session for resuming")
    resume_parser.add_argument("session_id")

    subparsers.add_parser("sessions", help="List recent sessions")

    history_parser = subparsers.add_parser("history", help="Show session history")
    history_parser.add_argument("session_id")

    clear_parser = subparsers.add_parser("clear", help="Clear session messages")
    clear_parser.add_argument("session_id")

    save_parser = subparsers.add_parser("save", help="Save a session transcript")
    save_parser.add_argument("session_id")
    save_parser.add_argument("output_path")

    compress_parser = subparsers.add_parser("compress", help="Compress session context")
    compress_parser.add_argument("session_id")

    chat_parser = subparsers.add_parser("chat", help="Run one no-tool chat turn")
    chat_parser.add_argument("message", nargs="+", help="Message to send")
    chat_parser.add_argument("--session-id", help="Existing session id")
    chat_parser.add_argument("--title", help="Title for a new session")
    chat_parser.add_argument("--provider", choices=(OPENAI_API_PROVIDER, CODEX_PROVIDER))
    chat_parser.add_argument("--model", help="Model override for this run")

    auth_parser = subparsers.add_parser("auth", help="Manage OpenAI/Codex auth")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")
    auth_subparsers.add_parser("status", help="Show redacted auth status")

    auth_login_codex = auth_subparsers.add_parser(
        "login-codex",
        aliases=("login",),
        help="Sign in to ChatGPT/Codex with browser device-code OAuth",
    )
    auth_login_codex.add_argument("--no-browser", action="store_true", help="Print URL/code but do not open a browser")
    auth_login_codex.add_argument("--timeout", type=int, default=900, help="Approval timeout in seconds")
    auth_login_codex.add_argument("--fresh", action="store_true", help="Skip existing Codex CLI auth import and force a fresh browser login")

    auth_set_openai = auth_subparsers.add_parser("set-openai-key", help="Store OpenAI API key")
    auth_set_openai.add_argument("api_key", nargs="?", help="Optional key; prompts when omitted")

    auth_set_codex = auth_subparsers.add_parser(
        "set-codex-tokens",
        help="Store Codex OAuth tokens from an external login flow",
    )
    auth_set_codex.add_argument("--access-token", required=True)
    auth_set_codex.add_argument("--refresh-token")
    auth_set_codex.add_argument("--account-id")
    auth_set_codex.add_argument("--expires-at")

    auth_import_codex = auth_subparsers.add_parser(
        "import-codex-cli",
        help="Import Codex CLI auth and select openai-codex/gpt-5.4-mini",
    )
    auth_import_codex.add_argument(
        "--model",
        default=DEFAULT_CODEX_MODEL,
        help="Codex model to select in config.yaml",
    )

    auth_logout = auth_subparsers.add_parser("logout", help="Remove stored provider credentials")
    auth_logout.add_argument("provider", choices=(OPENAI_API_PROVIDER, CODEX_PROVIDER, "all"))

    config_parser = subparsers.add_parser("config", help="Manage behavior config")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("init", help="Create config.yaml if it is missing")
    config_subparsers.add_parser("show", help="Show merged config")

    context_parser = subparsers.add_parser("context", help="Inspect or compress session context")
    context_subparsers = context_parser.add_subparsers(dest="context_command")

    context_show = context_subparsers.add_parser("show", help="Show session context metadata")
    context_show.add_argument("session_id")

    context_compress = context_subparsers.add_parser("compress", help="Create a deterministic context summary")
    context_compress.add_argument("session_id")

    file_parser = subparsers.add_parser("file", help="Read, write, patch, and search files")
    file_subparsers = file_parser.add_subparsers(dest="file_command")

    file_read = file_subparsers.add_parser("read", help="Read a file")
    file_read.add_argument("path")
    file_read.add_argument("--offset", type=int, default=1)
    file_read.add_argument("--limit", type=int, default=500)

    file_write = file_subparsers.add_parser("write", help="Write a file")
    file_write.add_argument("path")
    file_write.add_argument("--content", required=True)

    file_patch = file_subparsers.add_parser("patch", help="Patch a file by replacing one fragment")
    file_patch.add_argument("path")
    file_patch.add_argument("--old", required=True)
    file_patch.add_argument("--new", required=True)

    file_search = file_subparsers.add_parser("search", help="Search file names or content")
    file_search.add_argument("pattern")
    file_search.add_argument("--path", default=".")
    file_search.add_argument("--target", choices=("content", "name"), default="content")
    file_search.add_argument("--limit", type=int, default=50)

    tools_parser = subparsers.add_parser("tools", help="Inspect or call registered tools")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command")
    tools_subparsers.add_parser("list", help="List available tool definitions")

    tools_call = tools_subparsers.add_parser("call", help="Call a registered tool for diagnostics")
    tools_call.add_argument("name")
    tools_call.add_argument("--json", default="{}", help="JSON object arguments")
    tools_call.add_argument("--json-file", help="Read JSON object arguments from a file")
    tools_call.add_argument("--arg", action="append", default=[], help="Simple key=value argument")
    tools_call.add_argument("--approve", action="store_true", help="Approve risky diagnostic call")

    toolsets_parser = subparsers.add_parser("toolsets", help="List registered toolsets")
    toolsets_subparsers = toolsets_parser.add_subparsers(dest="toolsets_command")
    toolsets_subparsers.add_parser("list", help="List toolsets")

    terminal_parser = subparsers.add_parser("terminal", help="Run local shell commands")
    terminal_subparsers = terminal_parser.add_subparsers(dest="terminal_command")
    terminal_run = terminal_subparsers.add_parser("run", help="Run a foreground shell command")
    terminal_run.add_argument("--cwd", help="Working directory")
    terminal_run.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    terminal_run.add_argument("--approve", action="store_true", help="Approve risky command")
    terminal_run.add_argument("command_args", nargs=argparse.REMAINDER)

    process_parser = subparsers.add_parser("process", help="Manage background shell processes")
    process_subparsers = process_parser.add_subparsers(dest="process_command")
    process_start = process_subparsers.add_parser("start", help="Start a background shell command")
    process_start.add_argument("--cwd", help="Working directory")
    process_start.add_argument("--approve", action="store_true", help="Approve risky command")
    process_start.add_argument("command_args", nargs=argparse.REMAINDER)

    process_poll = process_subparsers.add_parser("poll", help="Poll a background process")
    process_poll.add_argument("id")

    process_kill = process_subparsers.add_parser("kill", help="Kill a background process")
    process_kill.add_argument("id")

    process_subparsers.add_parser("list", help="List tracked background processes")

    agents_parser = subparsers.add_parser("agents", help="Inspect or run subagents")
    agents_subparsers = agents_parser.add_subparsers(dest="agents_command")
    agents_subparsers.add_parser("list", help="Show subagent defaults and durable jobs")

    agents_delegate = agents_subparsers.add_parser("delegate", help="Run one child agent synchronously")
    agents_delegate.add_argument("prompt", nargs="+")
    agents_delegate.add_argument("--title")
    agents_delegate.add_argument("--max-depth", type=int, default=1)

    background_parser = subparsers.add_parser("background", help="Run and inspect background agent jobs")
    background_subparsers = background_parser.add_subparsers(dest="background_command")

    background_start = background_subparsers.add_parser("start", help="Start a background child agent process")
    background_start.add_argument("prompt", nargs="+")
    background_start.add_argument("--title")

    background_show = background_subparsers.add_parser("show", help="Show one background job")
    background_show.add_argument("job_id")

    background_poll = background_subparsers.add_parser("poll", help="Poll one background job process")
    background_poll.add_argument("job_id")

    background_kill = background_subparsers.add_parser("kill", help="Kill one background job process")
    background_kill.add_argument("job_id")

    background_subparsers.add_parser("list", help="List background jobs")

    queue_parser = subparsers.add_parser("queue", help="Manage durable queued agent jobs")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_command")
    queue_add = queue_subparsers.add_parser("add", help="Add a queued agent job")
    queue_add.add_argument("prompt", nargs="+")

    queue_show = queue_subparsers.add_parser("show", help="Show one queued job")
    queue_show.add_argument("job_id")

    queue_subparsers.add_parser("list", help="List queued and agent jobs")
    queue_subparsers.add_parser("claim", help="Atomically claim the oldest queued job")

    queue_complete = queue_subparsers.add_parser("complete", help="Mark a queued job complete")
    queue_complete.add_argument("job_id")
    queue_complete.add_argument("result", nargs="+")

    queue_fail = queue_subparsers.add_parser("fail", help="Mark a queued job failed")
    queue_fail.add_argument("job_id")
    queue_fail.add_argument("reason", nargs="+")

    cron_parser = subparsers.add_parser("cron", help="Manage CLI-only scheduled agent jobs")
    cron_subparsers = cron_parser.add_subparsers(dest="cron_command")

    cron_add = cron_subparsers.add_parser("add", help="Create a scheduled agent job")
    cron_add.add_argument("name")
    cron_add.add_argument("prompt", nargs="+")
    cron_add.add_argument("--schedule", default="manual")
    cron_add.add_argument("--repeat", type=int)
    cron_add.add_argument("--skill", action="append", dest="skills")
    cron_add.add_argument("--toolset", action="append", dest="enabled_toolsets")
    cron_add.add_argument("--model")
    cron_add.add_argument("--provider")

    cron_list = cron_subparsers.add_parser("list", help="List scheduled jobs")
    cron_list.add_argument("--all", action="store_true", help="Include paused/completed jobs")

    cron_show = cron_subparsers.add_parser("show", help="Show one scheduled job")
    cron_show.add_argument("job_id")

    cron_pause = cron_subparsers.add_parser("pause", help="Pause one scheduled job")
    cron_pause.add_argument("job_id")
    cron_pause.add_argument("--reason")

    cron_resume = cron_subparsers.add_parser("resume", help="Resume one scheduled job")
    cron_resume.add_argument("job_id")

    cron_remove = cron_subparsers.add_parser("remove", help="Remove one scheduled job")
    cron_remove.add_argument("job_id")

    cron_trigger = cron_subparsers.add_parser("trigger", help="Mark a job due without running it")
    cron_trigger.add_argument("job_id")

    cron_run = cron_subparsers.add_parser("run", help="Run one scheduled job immediately")
    cron_run.add_argument("job_id")

    cron_preview = cron_subparsers.add_parser("preview", help="Show the isolated prompt used by a cron job")
    cron_preview.add_argument("job_id")

    cron_subparsers.add_parser("tick", help="Run all currently due scheduled jobs")

    long_run_parser = subparsers.add_parser(
        "long-run",
        aliases=("kanban",),
        help="Durable Long-Run task workflow",
    )
    long_run_subparsers = long_run_parser.add_subparsers(dest="long_run_command")

    long_run_init = long_run_subparsers.add_parser("init", help="Initialize a Long-Run board")
    long_run_init.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_create = long_run_subparsers.add_parser("create", help="Create a Long-Run task")
    long_run_create.add_argument("title", nargs="+")
    long_run_create.add_argument("--board", default=long_run_db.DEFAULT_BOARD)
    long_run_create.add_argument("--description", default="")
    long_run_create.add_argument("--assignee")

    long_run_list = long_run_subparsers.add_parser("list", help="List Long-Run tasks")
    long_run_list.add_argument("--board", default=long_run_db.DEFAULT_BOARD)
    long_run_list.add_argument("--status")

    long_run_show = long_run_subparsers.add_parser("show", help="Show one Long-Run task")
    long_run_show.add_argument("task_id")
    long_run_show.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_assign = long_run_subparsers.add_parser("assign", help="Assign one Long-Run task")
    long_run_assign.add_argument("task_id")
    long_run_assign.add_argument("assignee")
    long_run_assign.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_claim = long_run_subparsers.add_parser("claim", help="Claim the next ready Long-Run task")
    long_run_claim.add_argument("--board", default=long_run_db.DEFAULT_BOARD)
    long_run_claim.add_argument("--worker", default="cli-worker")

    long_run_complete = long_run_subparsers.add_parser("complete", help="Complete a Long-Run task")
    long_run_complete.add_argument("task_id")
    long_run_complete.add_argument("result", nargs="+")
    long_run_complete.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_block = long_run_subparsers.add_parser("block", help="Block a Long-Run task")
    long_run_block.add_argument("task_id")
    long_run_block.add_argument("reason", nargs="+")
    long_run_block.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_unblock = long_run_subparsers.add_parser("unblock", help="Unblock a Long-Run task")
    long_run_unblock.add_argument("task_id")
    long_run_unblock.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_comment = long_run_subparsers.add_parser("comment", help="Comment on a Long-Run task")
    long_run_comment.add_argument("task_id")
    long_run_comment.add_argument("body", nargs="+")
    long_run_comment.add_argument("--board", default=long_run_db.DEFAULT_BOARD)
    long_run_comment.add_argument("--author", default="cli")

    long_run_dispatch = long_run_subparsers.add_parser("dispatch", help="Dispatch by claiming one ready task")
    long_run_dispatch.add_argument("--board", default=long_run_db.DEFAULT_BOARD)
    long_run_dispatch.add_argument("--worker", default="dispatcher")

    long_run_tail = long_run_subparsers.add_parser("tail", help="Show task comments and run logs")
    long_run_tail.add_argument("task_id")
    long_run_tail.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_stats = long_run_subparsers.add_parser("stats", help="Show Long-Run board stats")
    long_run_stats.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_runs = long_run_subparsers.add_parser("runs", help="List Long-Run runs")
    long_run_runs.add_argument("--board", default=long_run_db.DEFAULT_BOARD)

    long_run_heartbeat = long_run_subparsers.add_parser("heartbeat", help="Record worker heartbeat")
    long_run_heartbeat.add_argument("--board", default=long_run_db.DEFAULT_BOARD)
    long_run_heartbeat.add_argument("--worker", default="cli-worker")
    long_run_heartbeat.add_argument("--task-id")
    long_run_heartbeat.add_argument("--status", default="alive")

    checkpoints_parser = subparsers.add_parser("checkpoints", help="List checkpoints")
    checkpoints_parser.add_argument("checkpoint_command", choices=("list",), nargs="?", default="list")

    rollback_parser = subparsers.add_parser("rollback", help="Rollback a checkpoint")
    rollback_parser.add_argument("checkpoint_id")

    skills_parser = subparsers.add_parser("skills", help="List, view, or import skills")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")
    skills_list = skills_subparsers.add_parser("list", help="List skills")
    skills_list.add_argument("--source", choices=("all", "bundled", "home"), default="all")

    skills_view = skills_subparsers.add_parser("view", help="Read one skill")
    skills_view.add_argument("name")
    skills_view.add_argument("--source", choices=("bundled", "home"), default="bundled")

    skills_import = skills_subparsers.add_parser("import-bundled", help="Copy bundled skills to home")
    skills_import.add_argument("--overwrite", action="store_true")

    plugins_parser = subparsers.add_parser("plugins", help="List, enable, disable, or reload plugins")
    plugins_subparsers = plugins_parser.add_subparsers(dest="plugins_command")
    plugins_subparsers.add_parser("list", help="List local plugins")
    plugins_subparsers.add_parser("reload", help="Reload enabled plugins in this process")
    plugins_subparsers.add_parser("hooks", help="List registered hooks")

    plugins_enable = plugins_subparsers.add_parser("enable", help="Enable one plugin")
    plugins_enable.add_argument("name")

    plugins_disable = plugins_subparsers.add_parser("disable", help="Disable one plugin")
    plugins_disable.add_argument("name")

    mcp_parser = subparsers.add_parser("mcp", help="Configure and reload MCP stdio servers")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser("list", help="List configured MCP servers")
    mcp_subparsers.add_parser("reload", help="Discover tools from configured MCP servers")
    mcp_subparsers.add_parser("tools", help="List cached MCP tools and reload errors")

    mcp_add = mcp_subparsers.add_parser("add-stdio", help="Add or replace a stdio MCP server")
    mcp_add.add_argument("name")
    mcp_add.add_argument("--command", dest="server_command", required=True)
    mcp_add.add_argument("--arg", action="append", default=[])

    mcp_remove = mcp_subparsers.add_parser("remove", help="Remove one MCP server")
    mcp_remove.add_argument("name")

    model_parser = subparsers.add_parser("model", help="Show or set model/provider config")
    model_subparsers = model_parser.add_subparsers(dest="model_command")
    model_subparsers.add_parser("show", help="Show active model and provider")

    model_set = model_subparsers.add_parser("set", help="Set active model")
    model_set.add_argument("model")
    model_set.add_argument("--provider", choices=(OPENAI_API_PROVIDER, CODEX_PROVIDER))

    reasoning_parser = subparsers.add_parser("reasoning", help="Show or set reasoning effort")
    reasoning_subparsers = reasoning_parser.add_subparsers(dest="reasoning_command")
    reasoning_subparsers.add_parser("show", help="Show reasoning config")
    reasoning_set = reasoning_subparsers.add_parser("set", help="Set reasoning effort")
    reasoning_set.add_argument("effort", choices=("minimal", "low", "medium", "high"))

    verbose_parser = subparsers.add_parser("verbose", help="Show or set verbose mode")
    verbose_subparsers = verbose_parser.add_subparsers(dest="verbose_command")
    verbose_subparsers.add_parser("show", help="Show verbose mode")
    verbose_subparsers.add_parser("on", help="Enable verbose mode")
    verbose_subparsers.add_parser("off", help="Disable verbose mode")

    memory_parser = subparsers.add_parser("memory", help="List, read, write, or delete memory")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    memory_subparsers.add_parser("list", help="List saved memory")

    memory_get = memory_subparsers.add_parser("get", help="Read one memory entry")
    memory_get.add_argument("key")

    memory_set = memory_subparsers.add_parser("set", help="Create or update one memory entry")
    memory_set.add_argument("key")
    memory_set.add_argument("value", nargs="+")

    memory_delete = memory_subparsers.add_parser("delete", help="Delete one memory entry")
    memory_delete.add_argument("key")

    memory_clear = memory_subparsers.add_parser("clear", help="Clear all memory entries")
    memory_clear.add_argument("--yes", action="store_true", help="Confirm deletion")

    session_search = subparsers.add_parser("session-search", help="Search previous session messages")
    session_search.add_argument("query", nargs="+")
    session_search.add_argument("--limit", type=int, default=20)

    session_parser = subparsers.add_parser("session", help="Manage local sessions")
    session_subparsers = session_parser.add_subparsers(dest="session_command")

    session_new = session_subparsers.add_parser("new", help="Create a new session")
    session_new.add_argument("title", nargs="*", help="Optional session title")

    session_subparsers.add_parser("list", help="List recent sessions")

    session_history = session_subparsers.add_parser("history", help="Show session history")
    session_history.add_argument("session_id")

    session_add = session_subparsers.add_parser("add-message", help="Add a local message")
    session_add.add_argument("session_id")
    session_add.add_argument("role", choices=("user", "assistant", "system", "tool"))
    session_add.add_argument("content", nargs="+")

    session_clear = session_subparsers.add_parser("clear", help="Clear session messages")
    session_clear.add_argument("session_id")

    session_save = session_subparsers.add_parser("save", help="Save session transcript")
    session_save.add_argument("session_id")
    session_save.add_argument("output_path")
    return parser


def print_status() -> None:
    home = ensure_home()
    setup_logging()
    config = load_config()
    state = get_state_summary()
    local = workspace_status()

    print(f"LongRun Agent {__version__}")
    print(f"Workspace: {local['workspace']}")
    print(f"Workspace initialized: {local['exists']}")
    print(f"Workspace runs: {local['runs']}")
    print(f"Latest run: {local['latest_run'] or '-'}")
    print(f"Home: {home}")
    print(f"Config: {config_path()}")
    print(f"State DB: {state['db_path']}")
    print(f"Sessions: {state['sessions']}")
    print(f"Messages: {state['messages']}")
    print(f"Provider: {config['provider']}")
    print(f"Default model: {config['model']}")


def handle_setup_command(args: argparse.Namespace) -> int:
    home = ensure_home()
    config_file = write_default_config_if_missing()
    local = init_workspace()
    if not env_path().exists():
        env_path().write_text("# LongRun secrets only. Prefer auth.json for interactive setup.\n", encoding="utf-8")
    if not auth_path().exists():
        save_auth_store(load_auth_store())
    if not memory_path().exists():
        memory_path().write_text("{}\n", encoding="utf-8")

    config = load_config()
    if args.provider:
        set_config_value(config, "provider", args.provider)
    if args.model:
        set_config_value(config, "model", args.model)

    if args.openai_key:
        set_openai_api_key(args.openai_key)
        set_config_value(config, "provider", OPENAI_API_PROVIDER)
    elif not args.non_interactive and sys.stdin.isatty():
        answer = input("Store an OpenAI API key now? [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            set_openai_api_key(getpass("OpenAI API key: ").strip())
            set_config_value(config, "provider", OPENAI_API_PROVIDER)

    if args.codex_import:
        import_codex_cli_tokens()
        set_config_value(config, "provider", CODEX_PROVIDER)
        set_config_value(config, "model", args.model or DEFAULT_CODEX_MODEL)

    if args.codex_login:
        try:
            import_codex_cli_tokens()
            print("Imported existing Codex CLI browser login.")
        except RuntimeError:
            login_codex_device_code(open_browser=not args.no_browser)
        set_config_value(config, "provider", CODEX_PROVIDER)
        set_config_value(config, "model", args.model or DEFAULT_CODEX_MODEL)

    save_config(config)

    print("LongRun setup complete.")
    print(f"Home: {home}")
    print(f"Config: {config_file}")
    print(f"Auth: {auth_path()}")
    print(f"Secrets env: {env_path()}")
    print(f"Project workspace: {local['workspace']}")
    if not any(status.configured for status in get_provider_statuses()):
        print("")
        print("Auth is still missing. Configure one of:")
        print("  longrun auth set-openai-key")
        print("  longrun auth login-codex")
        print("  longrun auth import-codex-cli")
    return 0


def handle_logout_command(args: argparse.Namespace) -> int:
    providers = (OPENAI_API_PROVIDER, CODEX_PROVIDER) if args.provider == "all" else (args.provider,)
    for provider in providers:
        removed = clear_provider(provider)
        print(f"{provider}: {'removed' if removed else 'not configured'}")
    return 0


def handle_hooks_command() -> int:
    hooks = hook_manager.list_hooks()
    if not hooks:
        print("No hooks registered.")
        return 0
    for hook in hooks:
        print(f"{hook['name']} | {hook['source']}")
    return 0


def handle_doctor_command() -> int:
    home = ensure_home()
    write_default_config_if_missing()
    state = get_state_summary()
    local = workspace_status()
    print("LongRun doctor")
    print(f"Home exists: {home.exists()} ({home})")
    print(f"Config exists: {config_path().exists()} ({config_path()})")
    print(f"Auth store exists: {auth_path().exists()} ({auth_path()})")
    print(f"State DB: {state['db_path']} sessions={state['sessions']} messages={state['messages']}")
    print(f"Project workspace: {local['exists']} ({local['workspace']})")
    for status in get_provider_statuses():
        print(f"Auth {status.provider}: {'configured' if status.configured else 'missing'}")
    print(f"Registered tools: {len(registry.get_definitions())}")
    print(f"LongRun home root: {get_longrun_home()}")
    return 0


def handle_init_command(args: argparse.Namespace) -> int:
    result = init_workspace()
    print("LongRun workspace ready.")
    print(f"Workspace: {result['workspace']}")
    print(f"Config: {result['config']}")
    if result["created"]:
        print("Created:")
        for path in result["created"]:
            print(f"  {path}")
    else:
        print("No new files needed.")
    return 0


def handle_run_command(args: argparse.Namespace) -> int:
    task = " ".join(args.task)
    result = create_run(task)
    print("LongRun run created.")
    print(f"Run ID: {result['run_id']}")
    print(f"Run folder: {result['run_dir']}")
    print(f"Task saved: {result['task_path']}")
    print(f"Plan saved: {result['plan_path']}")
    print("")
    _print_plan(result["plan"])
    print("")
    print("MVP execution status:")
    print("  receive task: done")
    print("  create plan: done")
    print("  execute steps: stubbed")
    print("  validate output: stubbed")
    print("  retry/fix loop: stubbed")
    print("  final artifact: stubbed")
    return 0


def handle_plan_command(args: argparse.Namespace) -> int:
    plan = build_plan(" ".join(args.task))
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        _print_plan(plan)
    return 0


def handle_models_command(args: argparse.Namespace) -> int:
    config = load_config()
    command = args.models_command or "show"
    if command == "show":
        print(f"Provider: {config['provider']}")
        print(f"Model: {config['model']}")
        print(f"Reasoning effort: {config.get('reasoning', {}).get('effort', 'medium')}")
        return 0
    if command == "list":
        print("OpenAI API models:")
        for model, context in sorted(MODEL_CONTEXT_LENGTHS.items()):
            print(f"  {model}: context={context}")
        print("Codex OAuth models:")
        for model, context in sorted(CODEX_CONTEXT_LENGTHS.items()):
            print(f"  {model}: context={context}")
        return 0
    if command == "set":
        set_config_value(config, "model", args.model)
        if args.provider:
            set_config_value(config, "provider", args.provider)
        path = save_config(config)
        print(f"Model config saved: {path}")
        print(f"Provider: {config['provider']}")
        print(f"Model: {config['model']}")
        return 0
    print("Missing models command. Use: longrun models [show|list|set]")
    return 2


def handle_workers_command(args: argparse.Namespace) -> int:
    command = args.workers_command or "list"
    if command == "list":
        jobs = list_agent_jobs(limit=20)
        if not jobs:
            print("No durable agent jobs.")
        else:
            print("Agent jobs:")
            for job in jobs:
                _print_job(job)
        print("")
        print("Long-Run worker defaults:")
        print("  dispatcher: manual MVP command")
        print("  subagent_max_depth: 1")
        print("  subagent_concurrency: 3")
        return 0
    print("Missing workers command. Use: longrun workers [list]")
    return 2


def handle_logs_command(args: argparse.Namespace) -> int:
    if args.list:
        logs = list_workspace_logs()
        if not logs:
            print("No local .longrun logs found. Run `longrun init` first.")
            return 0
        for log in logs:
            print(f"{log['name']} | {log['bytes']} bytes | {log['path']}")
        return 0
    result = read_workspace_log(args.log_name, lines=args.lines)
    if not result["exists"]:
        print(f"Log not found: {result['path']}")
        print("Run `longrun init` or `longrun run \"task\"` first.")
        return 0
    print(result["content"])
    return 0


def _print_plan(plan: dict[str, Any]) -> None:
    print(f"Task: {plan['task']}")
    print("Plan:")
    for stage in plan["stages"]:
        print(f"  - {stage['id']}: {stage['description']} [{stage['status']}]")
    print(f"Note: {plan['mvp_note']}")


def handle_auth_command(args: argparse.Namespace) -> int:
    if args.auth_command in {None, "status"}:
        for status in get_provider_statuses():
            configured = "configured" if status.configured else "missing"
            source = f" source={status.source}" if status.source else ""
            detail = f" detail={status.detail}" if status.detail else ""
            print(f"{status.provider}: {configured}{source}{detail}")
        return 0

    if args.auth_command in {"login-codex", "login"}:
        imported = False
        try:
            if not args.fresh:
                try:
                    path = import_codex_cli_tokens()
                    imported = True
                except RuntimeError:
                    path = login_codex_device_code(
                        open_browser=not args.no_browser,
                        timeout_seconds=args.timeout,
                    )
            else:
                path = login_codex_device_code(
                    open_browser=not args.no_browser,
                    timeout_seconds=args.timeout,
                )
        except (RuntimeError, TimeoutError) as exc:
            print(f"Codex login failed: {exc}", file=sys.stderr)
            print("If you are already signed in with Codex, try: longrun auth import-codex-cli", file=sys.stderr)
            return 1
        config = load_config()
        set_config_value(config, "provider", CODEX_PROVIDER)
        set_config_value(config, "model", DEFAULT_CODEX_MODEL)
        save_config(config)
        print("")
        print("Codex login successful." if not imported else "Codex CLI browser login imported.")
        print(f"Credentials stored in {path}")
        print(f"Provider: {CODEX_PROVIDER}")
        print(f"Model: {DEFAULT_CODEX_MODEL}")
        return 0

    if args.auth_command == "set-openai-key":
        path = set_openai_api_key(args.api_key)
        print(f"OpenAI API key stored in {path}")
        return 0

    if args.auth_command == "set-codex-tokens":
        path = set_codex_tokens(
            access_token=args.access_token,
            refresh_token=args.refresh_token,
            account_id=args.account_id,
            expires_at=args.expires_at,
        )
        print(f"Codex OAuth tokens stored in {path}")
        return 0

    if args.auth_command == "import-codex-cli":
        path = import_codex_cli_tokens()
        config = load_config()
        set_config_value(config, "provider", CODEX_PROVIDER)
        set_config_value(config, "model", args.model)
        save_config(config)
        print(f"Codex CLI credentials imported into {path}")
        print(f"Provider: {CODEX_PROVIDER}")
        print(f"Model: {args.model}")
        return 0

    if args.auth_command == "logout":
        providers = (OPENAI_API_PROVIDER, CODEX_PROVIDER) if args.provider == "all" else (args.provider,)
        removed = [provider for provider in providers if clear_provider(provider)]
        if removed:
            print(f"Removed credentials for: {', '.join(removed)}")
        else:
            print("No matching credentials were stored.")
        return 0

    print("Missing auth command. Use: longrun auth status|login-codex|set-openai-key|set-codex-tokens|import-codex-cli|logout")
    return 2


def handle_chat_command(args: argparse.Namespace) -> int:
    message = " ".join(args.message)
    agent = AIAgent(
        session_id=args.session_id,
        title=args.title,
        provider=args.provider,
        model=args.model,
        event_handler=_print_agent_event,
    )
    try:
        result = agent.run_conversation(message)
    except (RuntimeError, ValueError) as exc:
        print(f"Chat failed: {exc}", file=sys.stderr)
        return 1

    print(result.final_response)
    print(f"\nSession: {result.session_id}")
    print(f"Model: {result.model} | Provider: {result.provider} | Iterations: {result.iterations}")
    print(f"Tools: {', '.join(result.tools_used) if result.tools_used else 'none'}")
    return 0


def _print_agent_event(event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "llm_start":
        print(f"| model call #{event.get('iteration')} with {event.get('tool_count')} tools")
    elif event_type == "llm_complete":
        tool_calls = event.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            print(f"| model requested tools: {', '.join(str(item) for item in tool_calls)}")
        else:
            print("| model returned final text")
    elif event_type == "tool_start":
        print(f"| tool start: {event.get('name')}")
    elif event_type == "tool_complete":
        status = "ok" if event.get("ok") else "failed"
        suffix = f" ({event.get('error')})" if event.get("error") else ""
        print(f"| tool done: {event.get('name')} [{status}]{suffix}")


def handle_config_command(args: argparse.Namespace) -> int:
    if args.config_command is None:
        args.config_command = "show"

    if args.config_command == "init":
        path = write_default_config_if_missing()
        print(f"Config ready: {path}")
        return 0

    if args.config_command == "show":
        print(format_config(load_config()), end="")
        return 0

    print("Missing config command. Use: longrun config init|show")
    return 2


def handle_todo_command(args: argparse.Namespace) -> int:
    command = args.todo_command or "list"
    if command == "add":
        item = add_todo(" ".join(args.title))
        print(f"Added todo {item.id}: {item.title}")
        print(f"Store: {todo_path()}")
        return 0
    if command == "list":
        items = list_todos()
        if not items:
            print("No todos yet.")
            return 0
        for item in items:
            mark = "x" if item.done else " "
            print(f"[{mark}] {item.id} {item.title}")
        print(f"Store: {todo_path()}")
        return 0
    if command == "done":
        try:
            item = complete_todo(args.id)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Completed todo {item.id}: {item.title}")
        print(f"Store: {todo_path()}")
        return 0
    if command == "clear":
        removed = clear_todos()
        print(f"Cleared {removed} todo(s).")
        print(f"Store: {todo_path()}")
        return 0
    print("Missing todo command. Use: longrun todo add|list|done|clear")
    return 2


def handle_context_command(args: argparse.Namespace) -> int:
    config = load_config()
    model = str(config["model"])

    if args.context_command == "show":
        if get_session(args.session_id) is None:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            return 1
        info = inspect_session_context(
            session_id=args.session_id,
            history=list_messages(args.session_id),
            config=config,
            model=model,
        )
        for key, value in info.items():
            print(f"{key}: {value}")
        return 0

    if args.context_command == "compress":
        if get_session(args.session_id) is None:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            return 1
        result = manual_compress_session(
            session_id=args.session_id,
            history=list_messages(args.session_id),
            config=config,
            model=model,
        )
        print(f"compressed: {result.compressed}")
        print(f"estimated_tokens_before: {result.estimated_tokens_before}")
        print(f"estimated_tokens_after: {result.estimated_tokens_after}")
        if result.summary:
            print("summary:")
            print(result.summary)
        return 0

    print("Missing context command. Use: longrun context show|compress")
    return 2


def handle_file_command(args: argparse.Namespace) -> int:
    if args.file_command == "read":
        result = execute_tool_call(
            "file_read",
            {"path": args.path, "offset": args.offset, "limit": args.limit},
        )
        print(result.to_json())
        return 0 if result.ok else 1

    if args.file_command == "write":
        result = execute_tool_call(
            "file_write",
            {"path": args.path, "content": args.content},
        )
        print(result.to_json())
        return 0 if result.ok else 1

    if args.file_command == "patch":
        result = execute_tool_call(
            "file_patch",
            {"path": args.path, "old": args.old, "new": args.new},
        )
        print(result.to_json())
        return 0 if result.ok else 1

    if args.file_command == "search":
        result = execute_tool_call(
            "file_search",
            {
                "pattern": args.pattern,
                "path": args.path,
                "target": args.target,
                "limit": args.limit,
            },
        )
        print(result.to_json())
        return 0 if result.ok else 1

    print("Missing file command. Use: longrun file read|write|patch|search")
    return 2


def handle_model_command(args: argparse.Namespace) -> int:
    config = load_config()
    if args.model_command is None:
        args.model_command = "show"

    if args.model_command == "show":
        print(f"Provider: {config['provider']}")
        print(f"Model: {config['model']}")
        return 0

    if args.model_command == "set":
        set_config_value(config, "model", args.model)
        if args.provider:
            set_config_value(config, "provider", args.provider)
        path = save_config(config)
        print(f"Model config saved: {path}")
        print(f"Provider: {config['provider']}")
        print(f"Model: {config['model']}")
        return 0

    print("Missing model command. Use: longrun model show|set")
    return 2


def handle_reasoning_command(args: argparse.Namespace) -> int:
    config = load_config()
    if args.reasoning_command in {None, "show"}:
        print(f"Reasoning effort: {config.get('reasoning', {}).get('effort', 'medium')}")
        return 0
    if args.reasoning_command == "set":
        set_config_value(config, "reasoning.effort", args.effort)
        path = save_config(config)
        print(f"Reasoning config saved: {path}")
        print(f"Reasoning effort: {args.effort}")
        return 0
    print("Missing reasoning command. Use: longrun reasoning show|set")
    return 2


def handle_verbose_command(args: argparse.Namespace) -> int:
    config = load_config()
    if args.verbose_command in {None, "show"}:
        print(f"Verbose: {bool(config.get('verbose', False))}")
        return 0
    if args.verbose_command in {"on", "off"}:
        value = args.verbose_command == "on"
        set_config_value(config, "verbose", value)
        path = save_config(config)
        print(f"Verbose config saved: {path}")
        print(f"Verbose: {value}")
        return 0
    print("Missing verbose command. Use: longrun verbose show|on|off")
    return 2


def handle_toolsets_command(args: argparse.Namespace) -> int:
    if args.toolsets_command in {None, "list"}:
        by_toolset: dict[str, list[str]] = {}
        for definition in registry.get_definitions():
            by_toolset.setdefault(str(definition["toolset"]), []).append(str(definition["name"]))
        if not by_toolset:
            print("No toolsets registered.")
            return 0
        if _RICH_CONSOLE is not None and Table is not None:
            table = Table(
                title="LongRun toolsets",
                box=box.SIMPLE_HEAVY if box is not None else None,
                show_lines=False,
            )
            table.add_column("status", style="bold")
            table.add_column("toolset", style="cyan", no_wrap=True)
            table.add_column("category", style="magenta")
            table.add_column("tools", justify="right")
            table.add_column("description")
            for item in TOOLSET_CATALOG:
                current_tools = by_toolset.get(item.name, [])
                status = "enabled" if current_tools else item.mvp_status
                style = "green" if current_tools else ("yellow" if item.mvp_status == "staged" else "dim")
                table.add_row(
                    f"[{style}]{status}[/]",
                    item.name,
                    item.category,
                    str(len(current_tools)),
                    item.description,
                )
            for toolset, names in sorted(by_toolset.items()):
                if any(item.name == toolset for item in TOOLSET_CATALOG):
                    continue
                info = classify_toolset(toolset)
                table.add_row("[blue]dynamic[/]", toolset, info.category, str(len(names)), info.description)
            _RICH_CONSOLE.print(table)
            return 0
        for toolset, names in sorted(by_toolset.items()):
            info = classify_toolset(toolset)
            print(f"{toolset} [{info.category}] {info.mvp_status}: {', '.join(sorted(names))}")
        return 0
    print("Missing toolsets command. Use: longrun toolsets list")
    return 2


def handle_debug_command() -> int:
    print_status()
    print("")
    print("Auth:")
    for status in get_provider_statuses():
        configured = "configured" if status.configured else "missing"
        source = f" source={status.source}" if status.source else ""
        detail = f" detail={status.detail}" if status.detail else ""
        print(f"{status.provider}: {configured}{source}{detail}")
    print("")
    print("Tools:")
    print(f"registered: {len(registry.get_definitions())}")
    print("")
    print("Config:")
    print(format_config(load_config()), end="")
    return 0


def handle_reload_command() -> int:
    plugins = reload_plugins(registry)
    mcp_result = reload_mcp_tools()
    print(f"Reloaded {len(plugins)} plugin(s).")
    _print_mcp_reload_result(mcp_result)
    return 0


def handle_reload_skills_command() -> int:
    skills = list_skills(source="all")
    print(f"Skills found: {len(skills)}")
    for skill in skills:
        print(f"{skill['name']} | {skill['source']} | {skill['path']}")
    return 0


def handle_session_alias_command(args: argparse.Namespace) -> int:
    if args.command == "new":
        session = create_session(" ".join(args.title).strip() or None)
        print(f"Created session: {session['id']}")
        print(f"Title: {session['title']}")
        return 0
    if args.command == "resume":
        session = get_session(args.session_id)
        if session is None:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            return 1
        print(f"Session: {session['id']}")
        print(f"Title: {session['title']}")
        print(f"Updated: {session['updated_at']}")
        return 0
    if args.command == "sessions":
        sessions = list_sessions()
        if not sessions:
            print("No sessions.")
            return 0
        for session in sessions:
            print(
                f"{session['id']} | {session['title']} | "
                f"messages={session['message_count']} | updated={session['updated_at']}"
            )
        return 0
    if args.command == "history":
        messages = list_messages(args.session_id)
        if not messages:
            print("No messages.")
            return 0
        for message in messages:
            print(f"[{message['id']}] {message['role']}: {message['content']}")
        return 0
    if args.command == "clear":
        deleted = clear_messages(args.session_id)
        print(f"Cleared {deleted} message(s) from {args.session_id}")
        return 0
    if args.command == "save":
        path = save_transcript(args.session_id, Path(args.output_path))
        print(f"Saved transcript: {path}")
        return 0
    if args.command == "compress":
        config = load_config()
        result = manual_compress_session(
            session_id=args.session_id,
            history=list_messages(args.session_id),
            config=config,
            model=str(config["model"]),
        )
        print(f"compressed: {result.compressed}")
        print(f"estimated_tokens_before: {result.estimated_tokens_before}")
        print(f"estimated_tokens_after: {result.estimated_tokens_after}")
        if result.summary:
            print("summary:")
            print(result.summary)
        return 0
    return 2


def handle_memory_command(args: argparse.Namespace) -> int:
    if args.memory_command == "list":
        result = execute_tool_call("memory_list", {})
        if not result.ok:
            print(result.to_json())
            return 1
        items = result.result["items"]
        if not items:
            print("No memory.")
            return 0
        for item in items:
            print(f"{item['key']}: {item['value']}")
        return 0

    if args.memory_command == "get":
        result = execute_tool_call("memory_get", {"key": args.key})
        print(result.to_json())
        return 0 if result.ok else 1

    if args.memory_command == "set":
        result = execute_tool_call(
            "memory_set",
            {"key": args.key, "value": " ".join(args.value)},
        )
        print(result.to_json())
        return 0 if result.ok else 1

    if args.memory_command == "delete":
        result = execute_tool_call("memory_delete", {"key": args.key})
        print(result.to_json())
        return 0 if result.ok else 1

    if args.memory_command == "clear":
        if not args.yes:
            print("Refusing to clear memory without --yes.", file=sys.stderr)
            return 1
        result = clear_memory()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print("Missing memory command. Use: longrun memory list|get|set|delete|clear")
    return 2


def handle_session_search_command(args: argparse.Namespace) -> int:
    result = execute_tool_call(
        "session_search",
        {"query": " ".join(args.query), "limit": args.limit},
    )
    if not result.ok:
        print(result.to_json())
        return 1
    matches = result.result["matches"]
    if not matches:
        print("No matches.")
        return 0
    for match in matches:
        print(
            f"{match['session_id']} [{match['message_id']}] {match['role']} | "
            f"{match['title']} | {match['snippet']}"
        )
    return 0


def handle_tools_command(args: argparse.Namespace) -> int:
    if args.tools_command == "list":
        definitions = registry.get_definitions()
        if not definitions:
            print("No tools registered.")
            return 0
        if _RICH_CONSOLE is not None and Table is not None:
            for category, group in group_tool_definitions(definitions).items():
                table = Table(
                    title=f"{category} tools",
                    box=box.SIMPLE_HEAVY if box is not None else None,
                    show_lines=False,
                )
                table.add_column("tool", style="cyan", no_wrap=True)
                table.add_column("toolset", style="magenta", no_wrap=True)
                table.add_column("purpose")
                for definition in sorted(group, key=lambda item: str(item["name"])):
                    table.add_row(
                        str(definition["name"]),
                        str(definition["toolset"]),
                        str(definition["description"]),
                    )
                _RICH_CONSOLE.print(table)
            return 0
        for definition in definitions:
            print(f"{definition['name']} | toolset={definition['toolset']} | {definition['description']}")
        return 0

    if args.tools_command == "call":
        try:
            raw_json = Path(args.json_file).read_text(encoding="utf-8-sig") if args.json_file else args.json
            tool_args = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON args: {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"Could not read JSON args file: {exc}", file=sys.stderr)
            return 1
        if not isinstance(tool_args, dict):
            print("Tool args JSON must be an object.", file=sys.stderr)
            return 1
        for item in args.arg:
            if "=" not in item:
                print(f"Invalid --arg value, expected key=value: {item}", file=sys.stderr)
                return 1
            key, value = item.split("=", 1)
            tool_args[key] = value
        result = execute_tool_call(args.name, tool_args, approved=args.approve)
        print(result.to_json())
        return 0 if result.ok else 1

    print("Missing tools command. Use: longrun tools list|call")
    return 2


def handle_terminal_command(args: argparse.Namespace) -> int:
    if args.terminal_command == "run":
        try:
            command = _join_command_args(args.command_args)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        result = execute_tool_call(
            "terminal_run",
            {
                "command": command,
                "cwd": args.cwd,
                "timeout_seconds": args.timeout,
            },
            approved=args.approve,
        )
        print(result.to_json())
        return 0 if result.ok else 1

    print("Missing terminal command. Use: longrun terminal run")
    return 2


def handle_process_command(args: argparse.Namespace) -> int:
    if args.process_command == "start":
        try:
            command = _join_command_args(args.command_args)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        result = execute_tool_call(
            "process_start",
            {
                "command": command,
                "cwd": args.cwd,
            },
            approved=args.approve,
        )
        print(result.to_json())
        return 0 if result.ok else 1

    if args.process_command == "poll":
        result = execute_tool_call("process_poll", {"id": args.id})
        print(result.to_json())
        return 0 if result.ok else 1

    if args.process_command == "kill":
        result = execute_tool_call("process_kill", {"id": args.id})
        print(result.to_json())
        return 0 if result.ok else 1

    if args.process_command == "list":
        result = execute_tool_call("process_list", {})
        print(result.to_json())
        return 0 if result.ok else 1

    print("Missing process command. Use: longrun process start|poll|kill|list")
    return 2


def handle_agents_command(args: argparse.Namespace) -> int:
    if args.agents_command == "list":
        print("Subagent defaults:")
        print("max_depth: 1")
        print("recursive_delegate: false")
        print("memory_mutation: false")
        jobs = list_agent_jobs(limit=10)
        if jobs:
            print("Recent jobs:")
            for job in jobs:
                _print_job(job)
        return 0

    if args.agents_command == "delegate":
        result = execute_tool_call(
            "delegate_task",
            {
                "prompt": " ".join(args.prompt),
                "title": args.title,
                "max_depth": args.max_depth,
            },
        )
        print(result.to_json())
        return 0 if result.ok else 1

    print("Missing agents command. Use: longrun agents list|delegate")
    return 2


def handle_background_command(args: argparse.Namespace) -> int:
    if args.background_command == "start":
        prompt = " ".join(args.prompt)
        job = create_agent_job(prompt, status="starting")
        command = _agent_chat_command(prompt, title=args.title)
        result = execute_tool_call("process_start", {"command": command})
        if not result.ok:
            update_agent_job(str(job["id"]), status="failed", error=result.error)
            print(result.to_json())
            return 1
        process_id = str(result.result["id"])
        job = update_agent_job(str(job["id"]), status="running", process_id=process_id)
        _print_job(job)
        print(f"Process: {process_id}")
        return 0

    if args.background_command == "list":
        jobs = [job for job in list_agent_jobs(limit=50) if job.get("process_id")]
        if not jobs:
            print("No background jobs.")
            return 0
        for job in jobs:
            _print_job(job)
        return 0

    if args.background_command == "show":
        job = _require_job(args.job_id)
        _print_job(job, verbose=True)
        return 0

    if args.background_command == "poll":
        job = _require_job(args.job_id)
        process_id = job.get("process_id")
        if not process_id:
            print(f"Job has no process: {args.job_id}", file=sys.stderr)
            return 1
        result = execute_tool_call("process_poll", {"id": process_id})
        if not result.ok:
            print(result.to_json())
            return 1
        process = result.result
        status = str(process.get("status"))
        if status == "exited":
            exit_code = process.get("exit_code")
            update_agent_job(
                args.job_id,
                status="completed" if exit_code == 0 else "failed",
                result=process.get("stdout"),
                error=process.get("stderr"),
            )
        print(json.dumps(process, indent=2, sort_keys=True))
        return 0

    if args.background_command == "kill":
        job = _require_job(args.job_id)
        process_id = job.get("process_id")
        if not process_id:
            print(f"Job has no process: {args.job_id}", file=sys.stderr)
            return 1
        result = execute_tool_call("process_kill", {"id": process_id})
        update_agent_job(args.job_id, status="killed")
        print(result.to_json())
        return 0 if result.ok else 1

    print("Missing background command. Use: longrun background start|list|show|poll|kill")
    return 2


def handle_queue_command(args: argparse.Namespace) -> int:
    if args.queue_command == "add":
        job = create_agent_job(" ".join(args.prompt), status="queued")
        _print_job(job)
        return 0

    if args.queue_command == "list":
        jobs = list_agent_jobs(limit=50)
        if not jobs:
            print("No queued jobs.")
            return 0
        for job in jobs:
            _print_job(job)
        return 0

    if args.queue_command == "show":
        _print_job(_require_job(args.job_id), verbose=True)
        return 0

    if args.queue_command == "claim":
        job = claim_next_agent_job()
        if job is None:
            print("No queued jobs to claim.")
            return 0
        _print_job(job, verbose=True)
        return 0

    if args.queue_command == "complete":
        job = update_agent_job(args.job_id, status="completed", result=" ".join(args.result), error=None)
        _print_job(job, verbose=True)
        return 0

    if args.queue_command == "fail":
        job = update_agent_job(args.job_id, status="failed", error=" ".join(args.reason))
        _print_job(job, verbose=True)
        return 0

    print("Missing queue command. Use: longrun queue add|list|show|claim|complete|fail")
    return 2


def handle_cron_command(args: argparse.Namespace) -> int:
    if args.cron_command == "add":
        job = cron_jobs.create_job(
            name=args.name,
            prompt=" ".join(args.prompt),
            schedule=args.schedule,
            repeat=args.repeat,
            skills=args.skills,
            enabled_toolsets=args.enabled_toolsets,
            model=args.model,
            provider=args.provider,
        )
        _print_cron_job(job, verbose=True)
        return 0

    if args.cron_command == "list":
        jobs = cron_jobs.list_jobs(include_disabled=args.all)
        if not jobs:
            print("No cron jobs.")
            return 0
        for job in jobs:
            _print_cron_job(job)
        return 0

    if args.cron_command == "show":
        job = cron_jobs.get_job(args.job_id)
        if not job:
            print(f"Cron job not found: {args.job_id}", file=sys.stderr)
            return 1
        _print_cron_job(job, verbose=True)
        return 0

    if args.cron_command == "pause":
        job = cron_jobs.pause_job(args.job_id, reason=args.reason)
        if not job:
            print(f"Cron job not found: {args.job_id}", file=sys.stderr)
            return 1
        _print_cron_job(job, verbose=True)
        return 0

    if args.cron_command == "resume":
        job = cron_jobs.resume_job(args.job_id)
        if not job:
            print(f"Cron job not found: {args.job_id}", file=sys.stderr)
            return 1
        _print_cron_job(job, verbose=True)
        return 0

    if args.cron_command == "remove":
        if not cron_jobs.remove_job(args.job_id):
            print(f"Cron job not found: {args.job_id}", file=sys.stderr)
            return 1
        print(f"Removed cron job: {args.job_id}")
        return 0

    if args.cron_command == "trigger":
        job = cron_jobs.trigger_job(args.job_id)
        if not job:
            print(f"Cron job not found: {args.job_id}", file=sys.stderr)
            return 1
        _print_cron_job(job, verbose=True)
        return 0

    if args.cron_command == "preview":
        result = preview_job(args.job_id)
        if not result:
            print(f"Cron job not found: {args.job_id}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.cron_command == "run":
        result = trigger_and_run(args.job_id)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("success") else 1

    if args.cron_command == "tick":
        result = cron_tick()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if all(item.get("success") for item in result.get("results", [])) else 1

    print("Missing cron command. Use: longrun cron add|list|show|pause|resume|remove|trigger|run|preview|tick")
    return 2


def handle_long_run_command(args: argparse.Namespace) -> int:
    board = getattr(args, "board", long_run_db.DEFAULT_BOARD)

    if args.long_run_command == "init":
        print(json.dumps(long_run_db.init_board(board), indent=2, sort_keys=True))
        return 0

    if args.long_run_command == "create":
        task = long_run_db.create_task(
            " ".join(args.title),
            description=args.description,
            assignee=args.assignee,
            board=board,
        )
        _print_long_run_task(task, verbose=True)
        return 0

    if args.long_run_command == "list":
        tasks = long_run_db.list_tasks(board=board, status=args.status)
        if not tasks:
            print("No Long-Run tasks.")
            return 0
        for task in tasks:
            _print_long_run_task(task)
        return 0

    if args.long_run_command == "show":
        task = _require_long_run_task(args.task_id, board=board)
        _print_long_run_task(task, verbose=True)
        comments = long_run_db.task_comments(args.task_id, board=board)
        if comments:
            print("comments:")
            for comment in comments:
                print(f"[{comment['id']}] {comment['author']}: {comment['body']}")
        return 0

    if args.long_run_command == "assign":
        _print_long_run_task(long_run_db.assign_task(args.task_id, args.assignee, board=board), verbose=True)
        return 0

    if args.long_run_command == "claim":
        task = long_run_db.claim_next_task(args.worker, board=board)
        if task is None:
            print("No ready Long-Run tasks.")
            return 0
        _print_long_run_task(task, verbose=True)
        return 0

    if args.long_run_command == "complete":
        task = long_run_db.complete_task(args.task_id, " ".join(args.result), board=board)
        _print_long_run_task(task, verbose=True)
        return 0

    if args.long_run_command == "block":
        task = long_run_db.block_task(args.task_id, " ".join(args.reason), board=board)
        _print_long_run_task(task, verbose=True)
        return 0

    if args.long_run_command == "unblock":
        task = long_run_db.unblock_task(args.task_id, board=board)
        _print_long_run_task(task, verbose=True)
        return 0

    if args.long_run_command == "comment":
        comment = long_run_db.comment_task(
            args.task_id,
            " ".join(args.body),
            author=args.author,
            board=board,
        )
        print(json.dumps(comment, indent=2, sort_keys=True))
        return 0

    if args.long_run_command == "dispatch":
        task = long_run_db.claim_next_task(args.worker, board=board)
        if task is None:
            print("No ready Long-Run tasks to dispatch.")
            return 0
        _print_long_run_task(task, verbose=True)
        return 0

    if args.long_run_command == "tail":
        print(json.dumps(long_run_db.task_log(args.task_id, board=board), indent=2, sort_keys=True))
        return 0

    if args.long_run_command == "stats":
        print(json.dumps(long_run_db.stats(board=board), indent=2, sort_keys=True))
        return 0

    if args.long_run_command == "runs":
        runs = long_run_db.list_runs(board=board)
        if not runs:
            print("No Long-Run runs.")
            return 0
        for run in runs:
            print(f"{run['id']} | task={run['task_id']} | worker={run['worker']} | {run['status']}")
        return 0

    if args.long_run_command == "heartbeat":
        print(
            json.dumps(
                long_run_db.heartbeat(
                    args.worker,
                    task_id=args.task_id,
                    status=args.status,
                    board=board,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print("Missing long-run command. Use: longrun long-run init|create|list|show|assign|claim|complete|block|unblock|comment|dispatch|tail|stats|runs|heartbeat")
    return 2


def handle_checkpoints_command(args: argparse.Namespace) -> int:
    for checkpoint in list_checkpoints():
        print(
            f"{checkpoint['id']} | {checkpoint['path']} | "
            f"existed={checkpoint['existed']} | reason={checkpoint['reason']} | "
            f"created={checkpoint['created_at']}"
        )
    return 0


def handle_rollback_command(args: argparse.Namespace) -> int:
    try:
        result = rollback_checkpoint(args.checkpoint_id)
    except (KeyError, ValueError) as exc:
        print(f"Rollback failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def handle_skills_command(args: argparse.Namespace) -> int:
    if args.skills_command == "list":
        skills = list_skills(source=args.source)
        if not skills:
            print("No skills found.")
            return 0
        for skill in skills:
            print(f"{skill['name']} | {skill['source']} | {skill['path']}")
        return 0

    if args.skills_command == "view":
        try:
            skill = read_skill(args.name, source=args.source)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Skill read failed: {exc}", file=sys.stderr)
            return 1
        print(f"# {skill['name']}")
        print(f"Path: {skill['path']}")
        print("")
        print(skill["content"], end="" if str(skill["content"]).endswith("\n") else "\n")
        return 0

    if args.skills_command == "import-bundled":
        result = import_bundled_skills(overwrite=args.overwrite)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print("Missing skills command. Use: longrun skills list|view|import-bundled")
    return 2


def handle_plugins_command(args: argparse.Namespace) -> int:
    if args.plugins_command == "list":
        plugins = list_plugins(registry=registry)
        if not plugins:
            print("No plugins found.")
            return 0
        for plugin in plugins:
            status = "loaded" if plugin.loaded else "not-loaded"
            enabled = "enabled" if plugin.enabled else "disabled"
            error = f" error={plugin.error}" if plugin.error else ""
            print(f"{plugin.name} | {enabled} | {status} | {plugin.path}{error}")
        return 0

    if args.plugins_command == "hooks":
        hooks = hook_manager.list_hooks()
        if not hooks:
            print("No hooks registered.")
            return 0
        for hook in hooks:
            print(f"{hook['name']} | {hook['source']}")
        return 0

    if args.plugins_command == "reload":
        plugins = reload_plugins(registry)
        print(f"Reloaded {len(plugins)} plugin(s).")
        for plugin in plugins:
            status = "loaded" if plugin.loaded else "not-loaded"
            error = f" error={plugin.error}" if plugin.error else ""
            print(f"{plugin.name} | {status}{error}")
        return 0

    if args.plugins_command == "enable":
        path = set_plugin_enabled(args.name, True)
        print(f"Enabled plugin {args.name} in {path}")
        return 0

    if args.plugins_command == "disable":
        path = set_plugin_enabled(args.name, False)
        print(f"Disabled plugin {args.name} in {path}")
        return 0

    print("Missing plugins command. Use: longrun plugins list|hooks|reload|enable|disable")
    return 2


def handle_mcp_command(args: argparse.Namespace) -> int:
    if args.mcp_command == "list":
        servers = list_mcp_servers()
        if not servers:
            print("No MCP servers configured.")
            return 0
        for server in servers:
            extra_args = " ".join(server.args)
            print(f"{server.name} | stdio | {server.command} {extra_args}".rstrip())
        return 0

    if args.mcp_command == "add-stdio":
        path = add_stdio_server(args.name, args.server_command, list(args.arg))
        print(f"MCP server saved: {path}")
        print(f"Reload tools with: longrun mcp reload")
        return 0

    if args.mcp_command == "remove":
        print(json.dumps(remove_mcp_server(args.name), indent=2, sort_keys=True))
        return 0

    if args.mcp_command == "reload":
        result = reload_mcp_tools()
        _print_mcp_reload_result(result)
        return 0

    if args.mcp_command == "tools":
        cache = cached_mcp_tools()
        tools = cache.get("tools", [])
        errors = cache.get("errors", {})
        if not tools:
            print("No cached MCP tools.")
        for tool in tools:
            print(f"{tool['registry_name']} | {tool['server']}::{tool['name']} | {tool['description']}")
        if errors:
            print("Errors:")
            for name, error in errors.items():
                print(f"{name}: {error}")
        return 0

    print("Missing mcp command. Use: longrun mcp list|add-stdio|remove|reload|tools")
    return 2


def _print_mcp_reload_result(result: dict[str, Any]) -> None:
    tools = result.get("tools", [])
    errors = result.get("errors", {})
    print(f"Discovered {len(tools)} MCP tool(s).")
    for tool in tools:
        print(f"{tool['registry_name']} | {tool['server']}::{tool['name']}")
    if errors:
        print("Errors:")
        for name, error in errors.items():
            print(f"{name}: {error}")


def handle_session_command(args: argparse.Namespace) -> int:
    if args.session_command == "new":
        title = " ".join(args.title).strip() or None
        session = create_session(title)
        print(f"Created session: {session['id']}")
        print(f"Title: {session['title']}")
        return 0

    if args.session_command == "list":
        sessions = list_sessions()
        if not sessions:
            print("No sessions.")
            return 0
        for session in sessions:
            print(
                f"{session['id']} | {session['title']} | "
                f"messages={session['message_count']} | updated={session['updated_at']}"
            )
        return 0

    if args.session_command == "history":
        messages = list_messages(args.session_id)
        if not messages:
            print("No messages.")
            return 0
        for message in messages:
            print(f"[{message['id']}] {message['role']}: {message['content']}")
        return 0

    if args.session_command == "add-message":
        content = " ".join(args.content)
        message = add_message(args.session_id, args.role, content)
        print(f"Added message {message['id']} to {message['session_id']}")
        return 0

    if args.session_command == "clear":
        deleted = clear_messages(args.session_id)
        print(f"Cleared {deleted} message(s) from {args.session_id}")
        return 0

    if args.session_command == "save":
        path = save_transcript(args.session_id, Path(args.output_path))
        print(f"Saved transcript: {path}")
        return 0

    print("Missing session command. Use: longrun session new|list|history|add-message|clear|save")
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"LongRun Agent {__version__}")
        return 0

    if args.command is None:
        from longrun_agent.cli.interactive import run_interactive

        return run_interactive()

    if args.command == "version":
        print(f"LongRun Agent {__version__}")
        return 0

    if args.command == "setup":
        return handle_setup_command(args)

    if args.command == "logout":
        return handle_logout_command(args)

    if args.command == "hooks":
        return handle_hooks_command()

    if args.command == "doctor":
        return handle_doctor_command()

    if args.command == "init":
        return handle_init_command(args)

    if args.command == "run":
        return handle_run_command(args)

    if args.command == "plan":
        return handle_plan_command(args)

    if args.command == "status":
        print_status()
        return 0

    if args.command == "debug":
        return handle_debug_command()

    if args.command in {"quit", "stop"}:
        print("No interactive command is running.")
        return 0

    if args.command == "reload":
        return handle_reload_command()

    if args.command == "reload-mcp":
        _print_mcp_reload_result(reload_mcp_tools())
        return 0

    if args.command == "reload-skills":
        return handle_reload_skills_command()

    if args.command == "models":
        return handle_models_command(args)

    if args.command == "workers":
        return handle_workers_command(args)

    if args.command == "logs":
        return handle_logs_command(args)

    if args.command in {"new", "resume", "sessions", "history", "clear", "save", "compress"}:
        return handle_session_alias_command(args)

    if args.command == "auth":
        return handle_auth_command(args)

    if args.command == "chat":
        return handle_chat_command(args)

    if args.command == "config":
        return handle_config_command(args)

    if args.command == "todo":
        return handle_todo_command(args)

    if args.command == "context":
        return handle_context_command(args)

    if args.command == "file":
        return handle_file_command(args)

    if args.command == "model":
        return handle_model_command(args)

    if args.command == "reasoning":
        return handle_reasoning_command(args)

    if args.command == "verbose":
        return handle_verbose_command(args)

    if args.command == "memory":
        return handle_memory_command(args)

    if args.command == "session-search":
        return handle_session_search_command(args)

    if args.command == "terminal":
        return handle_terminal_command(args)

    if args.command == "process":
        return handle_process_command(args)

    if args.command == "agents":
        return handle_agents_command(args)

    if args.command == "background":
        return handle_background_command(args)

    if args.command == "queue":
        return handle_queue_command(args)

    if args.command == "cron":
        return handle_cron_command(args)

    if args.command in {"long-run", "kanban"}:
        return handle_long_run_command(args)

    if args.command == "checkpoints":
        return handle_checkpoints_command(args)

    if args.command == "rollback":
        return handle_rollback_command(args)

    if args.command == "skills":
        return handle_skills_command(args)

    if args.command == "plugins":
        return handle_plugins_command(args)

    if args.command == "mcp":
        return handle_mcp_command(args)

    if args.command == "tools":
        return handle_tools_command(args)

    if args.command == "toolsets":
        return handle_toolsets_command(args)

    if args.command == "session":
        return handle_session_command(args)

    parser.print_help()
    return 0


def _join_command_args(parts: list[str]) -> str:
    command_parts = list(parts)
    if command_parts and command_parts[0] == "--":
        command_parts = command_parts[1:]
    command = " ".join(command_parts).strip()
    if not command:
        raise ValueError("Command cannot be empty")
    return command


def _agent_chat_command(prompt: str, *, title: str | None = None) -> str:
    parts = [sys.executable, "-m", "longrun_agent.cli.main", "chat", prompt]
    if title:
        parts.extend(["--title", title])
    return subprocess.list2cmdline(parts)


def _require_job(job_id: str) -> dict[str, Any]:
    job = get_agent_job(job_id)
    if job is None:
        raise ValueError(f"Agent job not found: {job_id}")
    return job


def _print_job(job: dict[str, Any], *, verbose: bool = False) -> None:
    print(
        f"{job['id']} | {job['status']} | process={job.get('process_id') or '-'} | "
        f"updated={job['updated_at']}"
    )
    if verbose:
        print(f"prompt: {job['prompt']}")
        if job.get("result"):
            print(f"result: {job['result']}")
        if job.get("error"):
            print(f"error: {job['error']}")


def _print_cron_job(job: dict[str, Any], *, verbose: bool = False) -> None:
    print(
        f"{job['id']} | {job.get('state', '-')} | {job.get('schedule_display', '-')} | "
        f"next={job.get('next_run_at') or '-'} | {job.get('name', '-')}"
    )
    if verbose:
        print(f"prompt: {job.get('prompt')}")
        if job.get("skills"):
            print(f"skills: {', '.join(job['skills'])}")
        if job.get("enabled_toolsets"):
            print(f"toolsets: {', '.join(job['enabled_toolsets'])}")
        if job.get("last_session_id"):
            print(f"last_session: {job['last_session_id']}")
        if job.get("last_status"):
            print(f"last_status: {job['last_status']}")
        if job.get("last_error"):
            print(f"last_error: {job['last_error']}")


def _require_long_run_task(task_id: str, *, board: str) -> dict[str, Any]:
    task = long_run_db.get_task(task_id, board=board)
    if task is None:
        raise ValueError(f"Long-Run task not found: {task_id}")
    return task


def _print_long_run_task(task: dict[str, Any], *, verbose: bool = False) -> None:
    print(
        f"{task['id']} | {task['status']} | assignee={task.get('assignee') or '-'} | "
        f"claimed_by={task.get('claimed_by') or '-'} | {task['title']}"
    )
    if verbose:
        if task.get("description"):
            print(f"description: {task['description']}")
        if task.get("block_reason"):
            print(f"block_reason: {task['block_reason']}")
        if task.get("result"):
            print(f"result: {task['result']}")


if __name__ == "__main__":
    raise SystemExit(main())
