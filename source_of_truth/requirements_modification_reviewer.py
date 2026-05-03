"""Sends a change-set to the live reviewer session and parses an approve/deny verdict.

Performance note: every raw_entry_reference in the change-set is resolved against
the on-disk raw input log and the resolved quote text + pre_submission_content
are inlined directly into the prompt, so the reviewer never needs to invoke
Read tools to verdict. This keeps the round-trip to a single Claude turn.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .raw_input_log_reader import (
    RawLogEntryNotFoundError,
    get_raw_log_entry,
    resolve_quote_text_from_reference,
)
from .reviewer_session_lifecycle_manager import ReviewerSessionLifecycleManager


@dataclass
class ReviewerVerdict:
    approved: bool
    message: str
    raw_response_text: str


_VERDICT_JSON_OBJECT_REGEX = re.compile(r"\{[^{}]*\"approved\"[^{}]*\}", re.DOTALL)


def _extract_verdict_json_from_response(response_text: str) -> dict[str, Any]:
    match = _VERDICT_JSON_OBJECT_REGEX.search(response_text)
    if not match:
        raise ValueError(f"No verdict JSON found in reviewer response: {response_text[:300]}")
    return json.loads(match.group(0))


def _build_inline_resolved_context_for_change_set(
    project_id: str, change_set_json_dict: dict[str, Any]
) -> str:
    inlined_blocks: list[str] = []
    for op_index, operation in enumerate(change_set_json_dict.get("operations", [])):
        ref = operation.get("raw_entry_reference")
        if not ref:
            continue
        session_id = ref["session_id"]
        entry_id = ref["entry_id"]
        char_range = tuple(ref["char_range"]) if ref.get("char_range") else None
        try:
            entry = get_raw_log_entry(project_id, session_id, entry_id)
            quoted_text = resolve_quote_text_from_reference(
                project_id, session_id, entry_id, char_range
            )
        except (RawLogEntryNotFoundError, ValueError) as exc:
            inlined_blocks.append(
                f"--- op[{op_index}] RESOLUTION ERROR: {exc} ---"
            )
            continue
        inlined_blocks.append(
            f"--- op[{op_index}] op={operation.get('op')} ---\n"
            f"PRE-INPUT CONTEXT (what the agent had said before this raw input):\n"
            f"{entry.pre_submission_content}\n"
            f"FULL RAW INPUT:\n{entry.submission_text}\n"
            f"CITED SLICE (what this op claims as the requirement):\n{quoted_text}\n"
        )
    return "\n".join(inlined_blocks)


def request_change_set_review(
    reviewer_lifecycle: ReviewerSessionLifecycleManager,
    change_set_json_dict: dict[str, Any],
    project_id: str,
) -> ReviewerVerdict:
    inline_context = _build_inline_resolved_context_for_change_set(
        project_id, change_set_json_dict
    )
    prompt_text = (
        "Please review the following requirements-tree change set. "
        "Reply with EXACTLY one JSON object on its own line as instructed in priming "
        "(no Read tools needed — all referenced quotes are inlined below).\n\n"
        f"CHANGE_SET:\n{json.dumps(change_set_json_dict, indent=2)}\n\n"
        f"RESOLVED CONTEXT FOR EACH OPERATION:\n{inline_context}\n"
    )
    response_text = reviewer_lifecycle.send_prompt_with_rotation_on_exhaustion(prompt_text)
    try:
        verdict_payload = _extract_verdict_json_from_response(response_text)
    except (ValueError, json.JSONDecodeError) as exc:
        return ReviewerVerdict(
            approved=False,
            message=f"Could not parse reviewer verdict ({exc}); denying by default.",
            raw_response_text=response_text,
        )
    return ReviewerVerdict(
        approved=bool(verdict_payload.get("approved", False)),
        message=str(verdict_payload.get("message", "")),
        raw_response_text=response_text,
    )
