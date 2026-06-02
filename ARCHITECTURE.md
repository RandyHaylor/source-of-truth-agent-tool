# Architecture & Developer Guide

Developer-facing reference for `source-of-truth-agent-tool`. For the user pitch
and the agent-facing capture rules, see `README.md` and `SKILL.md` respectively.
This document explains how the system is built, how the pieces fit, and where to
make changes.

---

## 1. The core invariant

Everything here exists to enforce one rule:

> **The agent can never author requirement text. It can only point at the user's
> verbatim words.**

Two data stores make this structural, not advisory:

- **Raw input log** (`raw_input_log.json`) — an append-only record of every user
  prompt, captured verbatim by a hook *before* the agent runs. The agent has
  **read-only** access; nothing in the agent's control path can write to it.
- **Requirements tree** (`project-<id>-source-of-truth.json`) — a tree whose
  nodes hold **pointers** (`raw_input_id` + optional ranges) into the raw log,
  plus a short agent-authored *title* (the subject, never the requirement). The
  tree is the **only** source of truth; the raw log is just the quote repository
  it draws from.

Requirement text is *resolved at render time* from the immutable log. The agent's
only authored free text is the `short_neutral_title` on a node/group — and even
that is bounded (1–50 chars) and reviewer-audited.

---

## 2. Data flow (one user turn)

```
                    ┌──────────────────────────────────────────────┐
  user types  ─────▶│ UserPromptSubmit hook                         │
                    │  • append verbatim prompt to raw_input_log     │
                    │  • attach prior agent output as "pre-text"     │
                    │  • inject context line (tree + new raw id)     │
                    └───────────────────────┬──────────────────────┘
                                            │ raw_input_id, tree blurb
                                            ▼
                    ┌──────────────────────────────────────────────┐
   agent acts  ────▶│ submit-change-set --add <rid> --parent <p>    │
                    │              --title "<subject>"               │
                    └───────────────────────┬──────────────────────┘
                                            │ change-set (ops, pointers only)
                                            ▼
            ┌────────────────┐   validate    ┌──────────────────────────┐
            │ reference      │◀──────────────│ controlled API           │
            │ validator      │   refs OK?    │ (RequirementsTreeControll │
            └────────────────┘               │  edApi)                  │
                                            │  • live: send to reviewer │
                                            │  • none: apply directly   │
                                            │  • deferred: queue        │
                                            └───────────┬──────────────┘
                                                        │ approved ops
                                                        ▼
                              ┌──────────────────────────────────────┐
                              │ change-set applier (pure fn)          │
                              │  → new tree → atomic save under lock  │
                              └──────────────────────────────────────┘

  next prompt ───▶ UserPromptSubmit reads the transcript and captures the
                   PRECEDING turn's agent output as this entry's pre-text
                   (works even if the previous turn was interrupted)
```

---

## 3. Module map

Grouped by responsibility. Each is a single-purpose module in `source_of_truth/`.

### Entry points / dispatch
| Module | Responsibility |
|---|---|
| `cli_entrypoint.py` | The single dispatcher: `source-of-truth <verb>` for every operation (setup verbs, runtime verbs, and hook entry points). Owns argv parsing, the session→project resolution for runtime verbs, and the per-turn context-injection line. |
| `__init__.py` | Package marker / high-level docstring. |

### Capture (write path into the raw log) — agent cannot reach these
| Module | Responsibility |
|---|---|
| `raw_input_log_writer.py` | Append one entry (verbatim submission + truncated pre-text) to the rolling raw log. |
| `raw_input_log_entry_schema.py` | Dataclass + JSON schema for a single raw entry (`raw_input_id`, `timestamp_iso`, `submission_text`, `pre_submission_content`). |
| `claude_cli_get_recent_agent_messages.py` | Extract the preceding turn's assistant text (incl. tool-result summaries, excl. tool calls) from the session transcript. `build_pre_text_for_incoming_user_prompt()` is what `UserPromptSubmit` calls to capture pre-text — robust to whether the new prompt is already appended to the transcript. (No Stop hook: it never fires on an interrupted turn.) |

### Read path (resolve quotes — agent-readable)
| Module | Responsibility |
|---|---|
| `raw_input_log_reader.py` | Read-only access by `raw_input_id`. `resolve_quote_text_from_reference()` turns a node's pointer into verbatim text (submission slice + selected pre-text). `select_pre_text()` applies the tri-state pre-text selection. |
| `compact_tree_renderer.py` | Render the tree for humans/agents: titles-only (indented) and `--show-all` (inlines resolved quotes for the top levels). |
| `conversation_context_injector.py` | Build the top-level injection blurb fed into the agent's context each turn / on sub-agent calls. |

### The tree (the source of truth)
| Module | Responsibility |
|---|---|
| `requirements_tree_node_schema.py` | Node + tree dataclasses and JSON schema. `RawInputReference` (the pointer: `raw_input_id`, `char_range`, `pre_text_line_range`), node kinds (quote-reference, group, project-paths), letter-id allocation, default-scaffold groups. |
| `requirements_tree_change_set_schema.py` | Schema for a batched change-set the agent submits. |
| `requirements_tree_change_set_applier.py` | **Pure function**: apply an approved change-set to a tree, return the new tree. Also the per-op-isolation variant. No I/O. |
| `requirements_tree_store.py` | Atomic load/save of the tree JSON under an exclusive file lock. Sole writer. |
| `requirements_tree_controlled_api.py` | The public API surface exposed to the primary agent. Orchestrates validate → review (per mode) → apply → save. Read endpoints (`get_node_by_id`, search) resolve quote text inline. |

### Review gate
| Module | Responsibility |
|---|---|
| `requirements_reference_validator.py` | Validate every `raw_input_id` / `char_range` / `pre_text_line_range` in a change-set against the raw log *before* anything reaches the reviewer or the tree. |
| `requirements_modification_reviewer.py` | Send a change-set (with inline-resolved context) to the live reviewer session; parse a per-operation verdict. |
| `reviewer_session_lifecycle_manager.py` | Own the long-lived reviewer subprocess for a project (prime it, resume it, track its session id). |
| `deferred_change_sets_queue.py` | Per-project queue for change-sets submitted in `deferred` mode; drained by `flush-deferred`. |

### AI-CLI abstraction (portability seam)
| Module | Responsibility |
|---|---|
| `ai_cli_adapter_interface.py` | Abstract interface any AI-CLI adapter must implement (persistent reviewer session handle, etc.). |
| `ai_cli_adapter_claude_code.py` | Concrete adapter for Anthropic's Claude Code CLI (`claude -p`, resume-based persistent reviewer session). |

### Config, identity, plumbing
| Module | Responsibility |
|---|---|
| `load_config.py` | Load global + per-project settings; expose system constants and all on-disk paths. Pure loader — tunable values live in JSON (see §5). |
| `project_identifier_resolver.py` | Standalone: scan `projects/*/project-settings.json` to find which project a `session_id` belongs to. The basis of session→project resolution and hook self-gating. |
| `add_session_to_project_cli.py` | Add a `session_id` (+ conversation path) to a project's membership. Enforces one-project-per-session. |
| `cross_platform_file_lock.py` | Context-manager exclusive file lock (fcntl on Linux/macOS, msvcrt on Windows). |
| `pending_messages_for_raw_input_sender.py` | Append/drain queue of user-facing messages produced by API calls. |
| `post_tool_use_show_messages_to_raw_input_sender.py` | PostToolUse hook: drain pending user-messages targeted at this session's project. |

---

## 4. Session → project resolution (no `project_id` on runtime verbs)

Runtime verbs (`show-tree`, `read`, `search-nodes`, `submit-change-set`,
`set-mode`, `add-path`, `show-top-level`, `flush-deferred`, `pretext`) take **no
project id**. `_resolve_project_and_remaining_args()` resolves it:

1. **Undocumented override** (portability only): a `--project <id>` flag, or a
   leading positional that names an existing project directory on disk.
2. Otherwise **the current session**: `CLAUDE_CODE_SESSION_ID` →
   `resolve_project_id_for_session()`.
3. Not enrolled → error: *"You must be part of a source-of-truth project to use
   this command."*

Only **setup/join** verbs take an explicit id, because they run *before*
membership exists: `init-project <project_id>`, `add-session <project_id>
<session_id> <path>`, and `init-and-register <session_id> <path>` (which sets
`project_id == session_id` by convention).

**One project per session** is enforced in `add_session_to_project()`
(`SessionAlreadyInDifferentProjectError`): a session already in a different
project must be removed there first.

---

## 5. Configuration model

Settings resolve in three layers (later wins):

1. **Shipped defaults** — `source_of_truth/default-global-settings.json` (carries
   every key).
2. **Live global** — `~/.source-of-truth/global-settings.json`.
3. **Per-project overrides** — `projects/<id>/project-settings.json` →
   `overrides: {}`. Only keys in `OVERRIDABLE_GLOBAL_SETTING_NAMES` may be
   overridden. `resolve_effective_global_settings(project_id)` returns the merge;
   all consumers (validator, injector, writer, reviewer) read through it.

`load_config.py` is a **pure loader** — it holds no tunable values, only paths,
mode constants, and the overridable-key list. Historical constant names are
re-exported from the loaded settings so older importers keep working.

Key tunables: `reviewer_mode` (`live`/`none`/`deferred`), `reviewer_model_name`,
`pre_submission_capture_char_limit` (default 2000), `char_range_allowed_above_threshold`
(default 500), `min_char_range_length` (default 1), and the agent-guidance /
injection-blurb templates.

---

## 6. Storage layout

```
~/.source-of-truth/
├── global-settings.json                         # live global tunables
└── projects/
    └── <project_id>/                            # project_id = initializing session_id
        ├── project-settings.json                # membership + per-project overrides
        ├── project-<project_id>-source-of-truth.json   # the requirements tree (sole writer = store)
        ├── raw_input_log.json                   # append-only verbatim quotes (agent: read-only)
        ├── reviewer_thinking.log                # reviewer's streamed NDJSON
        └── deferred_change_sets_queue.json      # pending submits (deferred mode)
```

---

## 7. The pointer model (`RawInputReference`)

A quote-reference node cites:

- `raw_input_id` — which log entry (per-project int, from 0).
- `char_range` *(optional)* — `[start, end]` inclusive into `submission_text`.
  **Forbidden** when the submission ≤ `char_range_allowed_above_threshold`
  (cite the whole entry); allowed-but-optional above it.
- `pre_text_line_range` *(optional, tri-state)* — selects the entry's agent
  pre-text: **absent ⇒ whole pre-text** (new-node default), `[start, end]` ⇒
  those 1-indexed lines, `"none"` ⇒ excluded. Set via the `pretext` verb.

`resolve_quote_text_from_reference()` always includes the selected pre-text, so
the reviewer, `search-nodes`, and `--show-all` all see exactly what a node cites.

---

## 8. Hooks

Installed by `install.py` into `~/.claude/settings.json`; all **self-gate** (no-op
silently if the current session isn't a member of any project):

| Event | Script | Purpose |
|---|---|---|
| `UserPromptSubmit` | `user_prompt_submit_hook.py` | Capture the prompt verbatim; capture the preceding turn's agent output as pre-text by reading the transcript; inject the per-turn context line. |
| `PostToolUse` (Bash) | `post_tool_use_hook.py` | Drain pending user-facing messages to this session's project. |
| `PostToolUse` (*) | `what_is_session_id_hook.py` | Sentinel hook resolving the current session id. |

(There is intentionally **no `Stop` hook** — it never fires on an interrupted turn, which dropped pre-text. Capture lives in `UserPromptSubmit`, which fires on every prompt.)

Hook wrapper scripts are generated into the install dir by `install.py`, which
also patches `settings.json` (dedup + stale-entry scrubbing) and deploys the
on-PATH `source-of-truth` stub. **Reinstall is non-destructive**: an existing
install dir is moved to a timestamped backup, never deleted.

---

## 9. Extending to another AI CLI

The portability seam is `ai_cli_adapter_interface.py`. To support a non-Claude
CLI:

1. Implement `AiCliAdapterInterface` (and a `PersistentReviewerSessionHandle`)
   for that CLI's invocation + resume semantics — model the new adapter on
   `ai_cli_adapter_claude_code.py`.
2. Provide that CLI's hook equivalents for the four events in §8, each feeding
   the same `pre_submission_content` / capture contract.
3. Supply the session id the way `CLAUDE_CODE_SESSION_ID` does today (the
   `--project` override exists precisely so a platform without an env session id
   can still drive the runtime verbs).

The core (tree, validator, applier, store, config) is CLI-agnostic.

---

## 10. Testing

`pytest` from the repo root. **149 tests passing** at time of writing. Tests use
an isolated `~/.source-of-truth` root via fixtures (see `tests/conftest.py`), so
they never touch a real install. Coverage spans: change-set application + per-op
isolation, reference validation (incl. `char_range` / `pre_text_line_range`
bounds), reviewer verdict parsing + modes, the controlled API, file locking,
session→project resolution, the runtime verbs (project resolved from session),
pre-text capture round-trip, the `pretext` verb, default-project scaffold, and
`read`/`search`/`--show-all` quote resolution.

A convenience runner lives at `/tmp/run_sot_tests.sh` during development; CI
should invoke `python3 -m pytest -q` from the repo root.
