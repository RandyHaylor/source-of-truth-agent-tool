"""Append a user submission (and prior assistant pre-text) to the project's rolling raw log.

Designed to be invoked from a UserPromptSubmit hook. Returns a dict suitable for
passing back as `additionalContext` to the AI agent so it knows the entry was logged.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    PRE_SUBMISSION_CAPTURE_CHAR_LIMIT,
    project_raw_input_log_file_path,
    project_directory_for,
)
from .cross_platform_file_lock import acquire_exclusive_file_lock
from .raw_input_log_entry_schema import RawInputLogEntry


def truncate_pre_text_to_capture_limit(prior_assistant_output_text: str) -> str:
    if len(prior_assistant_output_text) <= PRE_SUBMISSION_CAPTURE_CHAR_LIMIT:
        return prior_assistant_output_text
    return prior_assistant_output_text[-PRE_SUBMISSION_CAPTURE_CHAR_LIMIT:]


def append_submission_to_raw_input_log(
    project_id: str,
    session_id: str,
    submission_text: str,
    prior_assistant_output_text: str,
) -> dict[str, Any]:
    project_directory_for(project_id).mkdir(parents=True, exist_ok=True)
    log_file_path = project_raw_input_log_file_path(project_id)

    entry = RawInputLogEntry(
        entry_id=str(uuid.uuid4()),
        timestamp_iso=datetime.now(timezone.utc).isoformat(),
        pre_submission_content=truncate_pre_text_to_capture_limit(
            prior_assistant_output_text
        ),
        submission_text=submission_text,
    )

    with acquire_exclusive_file_lock(log_file_path):
        if log_file_path.exists():
            try:
                existing_log_data = json.loads(log_file_path.read_text())
            except json.JSONDecodeError:
                existing_log_data = {}
        else:
            existing_log_data = {}
        if not isinstance(existing_log_data, dict):
            existing_log_data = {}
        session_entries = existing_log_data.setdefault(session_id, [])
        session_entries.append(entry.to_json_dict())
        log_file_path.write_text(json.dumps(existing_log_data, indent=2))

    return {
        "entry_id": entry.entry_id,
        "timestamp_iso": entry.timestamp_iso,
        "session_id": session_id,
        "pre_text_char_count": len(entry.pre_submission_content),
        "additional_context_message": (
            f"[source-of-truth] Logged your submission at {entry.timestamp_iso} "
            f"as entry_id {entry.entry_id} for session_id {session_id}. "
            f"Pre-text captured: {len(entry.pre_submission_content)} chars. "
            f"Use raw_input_log_reader to retrieve quotes."
        ),
    }
