from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from longrun_agent.agent.loop import run_tool_loop
from longrun_agent.agent.context import repair_tool_call_pairs
from longrun_agent.agent.transports.base import ModelResponse, ToolCall
from longrun_agent.agent.transports.codex import (
    _collect_stream_response,
    _to_responses_payload,
    _to_responses_tools,
)
from longrun_agent.cli.commands import SlashCommandCompleter
from longrun_agent.tools.clarify import clarify
from longrun_agent.tools.code_execution import execute_code
from longrun_agent.tools.cronjob import cronjob_tool
from longrun_agent.tools.delegate import delegate_task
from longrun_agent.tools.files import write_file
from longrun_agent.tools.registry import registry
from longrun_agent.tools.runtime_context import reset_tool_context, set_tool_context
from longrun_agent.tools.skills import skill_view_tool, skills_list_tool
from longrun_agent.tools.todo import todo_tool
from longrun_agent.state import add_message, create_session, infer_session_title, maybe_auto_title_session

try:
    from prompt_toolkit.document import Document
except ImportError:  # pragma: no cover
    Document = None  # type: ignore[assignment]


class FakeToolTransport:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, tools=None):
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                content="I will write the requested file.",
                tool_calls=(
                    ToolCall(
                        id="call_write",
                        name="file_write",
                        arguments=json.dumps(
                            {
                                "path": "tmp-unit-agent/proof.md",
                                "content": "# Proof\n\nTools work.\n",
                            }
                        ),
                    ),
                ),
            )
        return ModelResponse(content="Done.")


class AgentToolTests(unittest.TestCase):
    def test_codex_tool_schema_conversion(self) -> None:
        tools = _to_responses_tools(
            [
                {
                    "name": "file_write",
                    "description": "Write a file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            ]
        )

        self.assertEqual(tools[0]["type"], "function")
        self.assertEqual(tools[0]["name"], "file_write")
        self.assertFalse(tools[0]["strict"])
        self.assertIn("parameters", tools[0])

    def test_codex_payload_replays_tool_pairs(self) -> None:
        _instructions, items = _to_responses_payload(
            [
                {"role": "system", "content": "rules"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "file_write", "arguments": '{"path":"x"}'},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_123", "content": '{"ok":true}'},
            ]
        )

        self.assertEqual(items[0]["type"], "function_call")
        self.assertEqual(items[0]["call_id"], "call_123")
        self.assertEqual(items[1]["type"], "function_call_output")
        self.assertEqual(items[1]["call_id"], "call_123")

    def test_codex_payload_skips_orphan_tool_outputs(self) -> None:
        _instructions, items = _to_responses_payload(
            [
                {"role": "tool", "tool_call_id": "missing_call", "content": '{"ok":true}'},
                {"role": "user", "content": "continue"},
            ]
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "message")
        self.assertEqual(items[0]["role"], "user")

    def test_context_repair_removes_orphan_tool_outputs(self) -> None:
        repaired = repair_tool_call_pairs(
            [
                {"role": "system", "content": "rules"},
                {"role": "tool", "tool_call_id": "old_call", "content": '{"ok":true}'},
                {
                    "role": "assistant",
                    "content": "I will call a tool.",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "file_read", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_123", "content": '{"ok":true}'},
                {
                    "role": "assistant",
                    "content": "Incomplete call",
                    "tool_calls": [
                        {
                            "id": "call_missing",
                            "type": "function",
                            "function": {"name": "file_read", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "user", "content": "next"},
            ]
        )

        self.assertEqual([message["role"] for message in repaired], ["system", "assistant", "tool", "assistant", "user"])
        self.assertEqual(repaired[2]["tool_call_id"], "call_123")
        self.assertNotIn("tool_calls", repaired[3])

    def test_codex_stream_function_call_parsing(self) -> None:
        stream = [
            SimpleNamespace(
                type="response.output_item.done",
                item=SimpleNamespace(
                    type="function_call",
                    call_id="call_abc",
                    name="file_write",
                    arguments='{"path":"proof.md","content":"ok"}',
                ),
            ),
            SimpleNamespace(type="response.completed", response=SimpleNamespace(output=[])),
        ]

        text, _response, tool_calls = _collect_stream_response(stream)

        self.assertEqual(text, "")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].name, "file_write")
        self.assertEqual(tool_calls[0].id, "call_abc")

    def test_loop_emits_events_and_executes_file_write(self) -> None:
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                import os

                os.chdir(tmp)
                result = run_tool_loop(
                    transport=FakeToolTransport(),
                    messages=[{"role": "user", "content": "write proof"}],
                    max_iterations=3,
                    event_handler=events.append,
                )
                self.assertEqual(result.final_response, "Done.")
                self.assertEqual(result.tools_used, ("file_write",))
                self.assertTrue(Path("tmp-unit-agent/proof.md").is_file())
                self.assertIn("Tools work.", Path("tmp-unit-agent/proof.md").read_text())
            finally:
                os.chdir(cwd)

        self.assertIn("llm_start", [event["type"] for event in events])
        self.assertIn("tool_start", [event["type"] for event in events])
        self.assertIn("tool_complete", [event["type"] for event in events])

    def test_file_write_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "plan.md"
            result = write_file(str(path), "# Plan\n")
            self.assertTrue(path.is_file())
            self.assertEqual(Path(result["path"]), path.resolve())

    def test_slash_completer_suggests_commands_and_skills(self) -> None:
        if Document is None:
            self.skipTest("prompt_toolkit is not installed")
        completer = SlashCommandCompleter(
            skill_commands_provider=lambda: {
                "testing-skill": {"description": "testing helper"},
            }
        )

        names = {
            completion.text.strip()
            for completion in completer.get_completions(Document("/go"), None)
        }
        skill_names = {
            completion.text.strip()
            for completion in completer.get_completions(Document("/testing"), None)
        }

        self.assertIn("goal", names)
        self.assertIn("testing-skill", skill_names)

    def test_staged_toolsets_are_registered(self) -> None:
        names = {definition["name"] for definition in registry.get_definitions()}

        self.assertIn("skills_list", names)
        self.assertIn("skill_view", names)
        self.assertIn("todo", names)
        self.assertIn("clarify", names)
        self.assertIn("execute_code", names)
        self.assertIn("cronjob", names)

    def test_todo_tool_persists_by_session_context(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            import os

            old_home = os.environ.get("LONGRUN_AGENT_HOME")
            os.environ["LONGRUN_AGENT_HOME"] = home
            token = set_tool_context(session_id="session-test")
            try:
                first = todo_tool(
                    [{"id": "one", "content": "Build tool", "status": "in_progress"}]
                )
                second = todo_tool()
            finally:
                reset_tool_context(token)
                if old_home is None:
                    os.environ.pop("LONGRUN_AGENT_HOME", None)
                else:
                    os.environ["LONGRUN_AGENT_HOME"] = old_home

        self.assertEqual(first["summary"]["total"], 1)
        self.assertEqual(second["todos"][0]["id"], "one")

    def test_skill_tools_list_and_view(self) -> None:
        listed = skills_list_tool("software-development")
        viewed = skill_view_tool("app-mvp-builder")

        self.assertGreaterEqual(listed["count"], 1)
        self.assertEqual(viewed["name"], "app-mvp-builder")
        self.assertIn("Actually create the files", viewed["content"])

    def test_clarify_uses_runtime_callback(self) -> None:
        token = set_tool_context(clarify_callback=lambda question, choices: choices[0] if choices else "answer")
        try:
            result = clarify("Pick one", ["A", "B"])
        finally:
            reset_tool_context(token)

        self.assertTrue(result["available"])
        self.assertEqual(result["answer"], "A")

    def test_execute_code_can_call_longrun_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = execute_code(
                "from longrun_tools import file_write\n"
                "file_write('generated/proof.txt', 'ok')\n"
                "print('done')\n",
                cwd=tmp,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertIn("done", result["stdout"])
            self.assertEqual((Path(tmp) / "generated" / "proof.txt").read_text(), "ok")

    def test_cronjob_tool_creates_and_pauses_job(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            import os

            old_home = os.environ.get("LONGRUN_AGENT_HOME")
            os.environ["LONGRUN_AGENT_HOME"] = home
            try:
                created = cronjob_tool(
                    action="create",
                    prompt="Write a weekly repo summary",
                    schedule="manual",
                    name="weekly-summary",
                )
                listed = cronjob_tool(action="list")
                paused = cronjob_tool(action="pause", job_id=created["job"]["id"], reason="test")
            finally:
                if old_home is None:
                    os.environ.pop("LONGRUN_AGENT_HOME", None)
                else:
                    os.environ["LONGRUN_AGENT_HOME"] = old_home

        self.assertTrue(created["success"])
        self.assertEqual(created["job"]["name"], "weekly-summary")
        self.assertEqual(listed["count"], 1)
        self.assertFalse(paused["job"]["enabled"])

    def test_delegate_task_records_completed_agent_job(self) -> None:
        import gc
        import os
        import longrun_agent.agent.runtime as runtime_module
        from longrun_agent.state import list_agent_jobs

        class FakeAgent:
            def __init__(self, *, title=None):
                self.title = title

            def run_conversation(self, prompt):
                return SimpleNamespace(
                    session_id="session-child",
                    final_response=f"child handled: {prompt}",
                    provider="fake-provider",
                    model="fake-model",
                    iterations=1,
                    stopped_by_limit=False,
                )

        with tempfile.TemporaryDirectory() as home:
            old_home = os.environ.get("LONGRUN_AGENT_HOME")
            old_agent = runtime_module.AIAgent
            os.environ["LONGRUN_AGENT_HOME"] = home
            runtime_module.AIAgent = FakeAgent
            try:
                result = delegate_task("inspect files", title="unit child")
                jobs = list_agent_jobs(limit=5)
            finally:
                runtime_module.AIAgent = old_agent
                if old_home is None:
                    os.environ.pop("LONGRUN_AGENT_HOME", None)
                else:
                    os.environ["LONGRUN_AGENT_HOME"] = old_home
                gc.collect()

        self.assertEqual(result["job_id"], jobs[0]["id"])
        self.assertEqual(jobs[0]["status"], "completed")
        self.assertEqual(jobs[0]["session_id"], "session-child")
        self.assertIn("child handled", jobs[0]["result"])

    def test_session_auto_title_from_first_user_message(self) -> None:
        import gc
        import os

        with tempfile.TemporaryDirectory() as home:
            old_home = os.environ.get("LONGRUN_AGENT_HOME")
            os.environ["LONGRUN_AGENT_HOME"] = home
            try:
                session = create_session()
                add_message(session["id"], "user", "uv run longrun long-run create \"build todo app\"")
                titled = maybe_auto_title_session(session["id"], "uv run longrun long-run create \"build todo app\"")

                explicit = create_session("Manual title")
                add_message(explicit["id"], "user", "make a notes app")
                unchanged = maybe_auto_title_session(explicit["id"], "make a notes app")
            finally:
                if old_home is None:
                    os.environ.pop("LONGRUN_AGENT_HOME", None)
                else:
                    os.environ["LONGRUN_AGENT_HOME"] = old_home
                gc.collect()

        self.assertEqual(titled["title"], 'long-run create "build todo app"')
        self.assertEqual(unchanged["title"], "Manual title")

    def test_session_title_infers_from_goal_wrapped_message(self) -> None:
        title = infer_session_title(
            "Standing goal is active for this LongRun session.\n"
            "Goal: make app\n\n"
            "Treat the user's message below as the next instruction.\n\n"
            "User message:\nmake a calculator app"
        )

        self.assertEqual(title, "make a calculator app")


if __name__ == "__main__":
    unittest.main()
