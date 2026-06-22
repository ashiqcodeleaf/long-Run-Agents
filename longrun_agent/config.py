"""Configuration and home-directory helpers for LongRun Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "model": "gpt-4.1-mini",
    "max_iterations": 90,
    "approvals": {"mode": "default"},
}


def get_longrun_home() -> Path:
    """Return the LongRun Agent home directory."""

    override = os.environ.get("LONGRUN_AGENT_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".longrun-agent"


def ensure_home() -> Path:
    """Create the basic home layout needed for Stage 0."""

    home = get_longrun_home()
    for child in (
        home,
        home / "logs",
        home / "skills",
        home / "plugins",
        home / "mcp",
        home / "checkpoints",
        home / "long-run",
    ):
        child.mkdir(parents=True, exist_ok=True)
    return home


def config_path() -> Path:
    return get_longrun_home() / "config.yaml"


def env_path() -> Path:
    return get_longrun_home() / ".env"


def state_db_path() -> Path:
    return get_longrun_home() / "state.db"


def load_config() -> dict[str, Any]:
    """Return default config for Stage 0.

    Real YAML parsing is intentionally delayed to Stage 1 so this stage remains
    only the runnable skeleton.
    """

    return dict(DEFAULT_CONFIG)
