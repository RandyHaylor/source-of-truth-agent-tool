"""Unit tests for ClaudeCodeReviewerSessionHandleViaResume.

We do NOT actually launch the claude CLI here; we patch subprocess.Popen with a
fake that yields scripted NDJSON lines, so we can verify command construction,
streaming-event capture, and result parsing without network or auth.
"""
from __future__ import annotations

import io
import json
import subprocess
from typing import Iterable
from unittest.mock import MagicMock, patch

import pytest

from source_of_truth.ai_cli_adapter_claude_code import (
    ClaudeCodeReviewerSessionHandleViaResume,
)


class _FakePopenYieldingScriptedStdoutLines:
    """Stand-in for subprocess.Popen with a deterministic stdout NDJSON stream."""

    def __init__(self, scripted_stdout_lines: Iterable[str]) -> None:
        joined_stdout_text = "".join(line if line.endswith("\n") else line + "\n"
                                     for line in scripted_stdout_lines)
        self.stdout = io.StringIO(joined_stdout_text)
        self.stderr = io.StringIO("")
        self._already_polled_alive_once = False
        self.kill_was_called = False

    def poll(self):
        # First poll returns "still running" so the readline loop drains stdout;
        # subsequent polls return 0 so it exits cleanly.
        if not self._already_polled_alive_once:
            self._already_polled_alive_once = True
            return 0
        return 0

    def kill(self):
        self.kill_was_called = True

    def terminate(self):
        self.kill_was_called = True


def _build_handle(priming_already_done: bool = False, captured_events: list | None = None):
    captured_events = captured_events if captured_events is not None else []
    appender = lambda kind, body: captured_events.append((kind, body))
    return ClaudeCodeReviewerSessionHandleViaResume(
        reviewer_session_id="11111111-2222-3333-4444-555555555555",
        allowed_tool_names=["Read"],
        allowed_read_paths=["/tmp/example"],
        priming_already_done=priming_already_done,
        reviewer_model_name="claude-haiku-4-5-20251001",
        streaming_event_appender=appender,
        per_call_timeout_seconds=10,
    ), captured_events


def test_first_call_uses_session_id_then_subsequent_calls_use_resume():
    handle, _ = _build_handle(priming_already_done=False)
    captured_command_lines: list[list[str]] = []

    def fake_popen(command_list, **kwargs):
        captured_command_lines.append(list(command_list))
        return _FakePopenYieldingScriptedStdoutLines([
            json.dumps({"type": "result", "result": "ok", "is_error": False, "total_cost_usd": 0}),
        ])

    with patch("source_of_truth.ai_cli_adapter_claude_code.subprocess.Popen", side_effect=fake_popen):
        handle.send_prompt_and_await_response("first prompt")
        handle.send_prompt_and_await_response("second prompt")

    first_call_command, second_call_command = captured_command_lines
    assert "--session-id" in first_call_command
    assert "11111111-2222-3333-4444-555555555555" in first_call_command
    assert "--resume" not in first_call_command

    assert "--resume" in second_call_command
    assert "--session-id" not in second_call_command

    # Both calls request stream-json + partial messages, pass --model, restrict tools.
    for cmd in (first_call_command, second_call_command):
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--include-partial-messages" in cmd
        assert "--model" in cmd
        assert "claude-haiku-4-5-20251001" in cmd
        assert "--allowed-tools" in cmd
        assert "Read" in cmd
        assert "--add-dir" in cmd
        assert "/tmp/example" in cmd


def test_returns_result_text_from_final_result_event():
    handle, _ = _build_handle()
    fake_lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "thinking..."}]}}),
        json.dumps({"type": "result", "result": "the verdict reply", "is_error": False, "total_cost_usd": 0.001}),
    ]
    with patch(
        "source_of_truth.ai_cli_adapter_claude_code.subprocess.Popen",
        side_effect=lambda *a, **k: _FakePopenYieldingScriptedStdoutLines(fake_lines),
    ):
        response_text = handle.send_prompt_and_await_response("prompt")
    assert response_text == "the verdict reply"


def test_streaming_appender_receives_every_ndjson_line_in_order():
    handle, captured_events = _build_handle()
    fake_lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "partial reasoning"}]}}),
        json.dumps({"type": "result", "result": "final", "is_error": False, "total_cost_usd": 0}),
    ]
    with patch(
        "source_of_truth.ai_cli_adapter_claude_code.subprocess.Popen",
        side_effect=lambda *a, **k: _FakePopenYieldingScriptedStdoutLines(fake_lines),
    ):
        handle.send_prompt_and_await_response("prompt")

    streamed_line_event_bodies = [body for kind, body in captured_events if kind == "STREAM_LINE"]
    assert len(streamed_line_event_bodies) == 3
    assert "init" in streamed_line_event_bodies[0]
    assert "partial reasoning" in streamed_line_event_bodies[1]
    assert "final" in streamed_line_event_bodies[2]

    final_result_event = next(
        (body for kind, body in captured_events if kind == "FINAL_RESULT"), None
    )
    assert final_result_event is not None
    assert "is_error=False" in final_result_event


def test_falls_back_to_concatenated_assistant_text_when_result_field_absent():
    handle, _ = _build_handle()
    fake_lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "alpha "},
            {"type": "text", "text": "beta"}]}}),
        json.dumps({"type": "result", "is_error": False}),
    ]
    with patch(
        "source_of_truth.ai_cli_adapter_claude_code.subprocess.Popen",
        side_effect=lambda *a, **k: _FakePopenYieldingScriptedStdoutLines(fake_lines),
    ):
        response_text = handle.send_prompt_and_await_response("prompt")
    assert response_text == "alpha beta"


def test_terminate_marks_handle_not_alive():
    handle, _ = _build_handle(priming_already_done=True)
    assert handle.is_alive() is True
    handle.terminate()
    assert handle.is_alive() is False
