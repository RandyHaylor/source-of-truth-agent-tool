"""Concrete AiCliAdapter implementation for Anthropic's Claude Code CLI.

Hook wiring: a UserPromptSubmit hook is registered in ~/.claude/settings.json that
invokes our cli_entrypoint with the user submission JSON via stdin.

Reviewer subprocess: launched via `claude -p` with constrained allowed-tool list.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from .ai_cli_adapter_interface import (
    AiCliAdapterInterface,
    PersistentReviewerSessionHandle,
)


class ClaudeCodePersistentReviewerSessionHandle(PersistentReviewerSessionHandle):
    def __init__(self, subprocess_handle: subprocess.Popen, generated_session_id: str) -> None:
        self._subprocess_handle = subprocess_handle
        self._generated_session_id = generated_session_id
        self._io_lock = threading.Lock()

    @property
    def session_id(self) -> str:
        return self._generated_session_id

    def send_prompt_and_await_response(self, prompt_text: str) -> str:
        with self._io_lock:
            if self._subprocess_handle.stdin is None or self._subprocess_handle.stdout is None:
                raise RuntimeError("reviewer subprocess stdio not available")
            self._subprocess_handle.stdin.write(prompt_text + "\n<<<END_OF_PROMPT>>>\n")
            self._subprocess_handle.stdin.flush()
            response_lines: list[str] = []
            while True:
                line = self._subprocess_handle.stdout.readline()
                if not line:
                    break
                if line.strip() == "<<<END_OF_RESPONSE>>>":
                    break
                response_lines.append(line)
            return "".join(response_lines)

    def is_alive(self) -> bool:
        return self._subprocess_handle.poll() is None

    def terminate(self) -> None:
        try:
            self._subprocess_handle.terminate()
        except OSError:
            pass


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
        # In Claude Code, hooks are registered declaratively in settings.json,
        # not at runtime via Python. Adapter exposes the callable for dispatch
        # by cli_entrypoint when invoked from settings.json.
        self._user_prompt_submit_hook_callable = hook_callable

    def inject_into_next_user_turn(self, injection_text: str) -> None:
        # Claude Code surfaces injection through the hook's `additionalContext`
        # response. Adapter buffers the text for cli_entrypoint to emit.
        self._pending_next_turn_injection = injection_text

    def inject_into_subagent_spawn(self, injection_text: str) -> None:
        self._pending_subagent_spawn_injection = injection_text

    def spawn_persistent_reviewer_session(
        self,
        priming_prompt_text: str,
        allowed_read_paths: list[str],
        allowed_tool_names: list[str],
    ) -> PersistentReviewerSessionHandle:
        command = [
            "claude", "-p",
            "--allowed-tools", ",".join(allowed_tool_names),
        ]
        subprocess_handle = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        generated_session_id = f"reviewer-{uuid.uuid4()}"
        handle = ClaudeCodePersistentReviewerSessionHandle(
            subprocess_handle, generated_session_id
        )
        priming_payload = (
            f"You are the source-of-truth REVIEWER agent.\n"
            f"Allowed read paths: {allowed_read_paths}\n"
            f"Priming context follows.\n{priming_prompt_text}"
        )
        handle.send_prompt_and_await_response(priming_payload)
        return handle
