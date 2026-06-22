"""Command-line entry point for LongRun Agent."""

from __future__ import annotations

import argparse
from typing import Sequence

from longrun_agent import __version__
from longrun_agent.config import ensure_home, get_longrun_home, load_config
from longrun_agent.logging import setup_logging
from longrun_agent.state import get_state_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="longrun", description="LongRun Agent CLI")
    parser.add_argument("--version", action="store_true", help="Print version and exit")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show Stage 0 runtime status")
    return parser


def print_status() -> None:
    home = ensure_home()
    setup_logging()
    config = load_config()
    state = get_state_summary()

    print(f"LongRun Agent {__version__}")
    print(f"Home: {home}")
    print(f"Config: {get_longrun_home() / 'config.yaml'}")
    print(f"State DB: {state['db_path']}")
    print(f"Sessions: {state['sessions']}")
    print(f"Messages: {state['messages']}")
    print(f"Default model: {config['model']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"LongRun Agent {__version__}")
        return 0

    if args.command == "status":
        print_status()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
