"""Loads global + per-project settings and exposes the system-wide constants and paths."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SOURCE_OF_TRUTH_ROOT_DIR: Path = Path.home() / ".source-of-truth"
GLOBAL_SETTINGS_FILE_PATH: Path = SOURCE_OF_TRUTH_ROOT_DIR / "global-settings.json"
PROJECTS_PARENT_DIR: Path = SOURCE_OF_TRUTH_ROOT_DIR / "projects"

CHAR_RANGE_ALLOWED_ABOVE_THRESHOLD: int = 500
# char_range is FORBIDDEN when submission length <= threshold (whole entry is the citation),
# and ALLOWED-BUT-OPTIONAL when submission length > threshold.
PRE_SUBMISSION_CAPTURE_CHAR_LIMIT: int = 2000
MIN_CHAR_RANGE_LENGTH: int = 1

INTERACTION_TIME_AGENT_GUIDANCE: str = (
    "[SoT guidance]\n"
    "PREFER asking ISOLATED yes/no or short-list (A/B/C) questions whose answer is a single\n"
    "word. The user's brief confirmation ('yes' / 'no' / 'A') becomes the cited slice while\n"
    "the ~2000 chars of PRE-INPUT CONTEXT (your question, captured automatically) supplies\n"
    "the actual requirement content. The reviewer explicitly supports this pattern --\n"
    "do not paraphrase the question into the user's mouth.\n"
    "ALWAYS pick a parent: every add op needs parent_id (use '0' for top-level only when\n"
    "no appropriate parent exists). Prefer organizing under group nodes (--add-group with a\n"
    "few-word subject title). Group letter ids: a, b, ..., z, aa, ab, ...\n"
    "Title rule: <short_neutral_title> is a 1-5 WORD NOUN PHRASE naming the TOPIC of the\n"
    "requirement (1-50 chars). It is NOT a sentence and NOT a rule.\n"
    "  Good: \"vendor placement\", \"phrase character voice\", \"back end stack\"\n"
    "  Bad:  \"Phrases must be in-character speech\" (sentence/rule), \"vendor every other floor\"\n"
    "        (adds spec detail), \"haiku default\" if cited slice was about gpt (contrast).\n"
    "Do NOT add detail/contrast/scope beyond the cited slice. The reviewer rewrites overreaching\n"
    "titles by emitting amended_short_title; you'll see the persisted title in the assigned_node_ids\n"
    "list of the submit response.\n"
    "Capture patterns (each user ack = a new node):\n"
    "  - confirm TECH STACK / PLAN / HIGH-LEVEL STRUCTURE -> ack -> add nodes\n"
    "  - on your A/B/C question + user pick: char_range the letter; pre_text anchors meaning\n"
    "  - on your yes/no question + user 'yes' or 'no': cite the whole short answer; pre_text carries the question\n"
    "  - user correction/feedback -> capture verbatim under an appropriate group\n"
    "Batch related captures into ONE `source-of-truth submit-change-set` invocation.\n"
    "When you submit:\n"
    "  - The result includes `message_for_raw_input_sender` — RELAY IT VERBATIM to the user before\n"
    "    continuing other work, so they know review is in flight + where the log is.\n"
    "  - On approval: relay the success message and proceed.\n"
    "  - On rejection: relay reviewer_message verbatim, then either adjust the change-set\n"
    "    or ask the user a clarifying question.\n"
)


TOP_LEVEL_INJECTION_BLURB_TEMPLATE: str = (
    "[SoT] tree (id title; indented; --show-all for raw quotes):\n"
    "{tree_compact_text}\n"
    "Shortcuts (combo first to encourage tree organization):\n"
    "  source-of-truth submit-change-set <project_id> --add <raw_input_id> --parent <pid_or_letter> --title \"<leaf>\" --new-group \"<group title>\"\n"
    "  source-of-truth submit-change-set <project_id> --add <raw_input_id> --parent <pid_or_letter> --title \"<leaf title>\"\n"
    "  source-of-truth submit-change-set <project_id> --add-group --parent <pid_or_letter> --title \"<group title>\"\n"
    "Read: `source-of-truth read <project_id> <id> [<id> ...]`  Search: `source-of-truth search-nodes <project_id> <q>`\n"
    "Capture rule: on every definitive user reply (explicit OR pick from your A/B/C), "
    "queue an add op referencing the raw_input_id (just logged) under an appropriate parent "
    "(or '0' if none); char_range is FORBIDDEN when submission <=500 chars (cite whole entry) "
    "and ALLOWED-BUT-OPTIONAL when submission >500 chars; batch ops; never paraphrase.\n"
    "See SKILL.md in the source-of-truth-agent-tool skill folder for full verb reference."
)


DEFAULT_REVIEWER_MODEL_NAME: str = "claude-haiku-4-5-20251001"

REVIEWER_MODE_LIVE_REVIEW_EVERY_SUBMIT: str = "live"
REVIEWER_MODE_NO_REVIEWER_DIRECT_APPLY: str = "none"
REVIEWER_MODE_DEFER_UNTIL_FLUSH: str = "deferred"

ALL_VALID_REVIEWER_MODES: tuple[str, ...] = (
    REVIEWER_MODE_LIVE_REVIEW_EVERY_SUBMIT,
    REVIEWER_MODE_NO_REVIEWER_DIRECT_APPLY,
    REVIEWER_MODE_DEFER_UNTIL_FLUSH,
)

DEFAULT_REVIEWER_MODE: str = REVIEWER_MODE_LIVE_REVIEW_EVERY_SUBMIT


@dataclass
class GlobalSettings:
    reviewer_command: list[str] = field(default_factory=lambda: ["claude", "-p"])
    reviewer_model_name: str = DEFAULT_REVIEWER_MODEL_NAME
    reviewer_mode: str = DEFAULT_REVIEWER_MODE
    raw_extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectSettings:
    project_id: str
    member_sessions: list[dict[str, str]] = field(default_factory=list)
    historical_reviewer_session_ids: list[str] = field(default_factory=list)
    current_reviewer_session_id: str | None = None
    reviewer_model_name_override: str | None = None
    reviewer_mode_override: str | None = None
    overrides: dict[str, Any] = field(default_factory=dict)
    raw_extra: dict[str, Any] = field(default_factory=dict)


def project_directory_for(project_id: str) -> Path:
    return PROJECTS_PARENT_DIR / project_id


def project_settings_file_path(project_id: str) -> Path:
    return project_directory_for(project_id) / "project-settings.json"


def project_source_of_truth_file_path(project_id: str) -> Path:
    return project_directory_for(project_id) / f"project-{project_id}-source-of-truth.json"


def project_raw_input_log_file_path(project_id: str) -> Path:
    return project_directory_for(project_id) / "raw_input_log.json"


def project_reviewer_thinking_log_file_path(project_id: str) -> Path:
    return project_directory_for(project_id) / "reviewer_thinking.log"


def project_deferred_change_sets_queue_file_path(project_id: str) -> Path:
    return project_directory_for(project_id) / "deferred_change_sets_queue.jsonl"


def ensure_root_directories_exist() -> None:
    SOURCE_OF_TRUTH_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_PARENT_DIR.mkdir(parents=True, exist_ok=True)


def load_global_settings() -> GlobalSettings:
    if not GLOBAL_SETTINGS_FILE_PATH.exists():
        return GlobalSettings()
    raw = json.loads(GLOBAL_SETTINGS_FILE_PATH.read_text())
    return GlobalSettings(
        reviewer_command=raw.get("reviewer_command", ["claude", "-p"]),
        reviewer_model_name=raw.get("reviewer_model_name", DEFAULT_REVIEWER_MODEL_NAME),
        reviewer_mode=raw.get("reviewer_mode", DEFAULT_REVIEWER_MODE),
        raw_extra={k: v for k, v in raw.items()
                   if k not in {"reviewer_command", "reviewer_model_name", "reviewer_mode"}},
    )


def save_global_settings(settings: GlobalSettings) -> None:
    SOURCE_OF_TRUTH_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "reviewer_command": settings.reviewer_command,
        "reviewer_model_name": settings.reviewer_model_name,
        "reviewer_mode": settings.reviewer_mode,
        **settings.raw_extra,
    }
    GLOBAL_SETTINGS_FILE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True)
    )


def write_default_global_settings_if_absent() -> None:
    if not GLOBAL_SETTINGS_FILE_PATH.exists():
        save_global_settings(GlobalSettings())


def resolve_reviewer_model_name_for_project(project_id: str) -> str:
    project_settings = load_project_settings(project_id)
    if project_settings.reviewer_model_name_override:
        return project_settings.reviewer_model_name_override
    return load_global_settings().reviewer_model_name


def resolve_reviewer_mode_for_project(project_id: str) -> str:
    project_settings = load_project_settings(project_id)
    if project_settings.reviewer_mode_override:
        return project_settings.reviewer_mode_override
    return load_global_settings().reviewer_mode


def load_project_settings(project_id: str) -> ProjectSettings:
    settings_file = project_settings_file_path(project_id)
    if not settings_file.exists():
        return ProjectSettings(project_id=project_id)
    raw = json.loads(settings_file.read_text())
    return ProjectSettings(
        project_id=project_id,
        member_sessions=raw.get("member_sessions", []),
        historical_reviewer_session_ids=raw.get("historical_reviewer_session_ids", []),
        current_reviewer_session_id=raw.get("current_reviewer_session_id"),
        reviewer_model_name_override=raw.get("reviewer_model_name_override"),
        reviewer_mode_override=raw.get("reviewer_mode_override"),
        overrides=raw.get("overrides", {}),
        raw_extra={k: v for k, v in raw.items() if k not in {
            "member_sessions", "historical_reviewer_session_ids",
            "current_reviewer_session_id", "reviewer_model_name_override",
            "reviewer_mode_override", "overrides",
        }},
    )


def save_project_settings(settings: ProjectSettings) -> None:
    """Write project-settings.json atomically under a cross-platform file lock.

    Two safeguards:
      1. Cross-platform file lock around the write so concurrent writers
         (multiple registered sessions adding themselves at once, etc.)
         do not interleave their payload bytes.
      2. Temp-file-and-rename so any concurrent reader always sees either
         the previous complete file or the new complete file -- never a
         partially-written one.
    """
    import os
    import tempfile
    from .cross_platform_file_lock import acquire_exclusive_file_lock

    project_directory_for(settings.project_id).mkdir(parents=True, exist_ok=True)
    settings_file = project_settings_file_path(settings.project_id)
    payload: dict[str, Any] = {
        "member_sessions": settings.member_sessions,
        "historical_reviewer_session_ids": settings.historical_reviewer_session_ids,
        "current_reviewer_session_id": settings.current_reviewer_session_id,
        "overrides": settings.overrides,
        **settings.raw_extra,
    }
    if settings.reviewer_model_name_override is not None:
        payload["reviewer_model_name_override"] = settings.reviewer_model_name_override
    if settings.reviewer_mode_override is not None:
        payload["reviewer_mode_override"] = settings.reviewer_mode_override
    payload_text = json.dumps(payload, indent=2, sort_keys=True)
    with acquire_exclusive_file_lock(settings_file):
        temp_fd, temp_path_str = tempfile.mkstemp(
            prefix=".sot-settings-", suffix=".tmp", dir=str(settings_file.parent)
        )
        try:
            with os.fdopen(temp_fd, "w") as temp_file_handle:
                temp_file_handle.write(payload_text)
            os.replace(temp_path_str, settings_file)
        except Exception:
            try:
                os.unlink(temp_path_str)
            except OSError:
                pass
            raise
