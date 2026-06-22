"""Logging setup for LongRun Agent."""

from __future__ import annotations

import logging
from pathlib import Path

from longrun_agent.config import ensure_home


def setup_logging() -> Path:
    """Configure file logging and return the logs directory."""

    home = ensure_home()
    logs_dir = home / "logs"
    agent_log = logs_dir / "agent.log"
    errors_log = logs_dir / "errors.log"

    root = logging.getLogger("longrun_agent")
    root.setLevel(logging.INFO)
    root.handlers.clear()

    info_handler = logging.FileHandler(agent_log, encoding="utf-8")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    error_handler = logging.FileHandler(errors_log, encoding="utf-8")
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    root.addHandler(info_handler)
    root.addHandler(error_handler)
    root.info("LongRun Agent logging initialized")

    return logs_dir
