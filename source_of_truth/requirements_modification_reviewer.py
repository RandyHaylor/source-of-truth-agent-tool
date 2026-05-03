"""Sends a change-set to the live reviewer session and parses a per-operation verdict.

Reviewer protocol:
  Reply with EXACTLY one JSON object containing one verdict per operation:
    {"ops": [{"index": 0, "approved": true, "reason": "..."},
             {"index": 1, "approved": false, "reason": "..."}],
     "message": "<overall summary, optional>"}
  The "message" field is an overall summary; per-op decisions live in "ops".

Performance note: every raw_input_reference in the change-set is resolved against
the on-disk raw input log and the resolved quote text + pre_submission_content
are inlined directly into the prompt, so the reviewer never needs to invoke
Read tools to verdict. This keeps the round-trip to a single Claude turn.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .raw_input_log_reader import (
    RawLogEntryNotFoundError,
    find_session_id_for_raw_input_id,
    get_raw_log_entry_by_raw_input_id,
    resolve_quote_text_from_reference,
)
from .reviewer_session_lifecycle_manager import ReviewerSessionLifecycleManager


@dataclass
class PerOperationVerdict:
    operation_index: int
    approved: bool
    reason: str = ""


@dataclass
class ReviewerVerdict:
    approved: bool                      # True iff EVERY op was approved
    message: str                        # overall summary the reviewer wrote
    per_operation_verdicts: list[PerOperationVerdict] = field(default_factory=list)
    raw_response_text: str = ""

    def approved_operation_indices(self) -> list[int]:
        return [v.operation_index for v in self.per_operation_verdicts if v.approved]

    def rejected_operation_indices_with_reasons(self) -> list[tuple[int, str]]:
        return [(v.operation_index, v.reason)
                for v in self.per_operation_verdicts if not v.approved]


# Greedy match for the outermost JSON-object candidate that contains "ops".
_VERDICT_JSON_OBJECT_REGEX = re.compile(r"\{.*\"ops\".*\}", re.DOTALL)


def _extract_verdict_json_from_response(response_text: str) -> dict[str, Any]:
    match = _VERDICT_JSON_OBJECT_REGEX.search(response_text)
    if not match:
        raise ValueError(f"No verdict JSON found in reviewer response: {response_text[:300]}")
    candidate_text = match.group(0)
    # Try progressively shorter prefixes ending in '}' so we find a parseable
    # object even if the regex over-matched into trailing prose.
    for trim_count in range(len(candidate_text), 0, -1):
        substring = candidate_text[:trim_count]
        if not substring.endswith("}"):
            continue
        try:
            parsed = json.loads(substring)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No valid verdict JSON parseable from response: {response_text[:300]}")


def _build_inline_resolved_context_for_change_set(
    project_id: str, change_set_json_dict: dict[str, Any]
) -> str:
    inlined_blocks: list[str] = []
    for op_index, operation in enumerate(change_set_json_dict.get("operations", [])):
        ref = operation.get("raw_input_reference")
        if not ref:
            inlined_blocks.append(
                f"--- op[{op_index}] op={operation.get('op')} (no raw_input_reference) ---"
            )
            continue
        raw_input_id = ref["raw_input_id"]
        char_range = tuple(ref["char_range"]) if ref.get("char_range") else None
        try:
            entry = get_raw_log_entry_by_raw_input_id(project_id, raw_input_id)
            session_id = find_session_id_for_raw_input_id(project_id, raw_input_id)
            quoted_text = resolve_quote_text_from_reference(
                project_id, raw_input_id, char_range
            )
        except (RawLogEntryNotFoundError, ValueError) as exc:
            inlined_blocks.append(
                f"--- op[{op_index}] RESOLUTION ERROR: {exc} ---"
            )
            continue
        inlined_blocks.append(
            f"--- op[{op_index}] op={operation.get('op')} raw_input_id={raw_input_id} session={session_id} ---\n"
            f"PRE-INPUT CONTEXT (what the agent had said before this raw input):\n"
            f"{entry.pre_submission_content}\n"
            f"FULL RAW INPUT:\n{entry.submission_text}\n"
            f"CITED SLICE (what this op claims as the requirement):\n{quoted_text}\n"
        )
    return "\n".join(inlined_blocks)


def _parse_per_operation_verdicts(
    verdict_payload: dict[str, Any], total_operation_count: int
) -> list[PerOperationVerdict]:
    raw_ops = verdict_payload.get("ops")
    if not isinstance(raw_ops, list):
        return []
    parsed: list[PerOperationVerdict] = []
    for raw in raw_ops:
        if not isinstance(raw, dict):
            continue
        index = raw.get("index")
        if not isinstance(index, int) or index < 0 or index >= total_operation_count:
            continue
        parsed.append(PerOperationVerdict(
            operation_index=index,
            approved=bool(raw.get("approved", False)),
            reason=str(raw.get("reason", "")),
        ))
    return parsed


def request_change_set_review(
    reviewer_lifecycle: ReviewerSessionLifecycleManager,
    change_set_json_dict: dict[str, Any],
    project_id: str,
) -> ReviewerVerdict:
    inline_context = _build_inline_resolved_context_for_change_set(
        project_id, change_set_json_dict
    )
    total_operation_count = len(change_set_json_dict.get("operations", []))
    prompt_text = (
        "Review fast. One bullet-style fact-check per op, then commit. "
        "Reply with EXACTLY one JSON object, nothing before/after, no markdown fence. "
        "Reason <=15 words. Message <=20 words.\n\n"
        f"OPS ({total_operation_count}):\n{json.dumps(change_set_json_dict.get('operations', []), indent=2)}\n\n"
        f"RESOLVED CONTEXT (quotes inlined; no Read needed):\n{inline_context}"
    )
    response_text = reviewer_lifecycle.send_prompt_with_rotation_on_exhaustion(prompt_text)
    try:
        verdict_payload = _extract_verdict_json_from_response(response_text)
    except (ValueError, json.JSONDecodeError) as exc:
        return ReviewerVerdict(
            approved=False,
            message=f"Could not parse reviewer verdict ({exc}); denying by default.",
            per_operation_verdicts=[],
            raw_response_text=response_text,
        )
    per_op = _parse_per_operation_verdicts(verdict_payload, total_operation_count)
    if not per_op:
        # Reviewer responded with valid JSON but no usable per-op verdicts;
        # fail closed rather than guess.
        return ReviewerVerdict(
            approved=False,
            message=(
                f"Reviewer response missing usable per-op verdicts: "
                f"{verdict_payload.get('message', '')}".strip()
            ),
            per_operation_verdicts=[],
            raw_response_text=response_text,
        )
    every_op_approved = (
        len(per_op) == total_operation_count
        and all(v.approved for v in per_op)
    )
    return ReviewerVerdict(
        approved=every_op_approved,
        message=str(verdict_payload.get("message", "")),
        per_operation_verdicts=per_op,
        raw_response_text=response_text,
    )
