"""Single CLI dispatcher: `source-of-truth <verb>` for ALL operations.

Setup verbs:
  init-project              <project_id>
  init-and-register         <session_id> <conversation_path>
  add-session               <project_id> <session_id> <conversation_path>
  set-mode                  <project_id> <live|none|deferred>

Runtime verbs (the agent calls these):
  submit-change-set         <project_id> --add-top-level <raw_input_id>
  submit-change-set         <project_id> @path/to/changeset.json
  submit-change-set         <project_id> -                  (read JSON from stdin)
  show-tree                 <project_id>
  get-node                  <project_id> <node_id>
  search-nodes              <project_id> <query>
  flush-deferred            <project_id>
  add-path                  <project_id> <filesystem_path>
  show-top-level            <project_id>

Hook entry-point:
  user-prompt-submit-hook   reads JSON from stdin, runs raw log writer,
                            emits {"hookSpecificOutput": {"additionalContext": ...}}
"""
from __future__ import annotations

import json
import sys

from .add_session_to_project_cli import add_session_to_project
from .ai_cli_adapter_claude_code import ClaudeCodeAdapter
from .config import (
    ALL_VALID_REVIEWER_MODES,
    ensure_root_directories_exist,
    load_project_settings,
    save_project_settings,
)
from .conversation_context_injector import build_top_level_injection_text_for_project
from .project_identifier_resolver import resolve_project_id_for_session
from .raw_input_log_writer import append_submission_to_raw_input_log
from .requirements_tree_controlled_api import RequirementsTreeControlledApi
from .requirements_tree_node_schema import RequirementsTree
from .requirements_tree_store import (
    load_requirements_tree,
    save_requirements_tree_atomically,
)


def _build_per_turn_additional_context_line(project_id: str, raw_input_id: int) -> str:
    """One-line action-shaped block injected on every user prompt."""
    return (
        f"source-of-truth: prompt logged id:{raw_input_id}, "
        f"add as requirement: source-of-truth submit-change-set {project_id} --add-top-level {raw_input_id}, "
        f"view project requirements: source-of-truth show-tree {project_id}, "
        f"read SKILL.md for more"
    )


def _handle_user_prompt_submit_hook() -> int:
    try:
        hook_input = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        hook_input = {}
    session_id = (
        hook_input.get("session_id")
        or hook_input.get("sessionId")
        or "unknown-session"
    )
    submission_text = (
        hook_input.get("prompt")
        or hook_input.get("user_prompt")
        or hook_input.get("userPrompt")
        or ""
    )
    prior_assistant_output_text = (
        hook_input.get("previous_assistant_output")
        or hook_input.get("priorAssistantOutput")
        or ""
    )

    project_id = resolve_project_id_for_session(session_id)
    if project_id is None:
        print(json.dumps({}))
        return 0

    log_result = append_submission_to_raw_input_log(
        project_id=project_id,
        session_id=session_id,
        submission_text=submission_text,
        prior_assistant_output_text=prior_assistant_output_text,
    )
    additional_context = _build_per_turn_additional_context_line(
        project_id=project_id,
        raw_input_id=log_result["raw_input_id"],
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": additional_context,
    }}))
    return 0


# ----- Setup verbs -----

def _handle_add_session(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: source-of-truth add-session <project_id> <session_id> <conversation_path>", file=sys.stderr)
        return 2
    project_id, session_id, conversation_path = argv
    was_added = add_session_to_project(project_id, session_id, conversation_path)
    print("added" if was_added else "already_present")
    return 0


def _handle_init_project(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: source-of-truth init-project <project_id>", file=sys.stderr)
        return 2
    project_id = argv[0]
    ensure_root_directories_exist()
    save_requirements_tree_atomically(RequirementsTree.empty_for_project(project_id))
    print(f"initialized project_id={project_id}")
    return 0


def _handle_init_and_register(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "Usage: source-of-truth init-and-register <session_id> <conversation_path>\n"
            "  project_id is set to <session_id> by convention.",
            file=sys.stderr,
        )
        return 2
    session_id, conversation_path = argv
    project_id = session_id
    ensure_root_directories_exist()
    save_requirements_tree_atomically(RequirementsTree.empty_for_project(project_id))
    was_added = add_session_to_project(project_id, session_id, conversation_path)
    print(
        f"initialized project_id={project_id}; "
        f"session={'added' if was_added else 'already_present'}"
    )
    return 0


def _handle_set_mode(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            f"Usage: source-of-truth set-mode <project_id> <{'|'.join(ALL_VALID_REVIEWER_MODES)}>",
            file=sys.stderr,
        )
        return 2
    project_id, requested_mode = argv
    if requested_mode not in ALL_VALID_REVIEWER_MODES:
        print(
            f"Invalid mode {requested_mode!r}. "
            f"Valid: {', '.join(ALL_VALID_REVIEWER_MODES)}",
            file=sys.stderr,
        )
        return 2
    settings = load_project_settings(project_id)
    settings.reviewer_mode_override = requested_mode
    save_project_settings(settings)
    print(f"project_id={project_id} reviewer_mode_override set to '{requested_mode}'")
    return 0


# ----- Runtime verbs (agent-facing) -----

def _resolve_change_set_payload_from_argv_after_project_id(
    payload_args: list[str], stdin_text_supplier=None
) -> dict:
    """Three input modes for submit-change-set:
       - --add-top-level <raw_input_id>     -> short form, builds a 1-op change-set
       - @path/to/file.json                 -> read file
       - -                                  -> read JSON from stdin
       - <raw json>                         -> parse argv[0] as JSON
    """
    if len(payload_args) >= 2 and payload_args[0] == "--add-top-level":
        try:
            raw_input_id = int(payload_args[1])
        except ValueError as exc:
            raise ValueError(f"--add-top-level expects integer raw_input_id; got {payload_args[1]!r}") from exc
        return {
            "submitter_rationale": f"Captured raw_input_id={raw_input_id} as a top-level requirement.",
            "operations": [{
                "op": "add_top_level",
                "raw_input_reference": {"raw_input_id": raw_input_id},
            }],
        }
    if len(payload_args) == 1 and payload_args[0] == "-":
        if stdin_text_supplier is None:
            stdin_text = sys.stdin.read()
        else:
            stdin_text = stdin_text_supplier()
        return json.loads(stdin_text)
    if len(payload_args) == 1 and payload_args[0].startswith("@"):
        with open(payload_args[0][1:]) as f:
            return json.loads(f.read())
    if len(payload_args) == 1:
        return json.loads(payload_args[0])
    raise ValueError(
        "submit-change-set payload must be one of: "
        "--add-top-level <raw_input_id> | @path/to/file.json | - (stdin) | <raw json>"
    )


def _handle_submit_change_set(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "Usage: source-of-truth submit-change-set <project_id> [--add-top-level <raw_input_id> | @path/to/file.json | - | <raw json>]",
            file=sys.stderr,
        )
        return 2
    project_id = argv[0]
    payload_args = argv[1:]
    try:
        change_set_dict = _resolve_change_set_payload_from_argv_after_project_id(payload_args)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"Could not build change-set payload: {exc}", file=sys.stderr)
        return 2
    api = RequirementsTreeControlledApi(project_id, ClaudeCodeAdapter())
    result = api.submit_requirements_tree_change_set(change_set_dict)
    print(json.dumps({
        "approved": result.approved,
        "applied_operation_count": result.applied_operation_count,
        "reviewer_message": result.reviewer_message,
        "message_for_raw_input_sender": result.message_for_raw_input_sender,
        "reviewer_thinking_log_path": result.reviewer_thinking_log_path,
    }, indent=2))
    return 0 if result.approved else 1


def _handle_show_tree(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: source-of-truth show-tree <project_id>", file=sys.stderr)
        return 2
    tree = load_requirements_tree(argv[0])
    print(json.dumps(tree.to_json_dict(), indent=2, sort_keys=True))
    return 0


def _handle_get_node(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: source-of-truth get-node <project_id> <node_id>", file=sys.stderr)
        return 2
    project_id, node_id_str = argv
    try:
        node_id = int(node_id_str)
    except ValueError:
        print(f"node_id must be integer; got {node_id_str!r}", file=sys.stderr)
        return 2
    api = RequirementsTreeControlledApi(project_id, ClaudeCodeAdapter())
    node_payload = api.get_node_by_id(node_id, include_children=True)
    if node_payload is None:
        print(json.dumps({"error": f"node_id {node_id} not found"}, indent=2))
        return 1
    print(json.dumps(node_payload, indent=2))
    return 0


def _handle_search_nodes(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: source-of-truth search-nodes <project_id> <query>", file=sys.stderr)
        return 2
    project_id, query = argv
    api = RequirementsTreeControlledApi(project_id, ClaudeCodeAdapter())
    print(json.dumps(api.search_requirements_nodes(query), indent=2))
    return 0


def _handle_flush_deferred(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: source-of-truth flush-deferred <project_id>", file=sys.stderr)
        return 2
    project_id = argv[0]
    api = RequirementsTreeControlledApi(project_id, ClaudeCodeAdapter())
    result = api.flush_deferred_change_sets_for_review()
    print(json.dumps({
        "approved": result.approved,
        "applied_operation_count": result.applied_operation_count,
        "reviewer_message": result.reviewer_message,
        "message_for_raw_input_sender": result.message_for_raw_input_sender,
    }, indent=2))
    return 0 if result.approved else 1


def _handle_add_path(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: source-of-truth add-path <project_id> <filesystem_path>", file=sys.stderr)
        return 2
    project_id, filesystem_path = argv
    api = RequirementsTreeControlledApi(project_id, ClaudeCodeAdapter())
    was_added = api.add_project_path(filesystem_path)
    print("added" if was_added else "already_present")
    return 0


def _handle_show_top_level(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: source-of-truth show-top-level <project_id>", file=sys.stderr)
        return 2
    print(build_top_level_injection_text_for_project(argv[0]))
    return 0


_VERB_DISPATCH_TABLE = {
    # hook
    "user-prompt-submit-hook": lambda argv: _handle_user_prompt_submit_hook(),
    # setup
    "init-project": _handle_init_project,
    "init-and-register": _handle_init_and_register,
    "add-session": _handle_add_session,
    "set-mode": _handle_set_mode,
    # runtime (agent-facing)
    "submit-change-set": _handle_submit_change_set,
    "show-tree": _handle_show_tree,
    "get-node": _handle_get_node,
    "search-nodes": _handle_search_nodes,
    "flush-deferred": _handle_flush_deferred,
    "add-path": _handle_add_path,
    "show-top-level": _handle_show_top_level,
}


def _main() -> int:
    if len(sys.argv) < 2:
        print(
            f"Usage: source-of-truth <verb> [...]\nVerbs: {', '.join(_VERB_DISPATCH_TABLE)}",
            file=sys.stderr,
        )
        return 2
    verb = sys.argv[1]
    handler = _VERB_DISPATCH_TABLE.get(verb)
    if handler is None:
        print(f"Unknown verb: {verb}", file=sys.stderr)
        return 2
    return handler(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(_main())
