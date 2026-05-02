"""Public API surface exposed to the primary AI agent.

All mutations go through submit_requirements_tree_change_set, which:
  1. Validates references against the raw log.
  2. Asks the reviewer subagent for approval.
  3. Applies the change-set and writes the new tree atomically (only on approval).

Read endpoints (search, get_node_by_id, get_top_level_node) are unrestricted.
add_project_path / remove_project_path mutate the special project-paths node
WITHOUT going through the reviewer (paths are facts, validated by os.path.exists).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from .ai_cli_adapter_interface import AiCliAdapterInterface
from .config import (
    INTERACTION_TIME_AGENT_GUIDANCE,
    project_reviewer_thinking_log_file_path,
)
from .conversation_context_injector import build_top_level_injection_text_for_project
from .pending_messages_for_raw_input_sender import add_pending_message_for_raw_input_sender
from .requirements_modification_reviewer import (
    ReviewerVerdict,
    request_change_set_review,
)
from .requirements_reference_validator import (
    ReferenceValidationError,
    validate_change_set_references,
)
from .requirements_tree_change_set_applier import (
    ChangeSetApplicationError,
    apply_change_set_to_tree,
)
from .requirements_tree_change_set_schema import RequirementsTreeChangeSet
from .requirements_tree_node_schema import (
    PROJECT_PATHS_SPECIAL_NODE_KIND,
    RequirementsTree,
    RequirementsTreeNode,
)
from .requirements_tree_store import (
    load_requirements_tree,
    save_requirements_tree_atomically,
)
from .reviewer_session_lifecycle_manager import ReviewerSessionLifecycleManager


@dataclass
class ChangeSetSubmissionResult:
    approved: bool
    reviewer_message: str
    applied_operation_count: int
    message_for_raw_input_sender: str = ""
    reviewer_thinking_log_path: str = ""
    agent_guidance: str = INTERACTION_TIME_AGENT_GUIDANCE


class RequirementsTreeControlledApi:
    def __init__(self, project_id: str, ai_cli_adapter: AiCliAdapterInterface) -> None:
        self._project_id = project_id
        self._reviewer_lifecycle = ReviewerSessionLifecycleManager(project_id, ai_cli_adapter)

    # ----- Read endpoints -----

    def get_top_level_node(self) -> str:
        return build_top_level_injection_text_for_project(self._project_id)

    def get_node_by_id(
        self, node_id: int, include_children: bool = True
    ) -> Optional[dict[str, Any]]:
        tree = load_requirements_tree(self._project_id)
        node = tree.nodes_by_id.get(node_id)
        if node is None:
            return None
        result: dict[str, Any] = {
            "node": node.to_json_dict(),
            "agent_guidance": INTERACTION_TIME_AGENT_GUIDANCE,
        }
        if include_children:
            result["children"] = [
                tree.nodes_by_id[cid].to_json_dict()
                for cid in node.child_node_ids
                if cid in tree.nodes_by_id
            ]
        return result

    def search_requirements_nodes(self, query: str) -> dict[str, Any]:
        from .raw_input_log_reader import resolve_quote_text_from_reference
        tree = load_requirements_tree(self._project_id)
        query_lowered = query.lower()
        matches: list[dict[str, Any]] = []
        for node in tree.nodes_by_id.values():
            if node.raw_entry_reference is None:
                if any(query_lowered in p.lower() for p in node.project_paths):
                    matches.append(node.to_json_dict())
                continue
            try:
                quote_text = resolve_quote_text_from_reference(
                    self._project_id,
                    node.raw_entry_reference.session_id,
                    node.raw_entry_reference.entry_id,
                    tuple(node.raw_entry_reference.char_range)  # type: ignore[arg-type]
                    if node.raw_entry_reference.char_range else None,
                )
            except Exception:
                continue
            if query_lowered in quote_text.lower():
                matches.append(node.to_json_dict())
        return {"matches": matches, "agent_guidance": INTERACTION_TIME_AGENT_GUIDANCE}

    # ----- Mutating endpoints -----

    def submit_requirements_tree_change_set(
        self, change_set_json_dict: dict[str, Any]
    ) -> ChangeSetSubmissionResult:
        change_set = RequirementsTreeChangeSet.from_json_dict(change_set_json_dict)
        thinking_log_path = str(project_reviewer_thinking_log_file_path(self._project_id))
        operation_count = len(change_set.operations)

        try:
            validate_change_set_references(self._project_id, change_set.operations)
        except ReferenceValidationError as exc:
            rejection_message = (
                f"{operation_count} requirement op(s) REJECTED at local validation "
                f"(no reviewer call): {exc}"
            )
            add_pending_message_for_raw_input_sender(rejection_message, target_project_id=self._project_id)
            return ChangeSetSubmissionResult(
                approved=False,
                reviewer_message=f"Reference validation failed: {exc}",
                applied_operation_count=0,
                message_for_raw_input_sender=f"[source-of-truth] {rejection_message}",
                reviewer_thinking_log_path=thinking_log_path,
            )

        # Pre-call user notice — queued so the PostToolUse hook can emit it
        # via systemMessage (user-only, not echoed into the agent's context).
        in_flight_user_message = (
            f"Submitting {operation_count} requirement op(s) to the reviewer agent. "
            f"Live reviewer thoughts stream to: {thinking_log_path}"
        )
        add_pending_message_for_raw_input_sender(in_flight_user_message, target_project_id=self._project_id)

        verdict: ReviewerVerdict = request_change_set_review(
            self._reviewer_lifecycle, change_set.to_json_dict()
        )
        if not verdict.approved:
            rejection_message = (
                f"{operation_count} requirement op(s) REJECTED by reviewer. "
                f"Notes: {verdict.message}. Full thoughts: {thinking_log_path}"
            )
            add_pending_message_for_raw_input_sender(rejection_message, target_project_id=self._project_id)
            return ChangeSetSubmissionResult(
                approved=False,
                reviewer_message=verdict.message,
                applied_operation_count=0,
                message_for_raw_input_sender=f"[source-of-truth] {rejection_message}",
                reviewer_thinking_log_path=thinking_log_path,
            )
        try:
            current_tree = load_requirements_tree(self._project_id)
            new_tree = apply_change_set_to_tree(current_tree, change_set.operations)
            save_requirements_tree_atomically(new_tree)
        except ChangeSetApplicationError as exc:
            return ChangeSetSubmissionResult(
                approved=False,
                reviewer_message=f"Approved by reviewer but failed to apply: {exc}",
                applied_operation_count=0,
                message_for_raw_input_sender=(
                    f"[source-of-truth] Reviewer APPROVED but apply failed: {exc}. "
                    f"Tree unchanged. Reviewer thoughts: {thinking_log_path}"
                ),
                reviewer_thinking_log_path=thinking_log_path,
            )
        approval_message = (
            f"{operation_count} requirement op(s) APPROVED + applied. "
            f"Notes: {verdict.message}. Thoughts log: {thinking_log_path}"
        )
        add_pending_message_for_raw_input_sender(approval_message, target_project_id=self._project_id)
        return ChangeSetSubmissionResult(
            approved=True,
            reviewer_message=verdict.message,
            applied_operation_count=operation_count,
            message_for_raw_input_sender=f"[source-of-truth] {approval_message}",
            reviewer_thinking_log_path=thinking_log_path,
        )

    def add_project_path(self, filesystem_path: str) -> bool:
        if not os.path.exists(filesystem_path):
            raise ValueError(f"Refusing to add non-existent path: {filesystem_path}")
        tree = load_requirements_tree(self._project_id)
        project_paths_node = self._find_or_create_project_paths_node(tree)
        if filesystem_path in project_paths_node.project_paths:
            return False
        project_paths_node.project_paths.append(filesystem_path)
        save_requirements_tree_atomically(tree)
        return True

    def remove_project_path(self, filesystem_path: str) -> bool:
        tree = load_requirements_tree(self._project_id)
        project_paths_node = self._find_project_paths_node_or_none(tree)
        if project_paths_node is None or filesystem_path not in project_paths_node.project_paths:
            return False
        project_paths_node.project_paths.remove(filesystem_path)
        save_requirements_tree_atomically(tree)
        return True

    # ----- internal helpers -----

    def _find_project_paths_node_or_none(
        self, tree: RequirementsTree
    ) -> Optional[RequirementsTreeNode]:
        for node_id in tree.top_level_node_ids:
            node = tree.nodes_by_id.get(node_id)
            if node is not None and node.kind == PROJECT_PATHS_SPECIAL_NODE_KIND:
                return node
        return None

    def _find_or_create_project_paths_node(
        self, tree: RequirementsTree
    ) -> RequirementsTreeNode:
        existing = self._find_project_paths_node_or_none(tree)
        if existing is not None:
            return existing
        new_node_id = tree.next_node_id
        tree.next_node_id += 1
        new_node = RequirementsTreeNode(
            node_id=new_node_id,
            parent_id=None,
            kind=PROJECT_PATHS_SPECIAL_NODE_KIND,
        )
        tree.nodes_by_id[new_node_id] = new_node
        tree.top_level_node_ids.append(new_node_id)
        return new_node
