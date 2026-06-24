"""Agent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from longrun_agent.agent.context import build_turn_context
from longrun_agent.agent.loop import run_tool_loop
from longrun_agent.agent.transports.base import ChatTransport
from longrun_agent.agent.transports.codex import CodexResponsesTransport
from longrun_agent.agent.transports.openai import OpenAIChatTransport
from longrun_agent.auth import CODEX_PROVIDER, OPENAI_API_PROVIDER, get_codex_access_token, require_openai_api_key
from longrun_agent.config import load_config
from longrun_agent.hooks import run_hooks
from longrun_agent.state import add_message, ensure_session, list_messages, maybe_auto_title_session
from longrun_agent.tools.runtime_context import ClarifyCallback, reset_tool_context, set_tool_context


@dataclass(frozen=True)
class AgentResult:
    """Result returned by one no-tool conversation turn."""

    session_id: str
    final_response: str
    user_message_id: int
    assistant_message_id: int
    provider: str
    model: str
    prompt_created: bool
    compressed: bool
    estimated_tokens: int
    iterations: int
    stopped_by_limit: bool
    tools_used: tuple[str, ...]


class AIAgent:
    """LongRun's small MyAgent-style agent surface."""

    def __init__(
        self,
        *,
        session_id: str | None = None,
        title: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
        config: dict[str, Any] | None = None,
        transport: ChatTransport | None = None,
        event_handler: Callable[[dict[str, Any]], None] | None = None,
        clarify_callback: ClarifyCallback | None = None,
    ) -> None:
        self.config = config or load_config()
        self.provider = provider or str(self.config["provider"])
        self.model = model or str(self.config["model"])
        self.max_iterations = max_iterations or int(self.config["max_iterations"])
        self.session_id = session_id
        self.title = title
        self._transport = transport
        self._event_handler = event_handler
        self._clarify_callback = clarify_callback

    def chat(self, message: str) -> str:
        """Simple interface returning only the assistant text."""

        return self.run_conversation(message).final_response

    def run_conversation(self, user_message: str) -> AgentResult:
        """Run one no-tool model turn and persist user/assistant messages."""

        clean_message = user_message.strip()
        if not clean_message:
            raise ValueError("User message cannot be empty")

        self._emit(
            {
                "type": "agent_init",
                "provider": self.provider,
                "model": self.model,
                "max_iterations": self.max_iterations,
                "session_id": self.session_id or "new",
            }
        )
        transport = self._transport or self._build_transport()
        session = ensure_session(self.session_id, self.title)
        self.session_id = str(session["id"])
        run_hooks(
            "session_start",
            {
                "session_id": self.session_id,
                "provider": self.provider,
                "model": self.model,
            },
        )
        turn_payload = {
            "session_id": self.session_id,
            "user_message": clean_message,
            "provider": self.provider,
            "model": self.model,
        }
        run_hooks("turn_start", turn_payload)
        clean_message = str(turn_payload.get("user_message", clean_message)).strip()
        if not clean_message:
            raise ValueError("User message cannot be empty after turn_start hooks")

        history = list_messages(self.session_id)
        self._emit(
            {
                "type": "context_start",
                "session_id": self.session_id,
                "history_messages": len(history),
            }
        )
        turn_context = build_turn_context(
            session_id=self.session_id,
            history=history,
            user_message=clean_message,
            config=self.config,
            model=self.model,
            provider=self.provider,
        )
        self._emit(
            {
                "type": "context_ready",
                "session_id": self.session_id,
                "prompt_created": turn_context.prompt_created,
                "compressed": turn_context.compressed,
                "estimated_tokens": turn_context.estimated_tokens,
                "message_count": len(turn_context.messages),
            }
        )

        user_row = add_message(self.session_id, "user", clean_message)
        maybe_auto_title_session(self.session_id, clean_message)
        context_token = set_tool_context(
            session_id=self.session_id,
            clarify_callback=self._clarify_callback,
        )
        try:
            loop_result = run_tool_loop(
                transport=transport,
                messages=turn_context.messages,
                max_iterations=self.max_iterations,
                event_handler=self._event_handler,
            )
        finally:
            reset_tool_context(context_token)
        assistant_text = loop_result.final_response.strip()
        if not assistant_text:
            raise RuntimeError("Model returned an empty assistant response")
        assistant_row = None
        for message in loop_result.messages_to_persist:
            row = add_message(
                self.session_id,
                message.role,  # type: ignore[arg-type]
                message.content,
                metadata=message.metadata,
            )
            if message.role == "assistant":
                assistant_row = row
        if assistant_row is None:
            raise RuntimeError("Agent loop did not produce an assistant message")

        return AgentResult(
            session_id=self.session_id,
            final_response=assistant_text,
            user_message_id=int(user_row["id"]),
            assistant_message_id=int(assistant_row["id"]),
            provider=self.provider,
            model=self.model,
            prompt_created=turn_context.prompt_created,
            compressed=turn_context.compressed,
            estimated_tokens=turn_context.estimated_tokens,
            iterations=loop_result.iterations,
            stopped_by_limit=loop_result.stopped_by_limit,
            tools_used=loop_result.tools_used,
        )

    def _build_transport(self) -> ChatTransport:
        if self.provider == OPENAI_API_PROVIDER:
            require_openai_api_key()
            return OpenAIChatTransport(
                model=self.model,
                base_url=str(self.config["openai"]["base_url"]),
            )

        if self.provider == CODEX_PROVIDER:
            if not get_codex_access_token():
                raise RuntimeError("Codex OAuth is not configured. Use `longrun auth status` to inspect auth.")
            return CodexResponsesTransport(
                model=self.model,
                base_url=str(self.config["codex"]["base_url"]),
            )

        raise ValueError(f"Unsupported provider for MVP: {self.provider}")

    def _emit(self, event: dict[str, Any]) -> None:
        if self._event_handler is None:
            return
        try:
            self._event_handler(event)
        except Exception:
            return
