"""Command-line entry point for LongRun Agent."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from longrun_agent import __version__
from longrun_agent.config import (
    config_path,
    ensure_home,
    format_config,
    get_longrun_home,
    load_config,
    write_default_config_if_missing,
)
from longrun_agent.logging import setup_logging
from longrun_agent.state import (
    add_message,
    clear_messages,
    create_session,
    get_state_summary,
    list_messages,
    list_sessions,
    save_transcript,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="longrun", description="LongRun Agent CLI")
    parser.add_argument("--version", action="store_true", help="Print version and exit")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show Stage 0 runtime status")

    config_parser = subparsers.add_parser("config", help="Manage behavior config")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("init", help="Create config.yaml if it is missing")
    config_subparsers.add_parser("show", help="Show merged config")

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

    print(f"LongRun Agent {__version__}")
    print(f"Home: {home}")
    print(f"Config: {config_path()}")
    print(f"State DB: {state['db_path']}")
    print(f"Sessions: {state['sessions']}")
    print(f"Messages: {state['messages']}")
    print(f"Default model: {config['model']}")


def handle_config_command(args: argparse.Namespace) -> int:
    if args.config_command == "init":
        path = write_default_config_if_missing()
        print(f"Config ready: {path}")
        return 0

    if args.config_command == "show":
        print(format_config(load_config()), end="")
        return 0

    print("Missing config command. Use: longrun config init|show")
    return 2


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

    if args.command == "status":
        print_status()
        return 0

    if args.command == "config":
        return handle_config_command(args)

    if args.command == "session":
        return handle_session_command(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
