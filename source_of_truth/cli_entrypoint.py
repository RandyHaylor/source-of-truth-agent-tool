"""Single CLI dispatcher: `sot <verb>` for manual ops AND the hook entry-point.

Verbs:
  user-prompt-submit-hook   reads JSON from stdin, runs raw log writer + injection,
                            emits {"hookSpecificOutput": {"additionalContext": ...}}
  add-session               <project_id> <session_id> <conversation_path>
  add-path                  <project_id> <filesystem_path>
  show-top-level            <project_id>
  init-project              <project_id>
"""
from __future__ import annotations

import json
import sys

from .add_session_to_project_cli import add_session_to_project
from .ai_cli_adapter_claude_code import ClaudeCodeAdapter
from .config import ensure_root_directories_exist
from .conversation_context_injector import build_top_level_injection_text_for_project
from .project_identifier_resolver import resolve_project_id_for_session
from .raw_input_log_writer import append_submission_to_raw_input_log
from .requirements_tree_controlled_api import RequirementsTreeControlledApi
from .requirements_tree_node_schema import RequirementsTree
from .requirements_tree_store import save_requirements_tree_atomically


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
        # Not a source-of-truth session; do nothing (gating).
        print(json.dumps({}))
        return 0

    log_result = append_submission_to_raw_input_log(
        project_id=project_id,
        session_id=session_id,
        submission_text=submission_text,
        prior_assistant_output_text=prior_assistant_output_text,
    )
    injection_text = build_top_level_injection_text_for_project(project_id)
    additional_context = (
        f"{log_result['additional_context_message']}\n\n{injection_text}"
    )
    print(json.dumps({"hookSpecificOutput": {"additionalContext": additional_context}}))
    return 0


def _handle_add_session(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: sot add-session <project_id> <session_id> <conversation_path>", file=sys.stderr)
        return 2
    project_id, session_id, conversation_path = argv
    was_added = add_session_to_project(project_id, session_id, conversation_path)
    print("added" if was_added else "already_present")
    return 0


def _handle_add_path(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: sot add-path <project_id> <filesystem_path>", file=sys.stderr)
        return 2
    project_id, filesystem_path = argv
    api = RequirementsTreeControlledApi(project_id, ClaudeCodeAdapter())
    was_added = api.add_project_path(filesystem_path)
    print("added" if was_added else "already_present")
    return 0


def _handle_show_top_level(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: sot show-top-level <project_id>", file=sys.stderr)
        return 2
    print(build_top_level_injection_text_for_project(argv[0]))
    return 0


def _handle_init_project(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: sot init-project <project_id>", file=sys.stderr)
        return 2
    project_id = argv[0]
    ensure_root_directories_exist()
    save_requirements_tree_atomically(RequirementsTree.empty_for_project(project_id))
    print(f"initialized project_id={project_id}")
    return 0


_VERB_DISPATCH_TABLE = {
    "user-prompt-submit-hook": lambda argv: _handle_user_prompt_submit_hook(),
    "add-session": _handle_add_session,
    "add-path": _handle_add_path,
    "show-top-level": _handle_show_top_level,
    "init-project": _handle_init_project,
}


def _main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: sot <verb> [...]\nVerbs: {', '.join(_VERB_DISPATCH_TABLE)}", file=sys.stderr)
        return 2
    verb = sys.argv[1]
    handler = _VERB_DISPATCH_TABLE.get(verb)
    if handler is None:
        print(f"Unknown verb: {verb}", file=sys.stderr)
        return 2
    return handler(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(_main())
