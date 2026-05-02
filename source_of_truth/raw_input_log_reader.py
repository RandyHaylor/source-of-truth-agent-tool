"""Read-only access to entries in a project's raw_input_log.json."""
from __future__ import annotations

import json
from typing import Optional

from .config import project_raw_input_log_file_path
from .raw_input_log_entry_schema import RawInputLogEntry


class RawLogEntryNotFoundError(LookupError):
    pass


class CharRangeOutOfBoundsError(ValueError):
    pass


def load_raw_log_for_project(project_id: str) -> dict[str, list[dict]]:
    log_file_path = project_raw_input_log_file_path(project_id)
    if not log_file_path.exists():
        return {}
    try:
        data = json.loads(log_file_path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def get_raw_log_entry(
    project_id: str, session_id: str, entry_id: str
) -> RawInputLogEntry:
    log_data = load_raw_log_for_project(project_id)
    session_entries = log_data.get(session_id)
    if not session_entries:
        raise RawLogEntryNotFoundError(
            f"No entries logged for session_id={session_id} in project={project_id}"
        )
    for raw_entry in session_entries:
        if raw_entry.get("entry_id") == entry_id:
            return RawInputLogEntry.from_json_dict(raw_entry)
    raise RawLogEntryNotFoundError(
        f"entry_id={entry_id} not found for session_id={session_id}"
    )


def resolve_quote_text_from_reference(
    project_id: str,
    session_id: str,
    entry_id: str,
    char_range: Optional[tuple[int, int]] = None,
) -> str:
    entry = get_raw_log_entry(project_id, session_id, entry_id)
    full_text = entry.submission_text
    if char_range is None:
        return full_text
    start_char_index, end_char_index = char_range
    if start_char_index < 0 or end_char_index > len(full_text) or start_char_index > end_char_index:
        raise CharRangeOutOfBoundsError(
            f"char_range {char_range} out of bounds for entry of length {len(full_text)}"
        )
    return full_text[start_char_index : end_char_index + 1]
