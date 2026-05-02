"""Validates raw-entry references in change-set operations against the raw log on disk."""
from __future__ import annotations

from typing import Any

from .config import CHAR_RANGE_REQUIRED_THRESHOLD, MIN_CHAR_RANGE_LENGTH
from .raw_input_log_reader import (
    RawLogEntryNotFoundError,
    get_raw_log_entry,
)


class ReferenceValidationError(ValueError):
    pass


def validate_raw_entry_reference(
    project_id: str, raw_entry_reference: dict[str, Any]
) -> None:
    session_id = raw_entry_reference.get("session_id")
    entry_id = raw_entry_reference.get("entry_id")
    char_range = raw_entry_reference.get("char_range")
    if not session_id or not entry_id:
        raise ReferenceValidationError(
            f"raw_entry_reference missing session_id or entry_id: {raw_entry_reference}"
        )
    try:
        entry = get_raw_log_entry(project_id, session_id, entry_id)
    except RawLogEntryNotFoundError as exc:
        raise ReferenceValidationError(str(exc)) from exc

    submission_text_length = len(entry.submission_text)

    if char_range is None:
        if submission_text_length > CHAR_RANGE_REQUIRED_THRESHOLD:
            raise ReferenceValidationError(
                f"submission_text length {submission_text_length} exceeds "
                f"{CHAR_RANGE_REQUIRED_THRESHOLD}; char_range is required."
            )
        return

    if not (isinstance(char_range, list) and len(char_range) == 2):
        raise ReferenceValidationError(f"char_range must be [start, end]; got {char_range}")
    start_char_index, end_char_index = char_range
    if not (isinstance(start_char_index, int) and isinstance(end_char_index, int)):
        raise ReferenceValidationError(f"char_range entries must be integers; got {char_range}")
    if start_char_index < 0 or end_char_index >= submission_text_length:
        raise ReferenceValidationError(
            f"char_range {char_range} out of bounds for entry of length {submission_text_length}"
        )
    if end_char_index < start_char_index:
        raise ReferenceValidationError(f"char_range end < start: {char_range}")
    range_length = (end_char_index - start_char_index) + 1
    if range_length < MIN_CHAR_RANGE_LENGTH:
        raise ReferenceValidationError(
            f"char_range length {range_length} below minimum {MIN_CHAR_RANGE_LENGTH}"
        )


def validate_change_set_references(
    project_id: str, change_set_operations: list[dict[str, Any]]
) -> None:
    for operation in change_set_operations:
        if "raw_entry_reference" in operation and operation["raw_entry_reference"] is not None:
            validate_raw_entry_reference(project_id, operation["raw_entry_reference"])
