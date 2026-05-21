"""Stop-hook handler: capture this turn's agent output as the next prompt's pre-text.

On every Claude Code Stop event this:
  1. reads the hook payload (session_id, transcript_path) from stdin,
  2. self-gates on project membership (silent no-op for unregistered sessions),
  3. extracts the assistant's text since the last user prompt -- INCLUDING
     tool-result summaries -- from the transcript jsonl,
  4. stashes it in the project's per-session pending-pre-text file.

The UserPromptSubmit hook consumes that file on the NEXT prompt, so a bare reply
like "yes" is logged with the agent's preceding message/plan as its pre-text
(truncated to the per-project pre_submission_capture_char_limit at consume time).

Always emits {} so unrelated sessions never see noise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _emit_empty_and_exit_silently() -> int:
    print(json.dumps({}))
    return 0


def _main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return _emit_empty_and_exit_silently()

    session_id = payload.get("session_id") or payload.get("sessionId")
    transcript_path = payload.get("transcript_path") or payload.get("transcriptPath")
    if not session_id or not transcript_path:
        return _emit_empty_and_exit_silently()

    from .project_identifier_resolver import resolve_project_id_for_session
    project_id = resolve_project_id_for_session(session_id)
    if project_id is None:
        return _emit_empty_and_exit_silently()  # not a registered project session

    transcript_file = Path(transcript_path)
    if not transcript_file.exists():
        return _emit_empty_and_exit_silently()

    from . import claude_cli_get_recent_agent_messages as extractor
    from .load_config import (
        project_directory_for,
        project_pending_pre_text_file_path,
    )

    events = list(extractor.parse_events(transcript_file))
    relevant_events = extractor.find_events_since_last_user_prompt(events)
    captured_pre_text = extractor.build_recent_agent_text_from_relevant_events(
        relevant_events,
        include_tool_calls=False,      # the CALL is noise; the RESULT is the signal
        include_tool_results=True,
        separator="\n\n",
        max_chars=None,                # writer truncates to per-project limit on consume
    )
    if not captured_pre_text:
        return _emit_empty_and_exit_silently()

    project_directory_for(project_id).mkdir(parents=True, exist_ok=True)
    project_pending_pre_text_file_path(project_id, session_id).write_text(captured_pre_text)
    return _emit_empty_and_exit_silently()


if __name__ == "__main__":
    try:
        sys.exit(_main())
    except Exception:
        sys.exit(_emit_empty_and_exit_silently())
