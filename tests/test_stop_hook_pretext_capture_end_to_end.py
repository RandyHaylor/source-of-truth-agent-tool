"""End-to-end: Stop hook captures agent output -> UserPromptSubmit consumes it
as the next prompt's pre_submission_content."""
from __future__ import annotations

import io
import json

from source_of_truth import cli_entrypoint, load_config
from source_of_truth import stop_hook_capture_agent_output as stop_mod
from source_of_truth.add_session_to_project_cli import add_session_to_project


def _write_completed_turn_transcript(path):
    """A turn that ends after a tool-use loop: user prompt, assistant text,
    assistant tool_use, tool_result (type:user), assistant final text."""
    events = [
        {"type": "user", "message": {"role": "user", "content": "design the audio thing"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "Here is the plan: A, B, C."}]}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "user", "message": {"role": "user",
            "content": [{"type": "tool_result", "content": "file1 file2"}]}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "Done; confirm?"}]}},
    ]
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def test_stop_capture_then_userpromptsubmit_consumes_pretext(tmp_path, monkeypatch):
    project_id = "sess-x"
    session_id = "sess-x"
    transcript = tmp_path / "t.jsonl"
    add_session_to_project(project_id, session_id, str(transcript))
    _write_completed_turn_transcript(transcript)

    # 1) Stop hook fires at end of the turn.
    stop_payload = json.dumps({"session_id": session_id, "transcript_path": str(transcript)})
    monkeypatch.setattr("sys.stdin", io.StringIO(stop_payload))
    stop_mod._main()

    pending = load_config.project_pending_pre_text_file_path(project_id, session_id)
    assert pending.exists()
    captured = pending.read_text()
    assert "Here is the plan: A, B, C." in captured       # assistant text
    assert "Done; confirm?" in captured                   # text after the tool loop
    assert "[tool_result] file1 file2" in captured        # tool RESULT included
    assert "[tool:" not in captured                       # tool CALL excluded

    # 2) Next prompt "yes" -> UserPromptSubmit consumes the pre-text.
    ups_payload = json.dumps({"session_id": session_id, "prompt": "yes"})
    monkeypatch.setattr("sys.stdin", io.StringIO(ups_payload))
    cli_entrypoint._handle_user_prompt_submit_hook()

    assert not pending.exists()  # consume-once

    raw_log = json.loads(load_config.project_raw_input_log_file_path(project_id).read_text())
    last_entry = raw_log[session_id][-1]
    assert last_entry["submission_text"] == "yes"
    assert "Here is the plan: A, B, C." in last_entry["pre_submission_content"]
    assert "[tool_result] file1 file2" in last_entry["pre_submission_content"]


def test_userpromptsubmit_with_no_capture_has_empty_pretext(tmp_path, monkeypatch):
    project_id = "sess-y"
    session_id = "sess-y"
    add_session_to_project(project_id, session_id, str(tmp_path / "y.jsonl"))

    ups_payload = json.dumps({"session_id": session_id, "prompt": "first message"})
    monkeypatch.setattr("sys.stdin", io.StringIO(ups_payload))
    cli_entrypoint._handle_user_prompt_submit_hook()

    raw_log = json.loads(load_config.project_raw_input_log_file_path(project_id).read_text())
    assert raw_log[session_id][-1]["pre_submission_content"] == ""
