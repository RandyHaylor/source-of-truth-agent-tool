"""Read-only access to entries in a project's raw_input_log.json by raw_input_id."""
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


def get_raw_log_entry_by_raw_input_id(
    project_id: str, raw_input_id: int
) -> RawInputLogEntry:
    log_data = load_raw_log_for_project(project_id)
    for session_entries in log_data.values():
        for raw_entry in session_entries:
            if int(raw_entry.get("raw_input_id", -1)) == raw_input_id:
                return RawInputLogEntry.from_json_dict(raw_entry)
    raise RawLogEntryNotFoundError(
        f"raw_input_id={raw_input_id} not found in project={project_id}"
    )


def find_session_id_for_raw_input_id(
    project_id: str, raw_input_id: int
) -> str:
    log_data = load_raw_log_for_project(project_id)
    for session_id, session_entries in log_data.items():
        for raw_entry in session_entries:
            if int(raw_entry.get("raw_input_id", -1)) == raw_input_id:
                return session_id
    raise RawLogEntryNotFoundError(
        f"raw_input_id={raw_input_id} not found in project={project_id}"
    )


def resolve_quote_text_from_reference(
    project_id: str,
    raw_input_id: int,
    char_range: Optional[tuple[int, int]] = None,
) -> str:
    entry = get_raw_log_entry_by_raw_input_id(project_id, raw_input_id)
    full_text = entry.submission_text
    if char_range is None:
        return full_text
    start_char_index, end_char_index = char_range
    if start_char_index < 0 or end_char_index >= len(full_text) or start_char_index > end_char_index:
        raise CharRangeOutOfBoundsError(
            f"char_range {char_range} out of bounds for entry of length {len(full_text)}"
        )
    return full_text[start_char_index : end_char_index + 1]
