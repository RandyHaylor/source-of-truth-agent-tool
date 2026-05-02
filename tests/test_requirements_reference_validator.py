from __future__ import annotations

import pytest

from source_of_truth.raw_input_log_writer import append_submission_to_raw_input_log
from source_of_truth.requirements_reference_validator import (
    ReferenceValidationError,
    validate_raw_entry_reference,
)


def test_rejects_missing_entry():
    with pytest.raises(ReferenceValidationError):
        validate_raw_entry_reference("proj-x", {"session_id": "no", "entry_id": "no"})


def test_accepts_short_submission_without_char_range():
    log_result = append_submission_to_raw_input_log("p", "s", "yes", "")
    validate_raw_entry_reference("p", {
        "session_id": "s", "entry_id": log_result["entry_id"],
    })


def test_requires_char_range_when_submission_exceeds_threshold():
    long_submission_text = "x" * 1000
    log_result = append_submission_to_raw_input_log("p", "s", long_submission_text, "")
    with pytest.raises(ReferenceValidationError):
        validate_raw_entry_reference("p", {
            "session_id": "s", "entry_id": log_result["entry_id"],
        })


def test_rejects_out_of_bounds_char_range():
    log_result = append_submission_to_raw_input_log("p", "s", "x" * 1000, "")
    with pytest.raises(ReferenceValidationError):
        validate_raw_entry_reference("p", {
            "session_id": "s", "entry_id": log_result["entry_id"],
            "char_range": [0, 5000],
        })


def test_accepts_valid_minimum_length_char_range():
    log_result = append_submission_to_raw_input_log("p", "s", "x" * 1000, "")
    validate_raw_entry_reference("p", {
        "session_id": "s", "entry_id": log_result["entry_id"],
        "char_range": [10, 10],
    })
