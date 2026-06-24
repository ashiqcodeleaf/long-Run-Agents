"""Local plugin discovery and loading."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from longrun_agent.config import ensure_home, get_longrun_home, plugin_state_path
from longrun_agent.hooks import hook_manager


@dataclass(frozen=True)
class PluginInfo:
    """Plugin metadata shown by the CLI."""

    name: str
    path: str
    enabled: bool
    loaded: bool
    description: str
    error: str | None = None


class PluginContext:
    """Narrow API exposed to local plugins."""

    def __init__(self, *, plugin_name: str, registry: Any) -> None:
        self.plugin_name = plugin_name
        self._registry = registry

    def register_tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Any,
        toolset: str | None = None,
    ) -> None:
        try:
            self._registry.register(
                name=name,
                description=description,
                parameters=parameters,
                handler=handler,
                toolset=toolset or f"plugin:{self.plugin_name}",
            )
        except ValueError as exc:
            if "already registered" not in str(exc):
                raise

    def register_hook(self, name: str, handler: Any) -> None:
        hook_manager.register(name, handler, source=f"plugin:{self.plugin_name}")


_LOADED = False
_LOADED_PLUGINS: dict[str, PluginInfo] = {}


def plugins_dir() -> Path:
    return get_longrun_home() / "plugins"


def list_plugins(*, registry: Any | None = None, load: bool = True) -> list[PluginInfo]:
    """List local plugins and optionally load enabled ones."""

    if load and registry is not None:
        load_enabled_plugins(registry)

    state = _load_state()
    rows: list[PluginInfo] = []
    for plugin_path in _plugin_paths():
        manifest = _read_manifest(plugin_path)
        name = str(manifest.get("name") or plugin_path.name)
        enabled = bool(state["enabled"].get(name, manifest.get("enabled", True)))
        loaded = name in _LOADED_PLUGINS and _LOADED_PLUGINS[name].loaded
        error = _LOADED_PLUGINS.get(name).error if name in _LOADED_PLUGINS else None
        rows.append(
            PluginInfo(
                name=name,
                path=str(plugin_path),
                enabled=enabled,
                loaded=loaded,
                description=str(manifest.get("description", "")),
                error=error,
            )
        )
    return sorted(rows, key=lambda item: item.name)


def load_enabled_plugins(registry: Any) -> list[PluginInfo]:
    """Load enabled local plugins once per process."""

    global _LOADED
    if _LOADED:
        return list(_LOADED_PLUGINS.values())
    _LOADED = True

    state = _load_state()
    for plugin_path in _plugin_paths():
        manifest = _read_manifest(plugin_path)
        name = str(manifest.get("name") or plugin_path.name)
        enabled = bool(state["enabled"].get(name, manifest.get("enabled", True)))
        if not enabled:
            _LOADED_PLUGINS[name] = PluginInfo(
                name=name,
                path=str(plugin_path),
                enabled=False,
                loaded=False,
                description=str(manifest.get("description", "")),
            )
            continue
        _LOADED_PLUGINS[name] = _load_one_plugin(plugin_path, name, manifest, registry)
    return list(_LOADED_PLUGINS.values())


def set_plugin_enabled(name: str, enabled: bool) -> Path:
    """Persist plugin enable/disable state."""

    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Plugin name cannot be empty")
    state = _load_state()
    state["enabled"][clean_name] = enabled
    return _save_state(state)


def reload_plugins(registry: Any) -> list[PluginInfo]:
    """Load plugins in the current process if they have not already loaded."""

    global _LOADED
    _LOADED = False
    _LOADED_PLUGINS.clear()
    return load_enabled_plugins(registry)


def _load_one_plugin(
    plugin_path: Path,
    name: str,
    manifest: dict[str, Any],
    registry: Any,
) -> PluginInfo:
    module_path = plugin_path / "plugin.py"
    description = str(manifest.get("description", ""))
    if not module_path.exists():
        return PluginInfo(
            name=name,
            path=str(plugin_path),
            enabled=True,
            loaded=False,
            description=description,
            error="missing plugin.py",
        )

    try:
        module = _import_plugin_module(module_path, name)
        register = getattr(module, "register", None)
        if not callable(register):
            raise ValueError("plugin.py must define register(ctx)")
        register(PluginContext(plugin_name=name, registry=registry))
    except Exception as exc:
        return PluginInfo(
            name=name,
            path=str(plugin_path),
            enabled=True,
            loaded=False,
            description=description,
            error=str(exc),
        )

    return PluginInfo(
        name=name,
        path=str(plugin_path),
        enabled=True,
        loaded=True,
        description=description,
    )


def _import_plugin_module(module_path: Path, name: str) -> ModuleType:
    module_name = f"longrun_user_plugin_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load plugin module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plugin_paths() -> list[Path]:
    ensure_home()
    root = plugins_dir()
    return [path for path in root.iterdir() if path.is_dir()]


def _read_manifest(plugin_path: Path) -> dict[str, Any]:
    manifest_path = plugin_path / "plugin.json"
    if not manifest_path.exists():
        return {"name": plugin_path.name, "enabled": True}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {
            "name": plugin_path.name,
            "enabled": False,
            "description": "",
            "error": str(exc),
        }
    return data if isinstance(data, dict) else {"name": plugin_path.name, "enabled": False}


def _load_state() -> dict[str, Any]:
    ensure_home()
    path = plugin_state_path()
    if not path.exists():
        return {"enabled": {}}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return {"enabled": {}}
    enabled = data.get("enabled", {})
    data["enabled"] = enabled if isinstance(enabled, dict) else {}
    return data


def _save_state(state: dict[str, Any]) -> Path:
    ensure_home()
    path = plugin_state_path()
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
