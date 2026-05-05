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


def _iter_balanced_brace_object_substrings_from_end(response_text: str):
    """Yield JSON-object substrings from the response, scanned right-to-left.

    For each '}' in the response (last to first), walk left tracking nesting
    depth and yield the substring from the matching '{' through this '}'.
    Skips braces inside JSON strings (handles escaped quotes).
    """
    closing_brace_positions = [i for i, ch in enumerate(response_text) if ch == "}"]
    for closing_index in reversed(closing_brace_positions):
        depth = 0
        inside_string_literal = False
        previous_char = ""
        for scan_index in range(closing_index, -1, -1):
            char_at_scan = response_text[scan_index]
            # Detect entering/leaving a JSON string literal (handle escaped quotes).
            if char_at_scan == '"':
                # Count preceding backslashes to decide if this quote is escaped.
                backslash_run_length = 0
                back = scan_index - 1
                while back >= 0 and response_text[back] == "\\":
                    backslash_run_length += 1
                    back -= 1
                if backslash_run_length % 2 == 0:
                    inside_string_literal = not inside_string_literal
            if inside_string_literal:
                continue
            if char_at_scan == "}":
                depth += 1
            elif char_at_scan == "{":
                depth -= 1
                if depth == 0:
                    yield response_text[scan_index : closing_index + 1]
                    break


def _extract_verdict_json_from_response(response_text: str) -> dict[str, Any]:
    """Find the rightmost valid JSON object in the response that contains 'ops'.

    Robust to: surrounding prose, markdown code fences, example JSON snippets
    embedded earlier in the reply, escaped quotes in string fields.
    """
    for candidate_substring in _iter_balanced_brace_object_substrings_from_end(response_text):
        try:
            parsed = json.loads(candidate_substring)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "ops" in parsed:
            return parsed
    # Fallback: rightmost valid JSON object even without "ops" key, so callers
    # can surface a useful error rather than a generic regex miss.
    for candidate_substring in _iter_balanced_brace_object_substrings_from_end(response_text):
        try:
            parsed = json.loads(candidate_substring)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"No valid JSON object found in reviewer response: {response_text[:300]}")


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
        "EXPLICITLY-SUPPORTED PATTERNS (do NOT reject for any of these reasons):\n"
        " (1) BRIEF CONFIRMATION: CITED SLICE may be a brief confirmation such as 'yes', "
        "'no', 'A', 'B', 'C', 'go', 'ok', 'do it', etc. The actual requirement is the "
        "conjunction of the agent's question (visible in PRE-INPUT CONTEXT, the ~2000 chars "
        "the agent said immediately before the user submitted) AND the user's confirmation. "
        "APPROVE when PRE-INPUT CONTEXT contains a clear question/proposal and the cited "
        "slice is an unambiguous affirmative/selection answer. Do NOT require the requirement "
        "statement to appear inside the user's submission text.\n"
        " (2) USER STATES THE REQUIREMENT DIRECTLY: if the CITED SLICE itself contains an "
        "unambiguous requirement statement (an instruction, rule, constraint, decision, "
        "preference), APPROVE -- the user is the source of truth. This holds EVEN IF the "
        "user's text partially contradicts, overrides, modifies, or sidesteps the agent's "
        "preceding question/proposal in PRE-INPUT CONTEXT. The pre-input is context, not a "
        "consistency check; user statements supersede prior agent framing. Common shapes: "
        "'yes and also X' / 'yes but X' / 'no, instead do X' / 'actually let's just X'. "
        "Treat the cited slice on its own merits as a requirement, ignore mismatch with "
        "PRE-INPUT CONTEXT.\n"
        "Only reject for substantive defects: cited slice is not actually a requirement "
        "(question, thinking-aloud, reaction with no directive content), char_range cuts "
        "off mid-meaning, or the operation does not match the cited slice.\n\n"
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
