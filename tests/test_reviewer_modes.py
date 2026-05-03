"""Cover the three reviewer modes: live, none, deferred."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from source_of_truth.ai_cli_adapter_interface import (
    AiCliAdapterInterface,
    PersistentReviewerSessionHandle,
)
from source_of_truth.config import (
    REVIEWER_MODE_DEFER_UNTIL_FLUSH,
    REVIEWER_MODE_NO_REVIEWER_DIRECT_APPLY,
    GlobalSettings,
    ProjectSettings,
    save_global_settings,
    save_project_settings,
)
from source_of_truth.deferred_change_sets_queue import (
    count_pending_deferred_change_sets,
    read_and_clear_all_deferred_change_sets,
)
from source_of_truth.raw_input_log_writer import append_submission_to_raw_input_log
from source_of_truth.requirements_tree_controlled_api import (
    RequirementsTreeControlledApi,
)
from source_of_truth.requirements_tree_store import load_requirements_tree


class _StubReviewerHandle(PersistentReviewerSessionHandle):
    @property
    def session_id(self): return "stub-reviewer"
    def send_prompt_and_await_response(self, prompt_text): return ""
    def is_alive(self): return True
    def terminate(self): pass


class _StubAdapter(AiCliAdapterInterface):
    def get_current_session_id(self): return "stub-sess"
    def register_user_prompt_submit_hook(self, hook_callable): pass
    def inject_into_next_user_turn(self, injection_text): pass
    def inject_into_subagent_spawn(self, injection_text): pass
    def spawn_persistent_reviewer_session(self, **kwargs): return _StubReviewerHandle()


def _seed_one_short_raw_entry(project_id: str, session_id: str = "s") -> str:
    log_result = append_submission_to_raw_input_log(project_id, session_id, "yes", "")
    return log_result["entry_id"]


def _build_one_op_change_set(session_id: str, entry_id: str) -> dict:
    return {
        "submitter_rationale": "test",
        "operations": [{
            "op": "add_top_level",
            "raw_entry_reference": {"session_id": session_id, "entry_id": entry_id},
        }],
    }


def test_no_reviewer_mode_applies_change_set_directly_without_calling_reviewer():
    save_project_settings(ProjectSettings(
        project_id="p-no-rev",
        reviewer_mode_override=REVIEWER_MODE_NO_REVIEWER_DIRECT_APPLY,
    ))
    entry_id = _seed_one_short_raw_entry("p-no-rev", "s")
    api = RequirementsTreeControlledApi("p-no-rev", _StubAdapter())

    with patch("source_of_truth.requirements_tree_controlled_api.request_change_set_review") as mock_review:
        result = api.submit_requirements_tree_change_set(
            _build_one_op_change_set("s", entry_id)
        )
        assert mock_review.call_count == 0  # reviewer NEVER called

    assert result.approved is True
    assert result.applied_operation_count == 1
    tree = load_requirements_tree("p-no-rev")
    assert len(tree.nodes_by_id) == 1


def test_deferred_mode_queues_change_set_without_calling_reviewer_or_applying():
    save_project_settings(ProjectSettings(
        project_id="p-defer",
        reviewer_mode_override=REVIEWER_MODE_DEFER_UNTIL_FLUSH,
    ))
    entry_id = _seed_one_short_raw_entry("p-defer", "s")
    api = RequirementsTreeControlledApi("p-defer", _StubAdapter())

    with patch("source_of_truth.requirements_tree_controlled_api.request_change_set_review") as mock_review:
        result = api.submit_requirements_tree_change_set(
            _build_one_op_change_set("s", entry_id)
        )
        assert mock_review.call_count == 0

    assert result.approved is False
    assert "DEFERRED" in result.message_for_raw_input_sender
    assert count_pending_deferred_change_sets("p-defer") == 1
    tree = load_requirements_tree("p-defer")
    assert len(tree.nodes_by_id) == 0


def test_deferred_flush_calls_reviewer_once_with_merged_ops_and_applies_on_approval():
    from source_of_truth.requirements_modification_reviewer import ReviewerVerdict

    save_project_settings(ProjectSettings(
        project_id="p-defer-flush",
        reviewer_mode_override=REVIEWER_MODE_DEFER_UNTIL_FLUSH,
    ))
    entry_a = _seed_one_short_raw_entry("p-defer-flush", "s")
    entry_b = _seed_one_short_raw_entry("p-defer-flush", "s")
    api = RequirementsTreeControlledApi("p-defer-flush", _StubAdapter())
    api.submit_requirements_tree_change_set(_build_one_op_change_set("s", entry_a))
    api.submit_requirements_tree_change_set(_build_one_op_change_set("s", entry_b))
    assert count_pending_deferred_change_sets("p-defer-flush") == 2

    with patch(
        "source_of_truth.requirements_tree_controlled_api.request_change_set_review",
        return_value=ReviewerVerdict(approved=True, message="ok", raw_response_text=""),
    ) as mock_review:
        flush_result = api.flush_deferred_change_sets_for_review()

    assert mock_review.call_count == 1
    merged_payload_passed_to_reviewer = mock_review.call_args[0][1]
    assert len(merged_payload_passed_to_reviewer["operations"]) == 2
    assert flush_result.approved is True
    assert flush_result.applied_operation_count == 2
    assert count_pending_deferred_change_sets("p-defer-flush") == 0
    tree = load_requirements_tree("p-defer-flush")
    assert len(tree.nodes_by_id) == 2


def test_deferred_flush_with_empty_queue_returns_no_op_success():
    save_project_settings(ProjectSettings(
        project_id="p-empty-flush",
        reviewer_mode_override=REVIEWER_MODE_DEFER_UNTIL_FLUSH,
    ))
    api = RequirementsTreeControlledApi("p-empty-flush", _StubAdapter())
    with patch("source_of_truth.requirements_tree_controlled_api.request_change_set_review") as mock_review:
        result = api.flush_deferred_change_sets_for_review()
        assert mock_review.call_count == 0
    assert result.approved is True
    assert result.applied_operation_count == 0


def test_deferred_flush_rejection_keeps_tree_unchanged_and_does_not_requeue():
    from source_of_truth.requirements_modification_reviewer import ReviewerVerdict

    save_project_settings(ProjectSettings(
        project_id="p-defer-reject",
        reviewer_mode_override=REVIEWER_MODE_DEFER_UNTIL_FLUSH,
    ))
    entry_id = _seed_one_short_raw_entry("p-defer-reject", "s")
    api = RequirementsTreeControlledApi("p-defer-reject", _StubAdapter())
    api.submit_requirements_tree_change_set(_build_one_op_change_set("s", entry_id))

    with patch(
        "source_of_truth.requirements_tree_controlled_api.request_change_set_review",
        return_value=ReviewerVerdict(approved=False, message="nope", raw_response_text=""),
    ):
        result = api.flush_deferred_change_sets_for_review()

    assert result.approved is False
    assert "REJECTED" in result.message_for_raw_input_sender
    tree = load_requirements_tree("p-defer-reject")
    assert len(tree.nodes_by_id) == 0
    # Queue stays drained even on rejection (would otherwise grow unbounded).
    assert count_pending_deferred_change_sets("p-defer-reject") == 0
