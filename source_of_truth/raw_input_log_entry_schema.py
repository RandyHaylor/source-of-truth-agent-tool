"""Dataclass + JSON schema for one raw user-input log entry."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RawInputLogEntry:
    entry_id: str
    timestamp_iso: str
    pre_submission_content: str
    submission_text: str

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> "RawInputLogEntry":
        return cls(
            entry_id=raw["entry_id"],
            timestamp_iso=raw["timestamp_iso"],
            pre_submission_content=raw["pre_submission_content"],
            submission_text=raw["submission_text"],
        )


RAW_INPUT_LOG_ENTRY_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "RawInputLogEntry",
    "type": "object",
    "required": [
        "entry_id",
        "timestamp_iso",
        "pre_submission_content",
        "submission_text",
    ],
    "properties": {
        "entry_id": {"type": "string", "minLength": 1},
        "timestamp_iso": {"type": "string", "minLength": 1},
        "pre_submission_content": {"type": "string"},
        "submission_text": {"type": "string"},
    },
    "additionalProperties": False,
}
