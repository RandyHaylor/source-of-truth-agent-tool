"""Sends a change-set to the live reviewer session and parses an approve/deny verdict."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

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


def request_change_set_review(
    reviewer_lifecycle: ReviewerSessionLifecycleManager,
    change_set_json_dict: dict[str, Any],
) -> ReviewerVerdict:
    prompt_text = (
        "Please review the following requirements-tree change set. "
        "Reply with a single JSON object on its own line as instructed in priming, "
        "then `<<<END_OF_RESPONSE>>>`.\n\n"
        f"CHANGE_SET:\n{json.dumps(change_set_json_dict, indent=2)}\n"
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
