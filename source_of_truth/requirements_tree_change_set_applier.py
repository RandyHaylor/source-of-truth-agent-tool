"""Pure function: apply an approved change-set to a tree and return the new tree.

No I/O. No validation of references (that is requirements_reference_validator's job).
Idempotent operations are not enforced here; the reviewer is the gate for semantics.
"""
from __future__ import annotations

import copy
from typing import Any

from .requirements_tree_change_set_schema import (
    OPERATION_KIND_ADD,
    OPERATION_KIND_ADD_TOP_LEVEL,
    OPERATION_KIND_MODIFY_REFERENCE,
    OPERATION_KIND_REMOVE,
    OPERATION_KIND_REORDER_CHILDREN,
    OPERATION_KIND_REPARENT,
)
from .requirements_tree_node_schema import (
    QUOTE_REFERENCE_NODE_KIND,
    RawInputReference,
    RequirementsTree,
    RequirementsTreeNode,
)


class ChangeSetApplicationError(ValueError):
    pass


def _allocate_new_node_id(tree: RequirementsTree) -> int:
    new_id = tree.next_node_id
    tree.next_node_id += 1
    return new_id


def _require_node(tree: RequirementsTree, node_id: int) -> RequirementsTreeNode:
    if node_id not in tree.nodes_by_id:
        raise ChangeSetApplicationError(f"node_id {node_id} does not exist")
    return tree.nodes_by_id[node_id]


def apply_change_set_to_tree(
    current_tree: RequirementsTree, change_set_operations: list[dict[str, Any]]
) -> RequirementsTree:
    new_tree = RequirementsTree.from_json_dict(copy.deepcopy(current_tree.to_json_dict()))

    for operation in change_set_operations:
        op_kind = operation["op"]

        if op_kind == OPERATION_KIND_ADD:
            parent_id = operation["parent_id"]
            parent_node = _require_node(new_tree, parent_id)
            new_node_id = _allocate_new_node_id(new_tree)
            new_tree.nodes_by_id[new_node_id] = RequirementsTreeNode(
                node_id=new_node_id,
                parent_id=parent_id,
                kind=QUOTE_REFERENCE_NODE_KIND,
                raw_input_reference=RawInputReference.from_json_dict(
                    operation["raw_input_reference"]
                ),
            )
            parent_node.child_node_ids.append(new_node_id)

        elif op_kind == OPERATION_KIND_ADD_TOP_LEVEL:
            new_node_id = _allocate_new_node_id(new_tree)
            new_tree.nodes_by_id[new_node_id] = RequirementsTreeNode(
                node_id=new_node_id,
                parent_id=None,
                kind=QUOTE_REFERENCE_NODE_KIND,
                raw_input_reference=RawInputReference.from_json_dict(
                    operation["raw_input_reference"]
                ),
            )
            new_tree.top_level_node_ids.append(new_node_id)

        elif op_kind == OPERATION_KIND_REPARENT:
            node_id = operation["node_id"]
            new_parent_id = operation["new_parent_id"]
            node = _require_node(new_tree, node_id)
            old_parent_id = node.parent_id
            if old_parent_id is None:
                if node_id in new_tree.top_level_node_ids:
                    new_tree.top_level_node_ids.remove(node_id)
            else:
                old_parent = _require_node(new_tree, old_parent_id)
                if node_id in old_parent.child_node_ids:
                    old_parent.child_node_ids.remove(node_id)
            node.parent_id = new_parent_id
            if new_parent_id is None:
                new_tree.top_level_node_ids.append(node_id)
            else:
                new_parent = _require_node(new_tree, new_parent_id)
                new_parent.child_node_ids.append(node_id)

        elif op_kind == OPERATION_KIND_REMOVE:
            node_id = operation["node_id"]
            node = _require_node(new_tree, node_id)
            ids_to_remove = []
            stack = [node_id]
            while stack:
                current = stack.pop()
                ids_to_remove.append(current)
                stack.extend(new_tree.nodes_by_id[current].child_node_ids)
            if node.parent_id is None:
                if node_id in new_tree.top_level_node_ids:
                    new_tree.top_level_node_ids.remove(node_id)
            else:
                parent_node = _require_node(new_tree, node.parent_id)
                if node_id in parent_node.child_node_ids:
                    parent_node.child_node_ids.remove(node_id)
            for nid in ids_to_remove:
                new_tree.nodes_by_id.pop(nid, None)

        elif op_kind == OPERATION_KIND_MODIFY_REFERENCE:
            node_id = operation["node_id"]
            node = _require_node(new_tree, node_id)
            if node.kind != QUOTE_REFERENCE_NODE_KIND:
                raise ChangeSetApplicationError(
                    f"modify_reference invalid on non-quote node {node_id} (kind={node.kind})"
                )
            node.raw_input_reference = RawInputReference.from_json_dict(
                operation["raw_input_reference"]
            )

        elif op_kind == OPERATION_KIND_REORDER_CHILDREN:
            parent_id = operation["parent_id"]
            new_child_order = list(operation["child_order"])
            parent_node = _require_node(new_tree, parent_id)
            if sorted(new_child_order) != sorted(parent_node.child_node_ids):
                raise ChangeSetApplicationError(
                    f"reorder_children for parent {parent_id} must contain the exact "
                    f"same child ids; got {new_child_order} vs {parent_node.child_node_ids}"
                )
            parent_node.child_node_ids = new_child_order

        else:
            raise ChangeSetApplicationError(f"Unknown op kind: {op_kind}")

    return new_tree
