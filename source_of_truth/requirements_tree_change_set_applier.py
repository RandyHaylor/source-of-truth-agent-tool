"""Pure function: apply an approved change-set to a tree and return the new tree.

No I/O. No validation of references (that is requirements_reference_validator's job).
Idempotent operations are not enforced here; the reviewer is the gate for semantics.
"""
from __future__ import annotations

import copy
from typing import Any

from .requirements_tree_change_set_schema import (
    OPERATION_KIND_ADD,
    OPERATION_KIND_ADD_GROUP,
    OPERATION_KIND_ADD_TOP_LEVEL,
    OPERATION_KIND_MODIFY_REFERENCE,
    OPERATION_KIND_REMOVE,
    OPERATION_KIND_REORDER_CHILDREN,
    OPERATION_KIND_REPARENT,
)
from .requirements_tree_node_schema import (
    GROUP_NODE_KIND,
    QUOTE_REFERENCE_NODE_KIND,
    TOP_LEVEL_PARENT_SENTINEL,
    RawInputReference,
    RequirementsTree,
    RequirementsTreeNode,
    _coerce_node_id_to_string,
    _coerce_parent_id_to_string_with_top_level_sentinel,
    letter_id_for_index,
)


class ChangeSetApplicationError(ValueError):
    pass


def _allocate_new_quote_leaf_node_id(tree: RequirementsTree) -> str:
    new_id_string = str(tree.next_node_id)
    tree.next_node_id += 1
    return new_id_string


def _allocate_new_group_letter_node_id(tree: RequirementsTree) -> str:
    new_id_string = letter_id_for_index(tree.next_group_letter_index)
    tree.next_group_letter_index += 1
    return new_id_string


def _require_node(tree: RequirementsTree, node_id: str) -> RequirementsTreeNode:
    if node_id not in tree.nodes_by_id:
        raise ChangeSetApplicationError(f"node_id {node_id!r} does not exist")
    return tree.nodes_by_id[node_id]


def apply_change_set_to_tree(
    current_tree: RequirementsTree, change_set_operations: list[dict[str, Any]]
) -> RequirementsTree:
    new_tree = RequirementsTree.from_json_dict(copy.deepcopy(current_tree.to_json_dict()))

    for operation in change_set_operations:
        op_kind = operation["op"]

        if op_kind == OPERATION_KIND_ADD:
            # parent_id of TOP_LEVEL_PARENT_SENTINEL ("0") means add at root with no parent node lookup.
            requested_parent_id = _coerce_parent_id_to_string_with_top_level_sentinel(
                operation.get("parent_id")
            )
            if requested_parent_id != TOP_LEVEL_PARENT_SENTINEL:
                parent_node = _require_node(new_tree, requested_parent_id)
            else:
                parent_node = None
            new_node_id = _allocate_new_quote_leaf_node_id(new_tree)
            new_tree.nodes_by_id[new_node_id] = RequirementsTreeNode(
                node_id=new_node_id,
                parent_id=requested_parent_id,
                kind=QUOTE_REFERENCE_NODE_KIND,
                raw_input_reference=RawInputReference.from_json_dict(
                    operation["raw_input_reference"]
                ),
                short_neutral_title=operation.get("short_neutral_title", ""),
            )
            if parent_node is not None:
                parent_node.child_node_ids.append(new_node_id)

        elif op_kind == OPERATION_KIND_ADD_TOP_LEVEL:
            # Legacy op kind: still supported in the applier so existing change-sets
            # in flight don't break; T7 will remove this entirely.
            new_node_id = _allocate_new_quote_leaf_node_id(new_tree)
            new_tree.nodes_by_id[new_node_id] = RequirementsTreeNode(
                node_id=new_node_id,
                parent_id=TOP_LEVEL_PARENT_SENTINEL,
                kind=QUOTE_REFERENCE_NODE_KIND,
                raw_input_reference=RawInputReference.from_json_dict(
                    operation["raw_input_reference"]
                ),
                short_neutral_title=operation.get("short_neutral_title", ""),
            )

        elif op_kind == OPERATION_KIND_ADD_GROUP:
            requested_parent_id = _coerce_parent_id_to_string_with_top_level_sentinel(
                operation.get("parent_id")
            )
            if requested_parent_id != TOP_LEVEL_PARENT_SENTINEL:
                parent_node = _require_node(new_tree, requested_parent_id)
            else:
                parent_node = None
            new_group_node_id = _allocate_new_group_letter_node_id(new_tree)
            new_tree.nodes_by_id[new_group_node_id] = RequirementsTreeNode(
                node_id=new_group_node_id,
                parent_id=requested_parent_id,
                kind=GROUP_NODE_KIND,
                short_neutral_title=operation.get("short_neutral_title", ""),
            )
            if parent_node is not None:
                parent_node.child_node_ids.append(new_group_node_id)

        elif op_kind == OPERATION_KIND_REPARENT:
            target_node_id = _coerce_node_id_to_string(operation["node_id"])
            new_parent_id = _coerce_parent_id_to_string_with_top_level_sentinel(
                operation.get("new_parent_id")
            )
            node = _require_node(new_tree, target_node_id)
            old_parent_id = node.parent_id
            if old_parent_id != TOP_LEVEL_PARENT_SENTINEL:
                old_parent = _require_node(new_tree, old_parent_id)
                if target_node_id in old_parent.child_node_ids:
                    old_parent.child_node_ids.remove(target_node_id)
            node.parent_id = new_parent_id
            if new_parent_id != TOP_LEVEL_PARENT_SENTINEL:
                new_parent = _require_node(new_tree, new_parent_id)
                new_parent.child_node_ids.append(target_node_id)

        elif op_kind == OPERATION_KIND_REMOVE:
            target_node_id = _coerce_node_id_to_string(operation["node_id"])
            node = _require_node(new_tree, target_node_id)
            ids_to_remove: list[str] = []
            stack = [target_node_id]
            while stack:
                current = stack.pop()
                ids_to_remove.append(current)
                stack.extend(new_tree.nodes_by_id[current].child_node_ids)
            if node.parent_id != TOP_LEVEL_PARENT_SENTINEL:
                parent_node = _require_node(new_tree, node.parent_id)
                if target_node_id in parent_node.child_node_ids:
                    parent_node.child_node_ids.remove(target_node_id)
            for nid in ids_to_remove:
                new_tree.nodes_by_id.pop(nid, None)

        elif op_kind == OPERATION_KIND_MODIFY_REFERENCE:
            target_node_id = _coerce_node_id_to_string(operation["node_id"])
            node = _require_node(new_tree, target_node_id)
            if node.kind != QUOTE_REFERENCE_NODE_KIND:
                raise ChangeSetApplicationError(
                    f"modify_reference invalid on non-quote node {target_node_id} (kind={node.kind})"
                )
            node.raw_input_reference = RawInputReference.from_json_dict(
                operation["raw_input_reference"]
            )

        elif op_kind == OPERATION_KIND_REORDER_CHILDREN:
            requested_parent_id = _coerce_parent_id_to_string_with_top_level_sentinel(
                operation["parent_id"]
            )
            new_child_order = [_coerce_node_id_to_string(c) for c in operation["child_order"]]
            parent_node = _require_node(new_tree, requested_parent_id)
            if sorted(new_child_order) != sorted(parent_node.child_node_ids):
                raise ChangeSetApplicationError(
                    f"reorder_children for parent {requested_parent_id} must contain the exact "
                    f"same child ids; got {new_child_order} vs {parent_node.child_node_ids}"
                )
            parent_node.child_node_ids = new_child_order

        else:
            raise ChangeSetApplicationError(f"Unknown op kind: {op_kind}")

    return new_tree


def apply_change_set_to_tree_with_per_op_isolation(
    current_tree: RequirementsTree, change_set_operations: list[dict[str, Any]]
) -> tuple[RequirementsTree, list[dict[str, Any]]]:
    """Apply each op individually; skip failures; return (final_tree, per_op_outcomes).

    Each entry in per_op_outcomes is a dict with keys:
      - "operation_index": position in the input list
      - "applied":         True if the op was applied, False if skipped
      - "error":           the ChangeSetApplicationError message (only present if not applied)
    """
    running_tree = RequirementsTree.from_json_dict(
        copy.deepcopy(current_tree.to_json_dict())
    )
    per_op_outcomes: list[dict[str, Any]] = []
    for op_index, single_operation in enumerate(change_set_operations):
        try:
            running_tree = apply_change_set_to_tree(running_tree, [single_operation])
            per_op_outcomes.append({"operation_index": op_index, "applied": True})
        except ChangeSetApplicationError as exc:
            per_op_outcomes.append({
                "operation_index": op_index,
                "applied": False,
                "error": str(exc),
            })
    return running_tree, per_op_outcomes
