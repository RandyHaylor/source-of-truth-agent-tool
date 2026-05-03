"""Builds the per-turn / per-subagent context injection text for the primary agent."""
from __future__ import annotations

import json

from .config import TOP_LEVEL_INJECTION_BLURB_TEMPLATE
from .requirements_tree_node_schema import RequirementsTree
from .requirements_tree_store import load_requirements_tree


def build_top_level_injection_text_for_project(project_id: str) -> str:
    tree = load_requirements_tree(project_id)
    top_level_summary = _summarize_top_level_for_injection(tree)
    return TOP_LEVEL_INJECTION_BLURB_TEMPLATE.format(
        top_level_node_json=json.dumps(top_level_summary, indent=2)
    )


def _summarize_top_level_for_injection(tree: RequirementsTree) -> dict:
    top_level_nodes = []
    for node_id in tree.top_level_node_ids:
        node = tree.nodes_by_id.get(node_id)
        if node is None:
            continue
        top_level_nodes.append({
            "node_id": node.node_id,
            "kind": node.kind,
            "child_count": len(node.child_node_ids),
            "has_reference": node.raw_input_reference is not None,
            "project_paths_count": len(node.project_paths) if node.project_paths else 0,
        })
    return {
        "project_id": tree.project_id,
        "top_level_nodes": top_level_nodes,
        "total_node_count": len(tree.nodes_by_id),
    }
