from __future__ import annotations

import copy

import pytest

from source_of_truth.requirements_tree_change_set_applier import (
    ChangeSetApplicationError,
    apply_change_set_to_tree,
)
from source_of_truth.requirements_tree_node_schema import RequirementsTree


def _build_tree_with_two_top_level_nodes_each_with_one_child() -> RequirementsTree:
    tree = RequirementsTree.empty_for_project("proj-x")
    add_top_a = {"op": "add_top_level", "raw_entry_reference": {"session_id": "s1", "entry_id": "e1"}}
    add_top_b = {"op": "add_top_level", "raw_entry_reference": {"session_id": "s1", "entry_id": "e2"}}
    tree = apply_change_set_to_tree(tree, [add_top_a, add_top_b])
    add_child_to_a = {"op": "add", "parent_id": tree.top_level_node_ids[0],
                      "raw_entry_reference": {"session_id": "s1", "entry_id": "e3"}}
    add_child_to_b = {"op": "add", "parent_id": tree.top_level_node_ids[1],
                      "raw_entry_reference": {"session_id": "s1", "entry_id": "e4"}}
    return apply_change_set_to_tree(tree, [add_child_to_a, add_child_to_b])


def test_add_top_level_creates_node_and_registers_at_top():
    tree = RequirementsTree.empty_for_project("p")
    new_tree = apply_change_set_to_tree(tree, [
        {"op": "add_top_level", "raw_entry_reference": {"session_id": "s", "entry_id": "e"}}
    ])
    assert len(new_tree.top_level_node_ids) == 1
    assert len(new_tree.nodes_by_id) == 1


def test_add_attaches_node_under_specified_parent():
    tree = _build_tree_with_two_top_level_nodes_each_with_one_child()
    parent_a = tree.top_level_node_ids[0]
    assert len(tree.nodes_by_id[parent_a].child_node_ids) == 1


def test_reparent_moves_node_between_parents_and_updates_lists():
    tree = _build_tree_with_two_top_level_nodes_each_with_one_child()
    parent_a, parent_b = tree.top_level_node_ids
    moving_node_id = tree.nodes_by_id[parent_a].child_node_ids[0]
    new_tree = apply_change_set_to_tree(tree, [
        {"op": "reparent", "node_id": moving_node_id, "new_parent_id": parent_b}
    ])
    assert moving_node_id not in new_tree.nodes_by_id[parent_a].child_node_ids
    assert moving_node_id in new_tree.nodes_by_id[parent_b].child_node_ids
    assert new_tree.nodes_by_id[moving_node_id].parent_id == parent_b


def test_remove_deletes_node_and_descendants():
    tree = _build_tree_with_two_top_level_nodes_each_with_one_child()
    parent_a = tree.top_level_node_ids[0]
    new_tree = apply_change_set_to_tree(tree, [{"op": "remove", "node_id": parent_a}])
    assert parent_a not in new_tree.nodes_by_id
    assert parent_a not in new_tree.top_level_node_ids
    # original child of A should also be gone
    assert len(new_tree.nodes_by_id) == 2  # the other parent + its child


def test_modify_reference_updates_quote_pointer():
    tree = _build_tree_with_two_top_level_nodes_each_with_one_child()
    target = tree.top_level_node_ids[0]
    new_tree = apply_change_set_to_tree(tree, [{
        "op": "modify_reference", "node_id": target,
        "raw_entry_reference": {"session_id": "s9", "entry_id": "e9"},
    }])
    assert new_tree.nodes_by_id[target].raw_entry_reference.session_id == "s9"


def test_reorder_children_requires_same_set_and_reorders():
    tree = _build_tree_with_two_top_level_nodes_each_with_one_child()
    parent_a = tree.top_level_node_ids[0]
    # Add a second child under A so reordering is meaningful.
    tree = apply_change_set_to_tree(tree, [{
        "op": "add", "parent_id": parent_a,
        "raw_entry_reference": {"session_id": "s", "entry_id": "e_extra"},
    }])
    children = list(tree.nodes_by_id[parent_a].child_node_ids)
    reversed_children = list(reversed(children))
    new_tree = apply_change_set_to_tree(tree, [{
        "op": "reorder_children", "parent_id": parent_a, "child_order": reversed_children,
    }])
    assert new_tree.nodes_by_id[parent_a].child_node_ids == reversed_children


def test_reorder_children_rejects_mismatched_set():
    tree = _build_tree_with_two_top_level_nodes_each_with_one_child()
    parent_a = tree.top_level_node_ids[0]
    with pytest.raises(ChangeSetApplicationError):
        apply_change_set_to_tree(tree, [{
            "op": "reorder_children", "parent_id": parent_a, "child_order": [99999],
        }])


def test_apply_change_set_does_not_mutate_input_tree():
    tree = _build_tree_with_two_top_level_nodes_each_with_one_child()
    snapshot_before = copy.deepcopy(tree.to_json_dict())
    apply_change_set_to_tree(tree, [{"op": "remove", "node_id": tree.top_level_node_ids[0]}])
    assert tree.to_json_dict() == snapshot_before
