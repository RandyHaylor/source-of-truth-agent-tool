"""Builds the per-turn / per-subagent context injection text for the primary agent."""
from __future__ import annotations

from .compact_tree_renderer import render_tree_titles_only_indented
from .config import TOP_LEVEL_INJECTION_BLURB_TEMPLATE
from .requirements_tree_store import load_requirements_tree


def build_top_level_injection_text_for_project(project_id: str) -> str:
    tree = load_requirements_tree(project_id)
    tree_compact_text = render_tree_titles_only_indented(project_id, tree)
    return TOP_LEVEL_INJECTION_BLURB_TEMPLATE.format(tree_compact_text=tree_compact_text)
