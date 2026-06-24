"""Minimal stdio MCP client and tool bridge."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from longrun_agent.config import ensure_home, mcp_servers_path, mcp_tools_cache_path

MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass(frozen=True)
class MCPServer:
    """One configured MCP stdio server."""

    name: str
    command: str
    args: tuple[str, ...]


def list_mcp_servers() -> list[MCPServer]:
    """Return configured MCP servers."""

    store = _load_servers()
    servers: list[MCPServer] = []
    for name, data in sorted(store["servers"].items()):
        if not isinstance(data, dict) or data.get("transport", "stdio") != "stdio":
            continue
        args = data.get("args", [])
        servers.append(
            MCPServer(
                name=name,
                command=str(data.get("command", "")),
                args=tuple(str(arg) for arg in args if arg is not None),
            )
        )
    return servers


def add_stdio_server(name: str, command: str, args: list[str] | None = None) -> Path:
    """Add or replace a stdio MCP server definition."""

    clean_name = _clean_name(name)
    clean_command = command.strip()
    if not clean_command:
        raise ValueError("MCP command cannot be empty")
    store = _load_servers()
    store["servers"][clean_name] = {
        "transport": "stdio",
        "command": clean_command,
        "args": args or [],
    }
    return _save_servers(store)


def remove_mcp_server(name: str) -> dict[str, Any]:
    """Remove one MCP server definition."""

    clean_name = _clean_name(name)
    store = _load_servers()
    existed = clean_name in store["servers"]
    store["servers"].pop(clean_name, None)
    _save_servers(store)
    return {"name": clean_name, "removed": existed}


def reload_mcp_tools(timeout_seconds: float = 10.0) -> dict[str, Any]:
    """Discover tools from every configured server and write the local cache."""

    tools: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for server in list_mcp_servers():
        try:
            discovered = _list_tools_from_server(server, timeout_seconds=timeout_seconds)
        except Exception as exc:
            errors[server.name] = str(exc)
            continue
        for tool in discovered:
            tool_name = str(tool.get("name", ""))
            if not tool_name:
                continue
            tools.append(
                {
                    "server": server.name,
                    "name": tool_name,
                    "registry_name": _registry_tool_name(server.name, tool_name),
                    "description": str(tool.get("description", "")),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            )

    cache = {"tools": tools, "errors": errors}
    _save_tools_cache(cache)
    return cache


def cached_mcp_tools() -> dict[str, Any]:
    """Return cached MCP tool discovery data."""

    path = mcp_tools_cache_path()
    if not path.exists():
        return {"tools": [], "errors": {}}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return {"tools": [], "errors": {}}
    data.setdefault("tools", [])
    data.setdefault("errors", {})
    return data


def register_cached_mcp_tools(registry: Any) -> None:
    """Register cached MCP tools with the central registry."""

    for tool in cached_mcp_tools().get("tools", []):
        if not isinstance(tool, dict):
            continue
        registry_name = str(tool.get("registry_name", ""))
        server_name = str(tool.get("server", ""))
        tool_name = str(tool.get("name", ""))
        if not registry_name or not server_name or not tool_name:
            continue
        try:
            registry.register(
                name=registry_name,
                description=str(tool.get("description", "")),
                parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                toolset="mcp",
                handler=lambda args, server=server_name, name=tool_name: call_mcp_tool(
                    server,
                    name,
                    args,
                ),
            )
        except ValueError as exc:
            if "already registered" not in str(exc):
                raise


def call_mcp_tool(server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call one cached MCP tool by launching its configured stdio server."""

    server = _get_server(server_name)
    with _stdio_client(server, timeout_seconds=30.0) as client:
        result = client.request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
    return {"server": server_name, "tool": tool_name, "result": result}


class _MCPStdioClient:
    def __init__(self, server: MCPServer, *, timeout_seconds: float) -> None:
        self.server = server
        self.timeout_seconds = timeout_seconds
        self._request_id = 0
        self._executor = ThreadPoolExecutor(max_workers=1)
        self.process = subprocess.Popen(
            [server.command, *server.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "longrun-agent", "version": "0.1.0"},
            },
        )
        self.notify("notifications/initialized", {})

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._request_id += 1
        request_id = self._request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        while True:
            message = self._read()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(json.dumps(message["error"], sort_keys=True))
            return message.get("result", {})

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _send(self, payload: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise RuntimeError("MCP server stdin is not available")
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.process.stdin.write(header + body)
        self.process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        if self.process.stdout is None:
            raise RuntimeError("MCP server stdout is not available")
        future = self._executor.submit(_read_message_blocking, self.process.stdout)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeout as exc:
            self.close()
            raise TimeoutError(f"MCP server timed out: {self.server.name}") from exc
        except Exception as exc:
            stderr = self._stderr_tail()
            if stderr:
                raise RuntimeError(f"{exc}; stderr={stderr}") from exc
            raise

    def _stderr_tail(self) -> str:
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                return ""
        if self.process.stderr is None:
            return ""
        try:
            text = self.process.stderr.read().decode("utf-8", errors="replace").strip()
        except OSError:
            return ""
        if len(text) > 1000:
            return text[-1000:]
        return text


class _stdio_client:
    def __init__(self, server: MCPServer, *, timeout_seconds: float) -> None:
        self.client = _MCPStdioClient(server, timeout_seconds=timeout_seconds)

    def __enter__(self) -> _MCPStdioClient:
        self.client.initialize()
        return self.client

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.client.close()


def _list_tools_from_server(server: MCPServer, *, timeout_seconds: float) -> list[dict[str, Any]]:
    with _stdio_client(server, timeout_seconds=timeout_seconds) as client:
        result = client.request("tools/list", {})
    tools = result.get("tools", []) if isinstance(result, dict) else []
    return [tool for tool in tools if isinstance(tool, dict)]


def _read_message_blocking(stdout: BinaryIO) -> dict[str, Any]:
    content_length: int | None = None
    while True:
        line = stdout.readline()
        if line == b"":
            raise RuntimeError("MCP server closed stdout")
        if line in {b"\r\n", b"\n"}:
            break
        decoded = line.decode("ascii", errors="replace").strip()
        if decoded.lower().startswith("content-length:"):
            content_length = int(decoded.split(":", 1)[1].strip())
    if content_length is None:
        raise RuntimeError("MCP message missing Content-Length")
    body = stdout.read(content_length)
    if len(body) != content_length:
        raise RuntimeError("MCP message body was truncated")
    message = json.loads(body.decode("utf-8"))
    if not isinstance(message, dict):
        raise RuntimeError("MCP message was not a JSON object")
    return message


def _get_server(name: str) -> MCPServer:
    clean_name = _clean_name(name)
    for server in list_mcp_servers():
        if server.name == clean_name:
            return server
    raise KeyError(f"MCP server not found: {clean_name}")


def _registry_tool_name(server_name: str, tool_name: str) -> str:
    return "mcp_" + _sanitize_name(server_name) + "_" + _sanitize_name(tool_name)


def _sanitize_name(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "_" for char in value]
    text = "".join(chars).strip("_")
    while "__" in text:
        text = text.replace("__", "_")
    return text or "tool"


def _clean_name(name: str) -> str:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("MCP server name cannot be empty")
    return clean_name


def _load_servers() -> dict[str, Any]:
    ensure_home()
    path = mcp_servers_path()
    if not path.exists():
        return {"servers": {}}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return {"servers": {}}
    servers = data.get("servers", {})
    data["servers"] = servers if isinstance(servers, dict) else {}
    return data


def _save_servers(store: dict[str, Any]) -> Path:
    ensure_home()
    path = mcp_servers_path()
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _save_tools_cache(cache: dict[str, Any]) -> Path:
    ensure_home()
    path = mcp_tools_cache_path()
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
