"""Resolve MYAGENT_HOME for standalone skill scripts.

Skill scripts may run outside the MyAgent process (e.g. system Python,
nix env, CI) where ``myagent_constants`` is not importable.  This module
provides the same ``get_myagent_home()`` and ``display_myagent_home()``
contracts as ``myagent_constants`` without requiring it on ``sys.path``.

When ``myagent_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``myagent_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``MYAGENT_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from myagent_constants import display_myagent_home as display_myagent_home
    from myagent_constants import get_myagent_home as get_myagent_home
except (ModuleNotFoundError, ImportError):

    def get_myagent_home() -> Path:
        """Return the MyAgent home directory (default: ~/.myagent).

        Mirrors ``myagent_constants.get_myagent_home()``."""
        val = os.environ.get("MYAGENT_HOME", "").strip()
        return Path(val) if val else Path.home() / ".myagent"

    def display_myagent_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``myagent_constants.display_myagent_home()``."""
        home = get_myagent_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
