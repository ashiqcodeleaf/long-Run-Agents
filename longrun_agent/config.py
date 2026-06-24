"""Configuration and home-directory helpers for LongRun Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "openai-api",
    "model": "gpt-4.1-mini",
    "max_iterations": 90,
    "reasoning": {"effort": "medium"},
    "verbose": False,
    "approvals": {"mode": "default"},
    "openai": {"base_url": "https://api.openai.com/v1"},
    "codex": {"base_url": "https://chatgpt.com/backend-api/codex"},
    "context": {
        "max_tokens": 128000,
        "compression_threshold_tokens": 96000,
        "tail_messages": 12,
        "context_file_max_chars": 12000,
    },
}

DEFAULT_CODEX_MODEL = "gpt-5.4-mini"


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
        home / "file-state",
        home / "long-run",
        home / "long-run" / "boards",
        home / "cron",
        home / "cron" / "output",
        home / "processes",
        home / "processes" / "logs",
    ):
        child.mkdir(parents=True, exist_ok=True)
    return home


def config_path() -> Path:
    return get_longrun_home() / "config.yaml"


def env_path() -> Path:
    return get_longrun_home() / ".env"


def auth_path() -> Path:
    return get_longrun_home() / "auth.json"


def processes_path() -> Path:
    return get_longrun_home() / "processes" / "processes.json"


def process_logs_dir() -> Path:
    return get_longrun_home() / "processes" / "logs"


def file_state_path() -> Path:
    return get_longrun_home() / "file-state" / "file_state.json"


def checkpoints_dir() -> Path:
    return get_longrun_home() / "checkpoints"


def checkpoints_manifest_path() -> Path:
    return checkpoints_dir() / "checkpoints.json"


def state_db_path() -> Path:
    return get_longrun_home() / "state.db"


def memory_path() -> Path:
    return get_longrun_home() / "memory.json"


def plugin_state_path() -> Path:
    return get_longrun_home() / "plugins" / "plugins.json"


def mcp_servers_path() -> Path:
    return get_longrun_home() / "mcp" / "servers.json"


def mcp_tools_cache_path() -> Path:
    return get_longrun_home() / "mcp" / "tools.json"


def long_run_boards_dir() -> Path:
    return get_longrun_home() / "long-run" / "boards"


def cron_dir() -> Path:
    return get_longrun_home() / "cron"


def cron_jobs_path() -> Path:
    return cron_dir() / "jobs.json"


def cron_output_dir() -> Path:
    return cron_dir() / "output"


def load_config() -> dict[str, Any]:
    """Load config from disk and merge it over defaults."""

    path = config_path()
    if not path.exists():
        return merge_config(DEFAULT_CONFIG, {})
    return merge_config(DEFAULT_CONFIG, _parse_simple_yaml(path.read_text(encoding="utf-8")))


def write_default_config_if_missing() -> Path:
    """Create `config.yaml` with defaults if it is missing."""

    ensure_home()
    path = config_path()
    if not path.exists():
        path.write_text(format_config(DEFAULT_CONFIG), encoding="utf-8")
    return path


def save_config(config: dict[str, Any]) -> Path:
    """Persist config to `config.yaml`."""

    ensure_home()
    path = config_path()
    path.write_text(format_config(config), encoding="utf-8")
    return path


def merge_config(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge user config over defaults."""

    merged: dict[str, Any] = {}
    for key, value in defaults.items():
        if isinstance(value, dict):
            merged[key] = merge_config(value, {})
        else:
            merged[key] = value

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_config_value(config: dict[str, Any], dotted_key: str) -> Any:
    """Read a nested config value using dot notation."""

    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted_key)
        current = current[part]
    return current


def set_config_value(config: dict[str, Any], dotted_key: str, value: Any) -> dict[str, Any]:
    """Set a nested config value using dot notation."""

    current = config
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(f"Cannot set nested key under non-object config value: {part}")
        current = child
    current[parts[-1]] = value
    return config


def format_config(config: dict[str, Any]) -> str:
    """Render the small Stage 1 config shape as YAML."""

    lines = _format_yaml_mapping(config)
    return "\n".join(lines) + "\n"


def _format_yaml_mapping(values: dict[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in values.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(_format_yaml_mapping(value, indent + 2))
        else:
            lines.append(f"{prefix}{key}: {_format_scalar(value)}")
    return lines


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    text = str(value)
    if not text or any(char in text for char in ":#\n"):
        return repr(text)
    return text


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the limited YAML shape emitted by `format_config`.

    This is intentionally small for Stage 1. It supports nested mappings with
    two-space indentation and scalar string/int/bool values.
    """

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            raise ValueError(f"Invalid config line: {raw_line}")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if raw_value == "":
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
        else:
            current[key] = _parse_scalar(raw_value)

    return root


def _parse_scalar(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value.strip("\"'")
