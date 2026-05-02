"""Standalone CLI: add a session_id (and its conversation path) to a project's membership.

Onus is on the user (or the user's AI agent) to call this whenever a session is
spawned/forked/compacted/transitioned and should be considered part of an existing
source-of-truth project.

Usage:
    python add_session_to_project_cli.py <project_id> <session_id> <conversation_path>
"""
from __future__ import annotations

import sys

from .config import (
    ensure_root_directories_exist,
    load_project_settings,
    save_project_settings,
)


def add_session_to_project(project_id: str, session_id: str, conversation_path: str) -> bool:
    """Returns True if a new membership was added, False if the session was already a member."""
    ensure_root_directories_exist()
    settings = load_project_settings(project_id)
    for existing_member in settings.member_sessions:
        if isinstance(existing_member, dict) and existing_member.get("session_id") == session_id:
            return False
    settings.member_sessions.append({
        "session_id": session_id,
        "conversation_path": conversation_path,
    })
    save_project_settings(settings)
    return True


def _main() -> int:
    if len(sys.argv) != 4:
        print(
            "Usage: add_session_to_project_cli.py <project_id> <session_id> <conversation_path>",
            file=sys.stderr,
        )
        return 2
    was_added = add_session_to_project(sys.argv[1], sys.argv[2], sys.argv[3])
    print("added" if was_added else "already_present")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
