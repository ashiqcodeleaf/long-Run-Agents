"""Deterministic hook lifecycle for LongRun Agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

HookHandler = Callable[[dict[str, Any]], Any]

HOOK_NAMES = (
    "session_start",
    "turn_start",
    "pre_llm_call",
    "post_llm_call",
    "pre_tool_call",
    "post_tool_call",
    "pre_approval_request",
    "post_approval_response",
    "subagent_start",
    "subagent_stop",
)


@dataclass(frozen=True)
class HookRegistration:
    """One registered hook callback."""

    name: str
    source: str
    handler: HookHandler


@dataclass(frozen=True)
class HookResult:
    """Result from one hook invocation."""

    name: str
    source: str
    ok: bool
    error: str | None = None


class HookManager:
    """In-process ordered hook registry."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookRegistration]] = {name: [] for name in HOOK_NAMES}

    def register(self, name: str, handler: HookHandler, *, source: str) -> None:
        if name not in HOOK_NAMES:
            raise ValueError(f"Unknown hook: {name}")
        self._hooks[name].append(HookRegistration(name=name, source=source, handler=handler))

    def run(self, name: str, payload: dict[str, Any]) -> list[HookResult]:
        if name not in HOOK_NAMES:
            raise ValueError(f"Unknown hook: {name}")
        results: list[HookResult] = []
        for registration in self._hooks[name]:
            try:
                registration.handler(payload)
            except Exception as exc:
                results.append(
                    HookResult(
                        name=name,
                        source=registration.source,
                        ok=False,
                        error=str(exc),
                    )
                )
                continue
            results.append(HookResult(name=name, source=registration.source, ok=True))
        return results

    def list_hooks(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for name in HOOK_NAMES:
            for registration in self._hooks[name]:
                rows.append({"name": name, "source": registration.source})
        return rows


hook_manager = HookManager()


def run_hooks(name: str, payload: dict[str, Any]) -> list[HookResult]:
    """Run registered hooks for one lifecycle event."""

    return hook_manager.run(name, payload)
