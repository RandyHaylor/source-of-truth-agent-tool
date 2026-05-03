"""Concrete AiCliAdapter implementation for Anthropic's Claude Code CLI.

Reviewer persistence model:
  - First call uses `claude -p --session-id <uuid> --output-format stream-json
    --include-partial-messages ...` to create the reviewer session with priming.
  - Subsequent calls reuse the session via `claude -p --resume <uuid> ...`.
  - Output is streamed in NDJSON so EVERY event (assistant text deltas, tool
    calls, partial messages, final result) is appended to the reviewer-thinking
    log as it arrives. If the call later times out, we still have the full
    record of what the reviewer was doing.

Tool sandbox: --allowed-tools restricts what the reviewer may invoke.
--add-dir grants Read access to the project directory without permission prompts.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .ai_cli_adapter_interface import (
    AiCliAdapterInterface,
    PersistentReviewerSessionHandle,
)


class ClaudeCodeReviewerSessionHandleViaResume(PersistentReviewerSessionHandle):
    """Reviewer handle that persists via Claude's --session-id / --resume mechanism.

    Streams every NDJSON event from `claude -p --output-format stream-json`
    to a caller-supplied appender so the reviewer-thinking log captures
    everything in real time -- even if the call later times out.
    """

    def __init__(
        self,
        reviewer_session_id: str,
        allowed_tool_names: list[str],
        allowed_read_paths: list[str],
        priming_already_done: bool,
        reviewer_model_name: str,
        streaming_event_appender: Optional[Callable[[str, str], None]] = None,
        per_call_timeout_seconds: float = 600.0,
    ) -> None:
        self._reviewer_session_id = reviewer_session_id
        self._allowed_tool_names = list(allowed_tool_names)
        self._allowed_read_paths = list(allowed_read_paths)
        self._priming_already_done = priming_already_done
        self._reviewer_model_name = reviewer_model_name
        self._streaming_event_appender = streaming_event_appender
        self._per_call_timeout_seconds = per_call_timeout_seconds
        self._is_alive = True

    @property
    def session_id(self) -> str:
        return self._reviewer_session_id

    def is_alive(self) -> bool:
        return self._is_alive

    def terminate(self) -> None:
        self._is_alive = False

    def _emit_streamed_event(self, event_kind: str, event_body_text: str) -> None:
        if self._streaming_event_appender is not None:
            try:
                self._streaming_event_appender(event_kind, event_body_text)
            except Exception:
                pass

    def send_prompt_and_await_response(self, prompt_text: str) -> str:
        command = [
            "claude", "-p",
            "--model", self._reviewer_model_name,
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",  # required by stream-json per claude CLI
        ]
        if self._priming_already_done:
            command += ["--resume", self._reviewer_session_id]
        else:
            command += ["--session-id", self._reviewer_session_id]
        if self._allowed_tool_names:
            command += ["--allowed-tools", ",".join(self._allowed_tool_names)]
        for read_path in self._allowed_read_paths:
            command += ["--add-dir", read_path]
        command.append(prompt_text)

        self._emit_streamed_event(
            "SUBPROCESS_LAUNCH",
            f"command={command[0]} session_id={self._reviewer_session_id} "
            f"resume={self._priming_already_done}",
        )
        process_handle = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._priming_already_done = True

        deadline_monotonic = time.monotonic() + self._per_call_timeout_seconds
        accumulated_assistant_text_chunks: list[str] = []
        final_result_text: Optional[str] = None
        timed_out = False

        try:
            assert process_handle.stdout is not None
            while True:
                if time.monotonic() > deadline_monotonic:
                    timed_out = True
                    self._emit_streamed_event(
                        "TIMEOUT",
                        f"per_call_timeout_seconds={self._per_call_timeout_seconds} exceeded; killing subprocess",
                    )
                    process_handle.kill()
                    break
                line = process_handle.stdout.readline()
                if not line:
                    if process_handle.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                stripped = line.rstrip("\n")
                self._emit_streamed_event("STREAM_LINE", stripped)
                try:
                    parsed_event = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                event_type = parsed_event.get("type")
                if event_type == "assistant":
                    content_blocks = parsed_event.get("message", {}).get("content") or []
                    for block in content_blocks:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_chunk = block.get("text") or ""
                            if text_chunk:
                                accumulated_assistant_text_chunks.append(text_chunk)
                elif event_type == "result":
                    final_result_text = parsed_event.get("result")
                    if final_result_text is None:
                        final_result_text = "".join(accumulated_assistant_text_chunks)
                    self._emit_streamed_event(
                        "FINAL_RESULT",
                        f"is_error={parsed_event.get('is_error')} cost_usd={parsed_event.get('total_cost_usd')}",
                    )
                    break
        finally:
            stderr_text = ""
            try:
                if process_handle.stderr is not None:
                    stderr_text = process_handle.stderr.read() or ""
            except Exception:
                stderr_text = ""
            if stderr_text.strip():
                self._emit_streamed_event("STDERR", stderr_text.strip())
            if process_handle.poll() is None:
                try:
                    process_handle.kill()
                except OSError:
                    pass

        if timed_out:
            return (
                f"[reviewer subprocess timed out after {self._per_call_timeout_seconds}s; "
                f"see streamed events in the reviewer log]"
            )
        if final_result_text is not None:
            return final_result_text
        return "".join(accumulated_assistant_text_chunks) or "[reviewer subprocess produced no parsable output]"


class ClaudeCodeAdapter(AiCliAdapterInterface):
    def __init__(self, current_session_id: str | None = None) -> None:
        self._current_session_id = current_session_id or os.environ.get(
            "CLAUDE_SESSION_ID", "unknown-session"
        )

    def get_current_session_id(self) -> str:
        return self._current_session_id

    def register_user_prompt_submit_hook(
        self, hook_callable: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        # Claude Code hooks are registered declaratively in settings.json.
        # The adapter just keeps the callable for cli_entrypoint to dispatch.
        self._user_prompt_submit_hook_callable = hook_callable

    def inject_into_next_user_turn(self, injection_text: str) -> None:
        self._pending_next_turn_injection = injection_text

    def inject_into_subagent_spawn(self, injection_text: str) -> None:
        self._pending_subagent_spawn_injection = injection_text

    def spawn_persistent_reviewer_session(
        self,
        priming_prompt_text: str,
        allowed_read_paths: list[str],
        allowed_tool_names: list[str],
        reviewer_model_name: str,
        streaming_event_appender: Optional[Callable[[str, str], None]] = None,
    ) -> PersistentReviewerSessionHandle:
        new_reviewer_session_id = str(uuid.uuid4())
        handle = ClaudeCodeReviewerSessionHandleViaResume(
            reviewer_session_id=new_reviewer_session_id,
            allowed_tool_names=allowed_tool_names,
            allowed_read_paths=allowed_read_paths,
            priming_already_done=False,
            reviewer_model_name=reviewer_model_name,
            streaming_event_appender=streaming_event_appender,
        )
        priming_payload = (
            "You are the source-of-truth REVIEWER agent.\n"
            f"Allowed read paths: {allowed_read_paths}\n"
            "On every change-set prompt, reply with EXACTLY one JSON object on its own line: "
            '{"approved": <bool>, "message": "<short reason or guidance>"} '
            "and nothing else outside that object.\n\n"
            f"Priming context:\n{priming_prompt_text}"
        )
        handle.send_prompt_and_await_response(priming_payload)
        return handle
