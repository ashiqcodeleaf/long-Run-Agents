"""Classic interactive LongRun shell."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Callable

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import ThreadedCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.styles import Style
except ImportError:  # pragma: no cover - plain input fallback.
    PromptSession = None  # type: ignore[assignment]
    ThreadedCompleter = None  # type: ignore[assignment]
    FileHistory = None  # type: ignore[assignment]
    Style = None  # type: ignore[assignment]
    patch_stdout = None  # type: ignore[assignment]

from longrun_agent.agent.context import manual_compress_session
from longrun_agent.agent.model_metadata import estimate_messages_tokens_rough, get_provider_context_length
from longrun_agent.agent.runtime import AIAgent
from longrun_agent.auth import get_provider_statuses
from longrun_agent.cli.banner import (
    print_activity,
    print_agent_bootstrap,
    print_banner,
    print_response_box,
    print_setup_guidance,
    print_slash_help,
)
from longrun_agent.cli.commands import SlashCommandCompleter, resolve_command
from longrun_agent.config import ensure_home, get_longrun_home, load_config, save_config, set_config_value
from longrun_agent.state import clear_messages, create_session, get_session, get_state_summary, list_messages, save_transcript
from longrun_agent.tools.registry import registry
from longrun_agent.tools.skills import build_skill_user_message, list_skills


class InteractiveCLI:
    def __init__(self, dispatch: Callable[[list[str]], int]) -> None:
        self.dispatch = dispatch
        self.session_id: str | None = None
        self.running = True
        self._prompt_session = self._build_prompt_session()

    def run(self) -> int:
        print_banner(session_id=self.session_id)
        print_activity("checking auth, tools, skills, and workspace state")
        if not _has_any_auth():
            print_setup_guidance()
        else:
            print_activity("auth configured; model turns can call tools", status="ok")

        while self.running:
            try:
                raw = self._read_input()
            except EOFError:
                print("")
                return 0
            except KeyboardInterrupt:
                print("\nUse /quit to exit.")
                continue

            line = raw.strip().lstrip("\ufeff\ufeff\xef\xbb\xbf")
            if not line:
                continue
            if line.startswith("/"):
                self._handle_slash(line)
            else:
                self._handle_chat(line)
        return 0

    def _build_prompt_session(self):
        if PromptSession is None or not sys.stdin.isatty():
            return None
        history_path = get_longrun_home() / "logs" / "prompt-history.txt"
        completer = SlashCommandCompleter(skill_commands_provider=_skill_command_map)
        style = (
            Style.from_dict(
                {
                    "prompt": "bold ansicyan",
                    "bottom-toolbar": "ansibrightblack",
                    "completion-menu.completion": "bg:#102030 #d7e7ff",
                    "completion-menu.completion.current": "bg:#00a6ff #000000 bold",
                    "completion-menu.meta.completion": "bg:#102030 #8aa0b8",
                    "completion-menu.meta.completion.current": "bg:#00a6ff #000000",
                }
            )
            if Style is not None
            else None
        )
        return PromptSession(
            history=FileHistory(str(history_path)) if FileHistory is not None else None,
            completer=ThreadedCompleter(completer) if ThreadedCompleter is not None else completer,
            complete_while_typing=True,
            style=style,
            bottom_toolbar=self._bottom_toolbar,
        )

    def _read_input(self) -> str:
        if self._prompt_session is None:
            return input("LongRun> ")
        prompt = [("class:prompt", self._prompt_text())]
        if patch_stdout is None:
            return self._prompt_session.prompt(prompt)
        with patch_stdout():
            return self._prompt_session.prompt(prompt)

    def _prompt_text(self) -> str:
        store = _read_goal_store()
        if store.get("goal") and store.get("goal_state", "active") == "active":
            return "LongRun(goal)> "
        return "LongRun> "

    def _bottom_toolbar(self) -> str:
        store = _read_goal_store()
        config = load_config()
        goal = store.get("goal")
        goal_part = f"goal: {str(goal)[:50]}" if goal and store.get("goal_state", "active") == "active" else "goal: off"
        return f"{config['provider']} | {config['model']} | session: {self.session_id or '-'} | {goal_part}"

    def _handle_slash(self, line: str) -> None:
        name, rest = _split_slash(line)
        command = resolve_command(name)
        if command is None:
            if self._try_skill_command(name, rest):
                return
            print(f"Unknown command: /{name}")
            print("Type /help to see available commands.")
            return

        canonical = command.name
        try:
            if canonical == "help":
                print_slash_help()
            elif canonical == "quit":
                self.running = False
                print_activity("session closed", status="ok")
            elif canonical == "new":
                title = rest.strip() or None
                session = create_session(title)
                self.session_id = str(session["id"])
                print_activity(f"new session: {self.session_id}", status="ok")
            elif canonical == "resume":
                self._resume(rest)
            elif canonical == "history":
                self._history()
            elif canonical == "clear":
                self._clear()
            elif canonical == "save":
                self._save(rest)
            elif canonical == "compress":
                self._compress()
            elif canonical == "usage":
                self._usage()
            elif canonical == "goal":
                self._goal("goal", rest)
            elif canonical == "subgoal":
                self._goal("subgoal", rest)
            elif canonical == "plan":
                self._plan(rest)
            elif canonical == "status":
                self.dispatch(["status"])
            elif canonical == "debug":
                self.dispatch(["debug"])
            elif canonical == "sessions":
                self.dispatch(["sessions"])
            elif canonical == "rollback":
                self.dispatch(["rollback", rest.strip()] if rest.strip() else ["checkpoints"])
            elif canonical == "model":
                self._model(rest)
            elif canonical == "config":
                self._config(rest)
            elif canonical == "reasoning":
                self.dispatch(["reasoning", "set", rest.strip()] if rest.strip() else ["reasoning", "show"])
            elif canonical == "verbose":
                self.dispatch(["verbose", rest.strip()] if rest.strip() in {"on", "off"} else ["verbose", "show"])
            elif canonical == "yolo":
                self._yolo(rest)
            elif canonical in {"tools", "toolsets", "skills", "memory", "plugins", "mcp", "agents", "background", "queue", "cron"}:
                self._dispatch_listing(canonical, rest)
            elif canonical == "long-run":
                args = ["long-run"] + (_parse_args(rest) if rest.strip() else ["list"])
                self.dispatch(args)
            elif canonical in {"reload", "reload-mcp", "reload-skills", "stop"}:
                self.dispatch([canonical])
            elif canonical in {"retry", "undo"}:
                print_activity(f"/{canonical} is staged for the next MVP slice", status="warn")
            else:
                print_activity(f"/{canonical} is registered but not wired yet", status="warn")
        except Exception as exc:
            print(f"Command failed: {exc}", file=sys.stderr)

    def _handle_chat(self, text: str, *, include_goal: bool = True) -> None:
        if not _has_any_auth():
            print("Model chat is not configured yet.")
            print_setup_guidance()
            return
        try:
            config = load_config()
            prompt = self._message_with_active_goal(text) if include_goal else text
            print_agent_bootstrap(
                {
                    "provider": config["provider"],
                    "model": config["model"],
                    "session": self.session_id or "new",
                    "tools": len(registry.get_definitions()),
                    "agents": _agent_tool_status(),
                    "goal": _goal_summary(),
                }
            )
            print_activity(f"thinking with {config['model']} ({config['provider']})", status="model")
            agent = AIAgent(
                session_id=self.session_id,
                event_handler=_print_agent_event,
                clarify_callback=self._clarify_user,
            )
            result = agent.run_conversation(prompt)
            self.session_id = result.session_id
            footer = [
                f"session: {result.session_id}",
                f"model: {result.model} | provider: {result.provider} | iterations: {result.iterations}",
                f"estimated context: {result.estimated_tokens} tokens | tools: {', '.join(result.tools_used) if result.tools_used else 'none'}",
            ]
            print_response_box("LongRun response", result.final_response, footer=footer)
        except Exception as exc:
            print(f"Chat failed: {exc}", file=sys.stderr)

    def _try_skill_command(self, name: str, rest: str) -> bool:
        try:
            message = build_skill_user_message(name, rest)
        except FileNotFoundError:
            return False
        print_activity(f"using skill /{name} as a user turn", status="ok")
        self._handle_chat(message)
        return True

    def _clarify_user(self, question: str, choices: list[str] | None) -> str:
        print_response_box(
            "Clarify",
            "\n".join(
                [question]
                + (
                    ["", *[f"{index}. {choice}" for index, choice in enumerate(choices, start=1)], "Other: type your own answer"]
                    if choices
                    else []
                )
            ),
        )
        while True:
            answer = self._read_input().strip()
            if not answer:
                continue
            if choices and answer.isdigit():
                index = int(answer)
                if 1 <= index <= len(choices):
                    return choices[index - 1]
            return answer

    def _plan(self, rest: str) -> None:
        task = rest.strip()
        if not task:
            print("Usage: /plan <task>")
            return
        prompt = (
            "Create a practical, step-by-step plan for this request. "
            "Be specific, prioritize first actions, include milestones, and avoid generic filler.\n\n"
            f"Request: {task}"
        )
        self._handle_chat(prompt, include_goal=False)

    def _dispatch_listing(self, command: str, rest: str) -> None:
        parts = _parse_args(rest) if rest.strip() else ["list"]
        self.dispatch([command] + parts)

    def _resume(self, rest: str) -> None:
        session_id = rest.strip()
        if not session_id:
            self.dispatch(["sessions"])
            return
        session = get_session(session_id)
        if session is None:
            print(f"Session not found: {session_id}", file=sys.stderr)
            return
        self.session_id = session_id
        print_activity(f"resumed session: {session_id}", status="ok")

    def _history(self) -> None:
        if not self.session_id:
            print("No active session. Use /new or /resume first.")
            return
        for message in list_messages(self.session_id):
            print(f"[{message['id']}] {message['role']}: {message['content']}")

    def _clear(self) -> None:
        if not self.session_id:
            print("No active session.")
            return
        deleted = clear_messages(self.session_id)
        print_activity(f"cleared {deleted} message(s) from {self.session_id}", status="ok")

    def _save(self, rest: str) -> None:
        if not self.session_id:
            print("No active session.")
            return
        output = rest.strip() or f"longrun-session-{self.session_id}.md"
        path = save_transcript(self.session_id, Path(output))
        print_activity(f"saved transcript: {path}", status="ok")

    def _compress(self) -> None:
        if not self.session_id:
            print("No active session.")
            return
        config = load_config()
        result = manual_compress_session(
            session_id=self.session_id,
            model=str(config["model"]),
            provider=str(config["provider"]),
            config=config,
        )
        print_response_box("Compression", json.dumps(result, indent=2, sort_keys=True))

    def _usage(self) -> None:
        state = get_state_summary()
        message_count = 0
        rough_tokens = 0
        if self.session_id:
            messages = list_messages(self.session_id)
            message_count = len(messages)
            rough_tokens = estimate_messages_tokens_rough(
                [{"role": message["role"], "content": message["content"]} for message in messages]
            )
        config = load_config()
        context_window = get_provider_context_length(
            str(config["model"]),
            provider=str(config["provider"]),
            configured_default=int(config.get("context", {}).get("max_tokens", 128000)),
        )
        threshold = int(config.get("context", {}).get("compression_threshold_tokens", int(context_window * 0.75)))
        pct = (rough_tokens / context_window * 100) if context_window else 0.0
        print_response_box(
            "Usage",
            "\n".join(
                [
                    f"Session: {self.session_id or '-'}",
                    f"Session messages: {message_count}",
                    f"Rough session tokens: {rough_tokens:,} / {context_window:,} ({pct:.2f}%)",
                    f"Compression threshold: {threshold:,}",
                    f"All sessions: {state['sessions']}",
                    f"All messages: {state['messages']}",
                    f"Provider: {config['provider']}",
                    f"Model: {config['model']}",
                    f"Goal: {_goal_summary()}",
                ]
            ),
        )

    def _goal(self, key: str, rest: str) -> None:
        store = _read_goal_store()
        value = rest.strip()
        if value in {"", "status"}:
            print_response_box(
                key,
                "\n".join(
                    [
                        f"{key}: {store.get(key) or '-'}",
                        f"state: {store.get('goal_state', '-') if key == 'goal' else '-'}",
                        f"runs: {store.get('goal_runs', 0) if key == 'goal' else '-'}",
                    ]
                ),
            )
            return
        if value == "clear":
            store.pop(key, None)
            if key == "goal":
                store.pop("goal_state", None)
                store.pop("goal_runs", None)
            _write_goal_store(store)
            print_activity(f"cleared {key}", status="ok")
            return
        if value == "pause" and key == "goal":
            store["goal_state"] = "pause"
            _write_goal_store(store)
            print_activity("goal paused", status="warn")
            return
        if value in {"run", "continue", "resume"} and key == "goal":
            if not store.get("goal"):
                print("No active goal. Use /goal <objective> first.")
                return
            store["goal_state"] = "active"
            _write_goal_store(store)
            self._run_goal_iteration("continue")
            return
        store[key] = value
        if key == "goal":
            store["goal_state"] = "active"
            store["goal_runs"] = 0
        _write_goal_store(store)
        print_activity(f"saved {key}: {value}", status="ok")
        if key == "goal":
            self._run_goal_iteration("start")

    def _run_goal_iteration(self, mode: str) -> None:
        store = _read_goal_store()
        goal = str(store.get("goal") or "").strip()
        if not goal:
            print("No active goal. Use /goal <objective> first.")
            return
        runs = int(store.get("goal_runs", 0)) + 1
        store["goal_runs"] = runs
        store["goal_state"] = "active"
        _write_goal_store(store)
        subgoal = str(store.get("subgoal") or "").strip()
        prompt = (
            "You are LongRun working on a durable standing goal.\n"
            f"Goal: {goal}\n"
            f"Iteration: {runs}\n"
            f"Mode: {mode}\n"
        )
        if subgoal:
            prompt += f"Focused subgoal: {subgoal}\n"
        prompt += (
            "\nAct like an agent, not a note taker. Analyze the current state, "
            "decide the next concrete step, use tools when useful, and report "
            "what changed or what proof is still missing."
        )
        self._handle_chat(prompt)

    def _message_with_active_goal(self, text: str) -> str:
        store = _read_goal_store()
        goal = str(store.get("goal") or "").strip()
        if not goal or store.get("goal_state", "active") != "active":
            return text
        subgoal = str(store.get("subgoal") or "").strip()
        prefix = f"Standing goal is active for this LongRun session.\nGoal: {goal}\n"
        if subgoal:
            prefix += f"Focused subgoal: {subgoal}\n"
        return (
            f"{prefix}\n"
            "Treat the user's message below as the next instruction toward that goal. "
            "Make concrete progress and use tools when useful.\n\n"
            f"User message:\n{text}"
        )

    def _model(self, rest: str) -> None:
        parts = _parse_args(rest) if rest.strip() else []
        self.dispatch(["model", "set"] + parts if parts else ["model", "show"])

    def _config(self, rest: str) -> None:
        parts = _parse_args(rest) if rest.strip() else []
        if len(parts) >= 2:
            config = load_config()
            set_config_value(config, parts[0], " ".join(parts[1:]))
            save_config(config)
            print_activity(f"set {parts[0]}", status="ok")
            return
        self.dispatch(["config", "show"])

    def _yolo(self, rest: str) -> None:
        arg = rest.strip()
        config = load_config()
        if arg in {"on", "off"}:
            set_config_value(config, "approvals.mode", "yolo" if arg == "on" else "default")
            save_config(config)
            print_activity(f"approvals mode: {config['approvals']['mode']}", status="ok")
            return
        print(f"Approvals mode: {config.get('approvals', {}).get('mode', 'default')}")


def run_interactive() -> int:
    ensure_home()

    def dispatch(argv: list[str]) -> int:
        from longrun_agent.cli.main import main

        return main(argv)

    return InteractiveCLI(dispatch).run()


def _has_any_auth() -> bool:
    return any(status.configured for status in get_provider_statuses())


def _split_slash(line: str) -> tuple[str, str]:
    clean = line.strip()[1:]
    if not clean:
        return "help", ""
    if " " not in clean:
        return clean.lower(), ""
    name, rest = clean.split(" ", 1)
    return name.lower(), rest


def _parse_args(text: str) -> list[str]:
    return shlex.split(text)


def _goal_path() -> Path:
    return ensure_home() / "goal.json"


def _read_goal_store() -> dict[str, object]:
    path = _goal_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_goal_store(store: dict[str, object]) -> None:
    path = _goal_path()
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_agent_event(event: dict[str, object]) -> None:
    event_type = event.get("type")
    if event_type == "agent_init":
        print_activity(
            f"agent ready: {event.get('model')} on {event.get('provider')} "
            f"(max {event.get('max_iterations')} iterations)",
            status="ok",
        )
    elif event_type == "context_start":
        print_activity(
            f"analyzing context: {event.get('history_messages')} prior messages",
            status="info",
        )
    elif event_type == "context_ready":
        cache = "created prompt cache" if event.get("prompt_created") else "reused prompt cache"
        compressed = "compressed" if event.get("compressed") else "no compression"
        print_activity(
            f"context ready: {event.get('estimated_tokens')} tokens, "
            f"{event.get('message_count')} messages, {cache}, {compressed}",
            status="ok",
        )
    elif event_type == "llm_start":
        print_activity(
            f"model call #{event.get('iteration')} with {event.get('tool_count')} tools",
            status="model",
        )
    elif event_type == "llm_complete":
        content = str(event.get("content") or "").strip()
        if content and isinstance(tool_calls := event.get("tool_calls"), list) and tool_calls:
            print_activity(f"agent note: {_one_line(content, 180)}", status="info")
        tool_calls = event.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            print_activity(f"model requested tools: {', '.join(str(item) for item in tool_calls)}", status="tool")
        else:
            print_activity("model returned final text", status="ok")
    elif event_type == "tool_start":
        print_activity(f"tool start: {event.get('name')} - {_tool_preview(event)}", status="tool")
    elif event_type == "tool_complete":
        status = "ok" if event.get("ok") else "failed"
        suffix = f" ({event.get('error')})" if event.get("error") else ""
        print_activity(
            f"tool done: {event.get('name')} [{status}] {_tool_result_preview(event)}{suffix}",
            status="ok" if event.get("ok") else "error",
        )


def _skill_command_map() -> dict[str, dict[str, str]]:
    return {
        skill["name"]: {
            "description": f"{skill['source']} skill",
            "path": skill["path"],
        }
        for skill in list_skills(source="all")
    }


def _goal_summary() -> str:
    store = _read_goal_store()
    goal = str(store.get("goal") or "").strip()
    if not goal or store.get("goal_state", "active") != "active":
        return "off"
    return goal[:64]


def _agent_tool_status() -> str:
    has_delegate = any(str(tool.get("toolset")) == "subagent" for tool in registry.get_definitions())
    return "delegate enabled" if has_delegate else "delegate unavailable"


def _tool_preview(event: dict[str, object]) -> str:
    name = str(event.get("name") or "")
    args = _parse_json_object(str(event.get("arguments") or "{}"))
    if name in {"terminal_run", "process_start"}:
        return _one_line(str(args.get("command", "")), 140)
    if name in {"file_read", "file_write", "file_patch", "file_search"}:
        path = args.get("path")
        pattern = args.get("pattern")
        return _one_line(str(path or pattern or ""), 140)
    if name == "execute_code":
        first = next((line.strip() for line in str(args.get("code", "")).splitlines() if line.strip()), "")
        return _one_line(first, 140)
    if name == "todo":
        todos = args.get("todos")
        if isinstance(todos, list):
            return f"{len(todos)} item(s), merge={bool(args.get('merge', False))}"
        return "read task list"
    if name == "cronjob":
        return _one_line(f"{args.get('action', '')} {args.get('job_id') or args.get('name') or args.get('schedule') or ''}", 140)
    if name == "clarify":
        return _one_line(str(args.get("question", "")), 140)
    if name in {"skills_list", "skill_view"}:
        return _one_line(str(args.get("name") or args.get("category") or "all skills"), 140)
    return _one_line(json.dumps(args, sort_keys=True), 140)


def _tool_result_preview(event: dict[str, object]) -> str:
    result = event.get("result")
    if not isinstance(result, dict):
        return ""
    if "exit_code" in result:
        return f"exit={result.get('exit_code')}"
    if "path" in result:
        return _one_line(str(result.get("path")), 100)
    if "summary" in result:
        return _one_line(json.dumps(result.get("summary"), sort_keys=True), 100)
    if "count" in result:
        return f"count={result.get('count')}"
    if "answer" in result:
        return "answered"
    return ""


def _parse_json_object(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _one_line(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)] + "..."
