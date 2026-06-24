"""Tool registration for LongRun Agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Any]
ToolCheck = Callable[[], bool]


@dataclass(frozen=True)
class ToolSpec:
    """One registered model-callable tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    toolset: str = "default"
    check_fn: ToolCheck | None = None

    def available(self) -> bool:
        return self.check_fn() if self.check_fn else True

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "toolset": self.toolset,
        }


class ToolRegistry:
    """Central registry for tool schemas and handlers."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        toolset: str = "default",
        check_fn: ToolCheck | None = None,
    ) -> None:
        if not name:
            raise ValueError("Tool name cannot be empty")
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            toolset=toolset,
            check_fn=check_fn,
        )

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def get_definitions(self, *, include_unavailable: bool = False) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for spec in sorted(self._tools.values(), key=lambda item: item.name):
            if include_unavailable or spec.available():
                definitions.append(spec.definition())
        return definitions

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        spec = self.get(name)
        if not spec.available():
            raise RuntimeError(f"Tool is not available: {name}")
        return spec.handler(args)


registry = ToolRegistry()


def register_diagnostic_tools() -> None:
    """Register Stage 5 diagnostic tools."""

    try:
        registry.register(
            name="diagnostic_echo",
            description="Return the provided text. Used to prove the tool path.",
            toolset="diagnostic",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to echo."},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=lambda args: {"text": str(args.get("text", ""))},
        )
    except ValueError:
        pass


register_diagnostic_tools()

from longrun_agent.tools.processes import register_process_tools
from longrun_agent.tools.clarify import register_clarify_tools
from longrun_agent.tools.code_execution import register_code_execution_tools
from longrun_agent.tools.cronjob import register_cronjob_tools
from longrun_agent.tools.delegate import register_delegate_tools
from longrun_agent.tools.files import register_file_tools
from longrun_agent.tools.long_run import register_long_run_tools
from longrun_agent.tools.memory import register_memory_tools
from longrun_agent.tools.session_search import register_session_search_tools
from longrun_agent.tools.skills import register_skill_tools
from longrun_agent.tools.terminal import register_terminal_tools
from longrun_agent.tools.todo import register_todo_tools

register_file_tools(registry)
register_skill_tools(registry)
register_todo_tools(registry)
register_clarify_tools(registry)
register_code_execution_tools(registry)
register_cronjob_tools(registry)
register_memory_tools(registry)
register_session_search_tools(registry)
register_delegate_tools(registry)
register_long_run_tools(registry)
register_terminal_tools(registry)
register_process_tools(registry)

try:
    from longrun_agent.plugins.loader import load_enabled_plugins

    load_enabled_plugins(registry)
except Exception:
    pass

try:
    from longrun_agent.mcp.client import register_cached_mcp_tools

    register_cached_mcp_tools(registry)
except Exception:
    pass
