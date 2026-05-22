---
agent_instruction_for_ai_readers: |
  This repo is a Claude Code skill. README.md is human-facing documentation.
  The actionable agent instructions live in SKILL.md next to this file.
  If you are an AI agent about to help a user set up, install, configure,
  use, or troubleshoot this tool, READ SKILL.md FIRST and follow the
  project-start-wizard.md it points at. Do not infer setup steps from this
  README alone.
---

# source-of-truth-agent-tool

### Perfect memory for everything you ask the AI to build.

Every requirement you give your AI coding agent is captured in your exact words and recalled on demand — so it builds precisely what you asked for, kept organized and quote-backed for the life of the project.

**Verbatim · Organized · Recall on demand**

> **Developers:** see [`ARCHITECTURE.md`](ARCHITECTURE.md) for the module map, data flow, configuration model, and extension points.

## How it keeps your requirements exact

- **Verbatim capture** — every prompt you send is script-copied to an append-only log the agent cannot edit.
- **Pointers, not prose** — each requirement references your quote; the agent only adds short, reviewer-audited labels, never the requirement text itself.
- **Second-AI review** on every change, so your words can't be mis-cited.
- **Context preserved** — each quote keeps the agent's preceding message, so even your one-word "yes" resolves to the question it answered.

## In practice

1. **You type:** `I want to use a MERN stack.`
2. A hook copies it verbatim (`raw#7`) and hands the agent the id.
3. The agent files a pointer (no requirement text of its own): `submit-change-set --add 7 --parent technical-requirements --title "stack choice"`
4. A second AI approves the citation; the node lands.
5. Anytime, you (or the agent) can pull that node and see **your exact words** — `"I want to use a MERN stack."`
6. **Months later:** it still resolves to exactly what you said.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│            REQUIREMENTS TREE  (what the agent stores — pointers only)        │
│                                                                              │
│   [A]                                                                        │
│    ├── [A.a]  raw_input_id: 3                                                │
│    │     ├── [A.a.i]   raw_input_id: 3                                       │
│    │     └── [A.a.ii]  raw_input_id: 5                                       │
│    └── [A.b]  raw_input_id: 4                                                │
│                                                                              │
│   [B]                                                                        │
│    ├── [B.a]  raw_input_id: 7                                                │
│    └── [B.b]  raw_input_id: 9                                                │
└──────────────────────────────────────────────────────────────────────────────┘
                │            │            │            │
                ▼            ▼            ▼            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    RAW INPUT LOG  (append-only, verbatim)                    │
│                                                                              │
│  raw#3  "must support offline mode for at least 24 hours of cached data.     │
│          cache eviction is LRU, capped at 500 MB."                           │
│  raw#4  "all user-visible timestamps render in the viewer's local timezone"  │
│  raw#5  "re-sync on reconnect must be incremental, not a full refresh"       │
│  raw#7  "login flow must use OAuth2 (Google + GitHub providers only)"        │
│  raw#9  "the auth code lives in src/auth/ and tests in tests/auth/"          │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼  resolve pointers → render
┌──────────────────────────────────────────────────────────────────────────────┐
│                  RENDERED VIEW  (what the agent / user sees)                 │
│                                                                              │
│  [A.a]   raw#3: must support offline mode for at least 24 hours of cached... │
│   [A.a.i]  raw#3: cache eviction is LRU, capped at 500 MB                    │
│   [A.a.ii] raw#5: re-sync on reconnect must be incremental, not a full...    │
│  [A.b]   raw#4: all user-visible timestamps render in the viewer's local...  │
│  [B.a]   raw#7: login flow must use OAuth2 (Google + GitHub providers only)  │
│  [B.b]   raw#9: the auth code lives in src/auth/ and tests in tests/auth/    │
└──────────────────────────────────────────────────────────────────────────────┘

The tree itself carries no requirement text — only pointers. All requirement
wording is resolved at render time from the immutable raw log, so the agent
cannot paraphrase or drift from what the user actually said. Each raw-log entry
also carries the agent's *preceding* output (auto-captured "pre-text"), so even a
one-word reply like "yes" resolves to the full question/plan it answered.
```

## The problem

You ask an AI agent for X. Twenty turns later it has paraphrased X into something subtly different and is now defending the paraphrase. By turn fifty the original requirement is gone — never written down verbatim, only restated through the agent's filter. There is no way to point at a single line and say "this is what was asked for."

This tool fixes that.

## How it fixes it

1. **Every raw input you send is captured verbatim** to a per-project log file at write-time, untouched.
2. The agent is allowed to maintain a **requirements tree**, but every node in that tree is **only a reference to a verbatim quote** in the log — never agent prose. Nothing the agent can write goes into the tree directly.
3. Every proposed edit to the tree (add, move, remove, modify reference, reorder) is sent to a **separate AI reviewer subprocess** (Haiku by default — fast and cheap) which returns a per-operation approve/reject verdict with reasons.
4. Only approved operations land on disk. Rejected ones come back to the agent with the reviewer's reasoning. Approved ops are also applied **one at a time** so a single bad op (e.g., a `reparent` referencing a node a sibling op removed) doesn't sink the others — its failure is reported back to the agent per-op.
5. The agent receives a small top-level summary of the tree on every turn, plus brief usage instructions.

The result: the only path for a hallucinated requirement to enter the tree is the agent **deliberately mis-citing a real quote**, which the reviewer catches by comparing the cited slice against the surrounding context. Pure invention is structurally impossible.

## Benefits

- **Verbatim audit trail.** Every requirement in the tree resolves to a real timestamped quote you typed.
- **No paraphrase rot.** Agent cannot rewrite or summarize requirements into the tree.
- **Two-AI gate.** A second model (different role, fresh context) reviews every proposed change.
- **Three speed tiers.** Live review on every submit, batched review on demand (deferred mode), or no review at all (none mode) when you want raw speed and trust the agent.
- **Per-operation verdicts.** The reviewer can approve some ops and reject others in the same batch.
- **Streamed reviewer log.** Watch the reviewer's NDJSON event stream live in `reviewer_thinking.log` as it works.
- **Cross-AI-CLI ready.** Claude Code is the first concrete adapter; the interface is small enough to plug another CLI under it.
- **Self-gating global hooks.** Install once; hooks fire on every Claude Code session but silently no-op for any session not registered to a project.
- **Terse replies still count.** The agent's prior turn is auto-captured as each entry's pre-text, so a bare "yes" / "option B" becomes a real, context-carrying requirement — no need to restate the question.
- **Trimmable citations.** Per-node `pretext` selection narrows that captured context to specific lines (or drops it) without losing the audit trail.
- **Per-project tuning.** Every global setting (reviewer model/mode, capture window, citation thresholds) is overridable per project with project→global fallback — no code edits.
- **Non-destructive install.** Reinstalls move the old folder to a timestamped backup; nothing is ever deleted. One project per session is enforced.

## What this unlocks together

The pieces compound into something none delivers alone: **you can run an entire project on terse confirmations and still end with a drift-proof, quote-backed requirements ledger.**

- The **verbatim raw log** + **auto pre-text capture** + the **reviewer gate** mean a one-word answer is captured *with the exact question/plan it answered*, cited (not paraphrased), and validated. Short, fast turns no longer cost you traceability.
- **Per-node pre-text selection** then lets the agent trim that captured context to just the relevant lines after the fact — precision without re-typing, and the full original is still in the immutable log.
- **Per-project overrides + settings-in-JSON** retune the same engine per project (how much context to capture, which reviewer, how strict citations are) with project→global fallback.
- **Default-scaffolded subject groups** (`resources`, `user-interaction-preferences`, `technical-requirements`, `current-project-documentation`) give every new project a consistent logical skeleton to file into from turn one.
- **Non-destructive install + self-gating hooks** make it safe to install once and leave on: unenrolled sessions no-op, reinstalls back up rather than delete.

Net: terse to type, exhaustive to audit — every requirement traces to a real timestamped quote, with its surrounding context, that a second model signed off on.

## Quickstart

Requires Python 3.10+ and (for the reviewer) the `claude` CLI logged in.

```bash
# 1. Clone the repo (anywhere -- install.py will deploy it to your skill folder).
git clone git@github.com:RandyHaylor/source-of-truth-agent-tool.git
cd source-of-truth-agent-tool

# 2. Install. This copies the repo into ~/.claude/skills/source-of-truth-agent-tool/,
#    writes the hook wrapper scripts (UserPromptSubmit / PostToolUse / Stop / etc.),
#    patches ~/.claude/settings.json, deploys the `source-of-truth` command on your
#    PATH (~/.local/bin), and seeds ~/.source-of-truth/global-settings.json.
#    Reinstall is non-destructive: an existing install dir is moved to a backup, never deleted.
python3 install.py

# 3. Open a new Claude Code session in your project, then in that session
#    register it as a source-of-truth project. Find the session id from
#    ~/.claude/projects/<encoded-cwd>/<session_id>.jsonl or from the UI.
source-of-truth init-and-register <your_session_id> ~/.claude/projects/<encoded-cwd>/<your_session_id>.jsonl

# 4. Pick a reviewer mode. Default is "live" (every submit gets reviewed).
#    Runtime verbs take no session/project id -- they resolve it from your session.
source-of-truth set-mode live    # or: none, deferred
```

You can also clone directly into `~/.claude/skills/source-of-truth-agent-tool/` and run `python3 install.py` from there — install.py detects the case and skips the copy step. If `source-of-truth` isn't found after install, add `~/.local/bin` to your PATH.

With install.py done, every user prompt in any registered session is auto-logged and any reviewer outcome messages auto-surface to you via Claude Code's `systemMessage`.

To use the API from inside an agent's tool calls:

```python
from source_of_truth.requirements_tree_controlled_api import RequirementsTreeControlledApi
from source_of_truth.ai_cli_adapter_claude_code import ClaudeCodeAdapter

api = RequirementsTreeControlledApi(project_id, ClaudeCodeAdapter(session_id))

# Capture: agent picks raw_input_id values from the log entries it already
# saw via the per-turn injection, then proposes a change-set.
result = api.submit_requirements_tree_change_set({
    "submitter_rationale": "User just confirmed the haiku-default decision.",
    "operations": [
        {"op": "add",
         "parent_id": "0",  # "0" = top-level; or a node_id like "12" or "a"
         "raw_input_reference": {"raw_input_id": 41},
         "short_neutral_title": "haiku default model"},
    ],
})
print(result.approved, result.reviewer_message)
```

## Reviewer modes

Set via `reviewer_mode` in `~/.source-of-truth/global-settings.json` or `reviewer_mode_override` in any project's `project-settings.json` (use `source-of-truth set-mode`).

| Mode | Behavior | Use when |
|------|---------|----------|
| `live` (default) | Every submit hits the reviewer immediately. | You want maximum safety. |
| `none` | Reviewer never called. Local validation runs (refs must resolve), then ops apply directly. | You trust the agent and want raw speed. |
| `deferred` | Submits validate locally and queue. Tree unchanged until the agent calls `flush_deferred_change_sets_for_review()`, which merges all queued ops and reviews in one round-trip. | Agent is doing extended planning and will batch decisions later. |

Live haiku round-trip in steady state is roughly 13–18s per call after a one-time priming step.

## Reviewer model

Set via `reviewer_model_name` in `global-settings.json` or `reviewer_model_name_override` per project. Default `claude-haiku-4-5-20251001` for cost and speed. Override per project to use a stronger model when needed.

## Per-project setting overrides

Every global setting can be overridden per project. Resolution is always **project → global**: a project value wins if present, otherwise the global default is used.

Two ways to set a per-project override:
- The dedicated reviewer fields `reviewer_mode_override` / `reviewer_model_name_override` (written by `source-of-truth set-mode`, etc.).
- A generic `overrides` map in the project's `project-settings.json`, keyed by the **exact** global setting name. Example:
  ```json
  "overrides": {
    "reviewer_mode": "none",
    "pre_submission_capture_char_limit": 4000
  }
  ```

A freshly created `project-settings.json` ships with an empty `overrides` map plus a `_comment_overrides` key (a JSON "comment", ignored by the loader) listing every overridable key. `load_config.resolve_effective_global_settings(project_id)` returns the merged result, and all consumers (validator, context injector, raw-input writer, reviewer) read through it.

## CLI verbs

```bash
# Setup (these establish the session↔project link, so they take ids)
source-of-truth init-and-register <session_id> <conversation_path>
source-of-truth init-project       <project_id>
source-of-truth add-session        <project_id> <session_id> <conversation_path>

# Runtime — the project is resolved from your current session; no project id
source-of-truth set-mode           live|none|deferred
source-of-truth show-tree          [--show-all]
source-of-truth read               <node_id> [<node_id> ...]
source-of-truth search-nodes       <query>
source-of-truth pretext            <node_id> <start> <end> | --all | --none
source-of-truth add-path           <filesystem_path>
source-of-truth show-top-level
source-of-truth flush-deferred

# Submit a change-set (combo shortcut FIRST to encourage tree organization)
source-of-truth submit-change-set --add <rid> --parent <parent_id_or_letter> --title "<leaf>" --new-group "<group title>"
source-of-truth submit-change-set --add <rid> --parent <parent_id_or_letter> --title "<leaf title>"
source-of-truth submit-change-set --add-group --parent <parent_id_or_letter> --title "<group title>"
source-of-truth submit-change-set '<raw json>'  # or @file.json or - for stdin

# Hooks (consumed by the harness, not by you)
source-of-truth user-prompt-submit-hook
```

By convention `project_id == initializing session_id` (what `init-and-register` does in one step). Any unique string works otherwise.

## Hook installation

The global hooks (`UserPromptSubmit`, `PostToolUse`, and `Stop`) are installed by `python3 install.py` (see Quickstart). They fire on every Claude Code session but **self-gate on project membership** — they silently no-op for any session whose `session_id` is not in a project's `member_sessions` list, so leaving them installed is safe even when you're not using the tool.

`install.py`:
- Deploys the repo into `~/.claude/skills/source-of-truth-agent-tool/` (skipping the copy if you cloned directly into that folder). **Reinstall is non-destructive:** an existing install dir is never deleted — the whole folder is *moved* to `~/.claude/source-of-truth-bak/<UTC-timestamp>/source-of-truth-agent-tool/` (logged to the console), then the repo is copied in fresh.
- Writes the hook wrapper scripts in that dir. Each adds the install dir to `sys.path`, calls into the `source_of_truth` package next to it, and emits `{}` on any error.
- Patches `~/.claude/settings.json` to register the hooks if not already present. Other hook entries are left untouched. `settings.json` is backed up with a timestamp.
- Initializes `~/.source-of-truth/global-settings.json` from the shipped `default-global-settings.json` if absent. All tunable settings live in JSON (loaded by `load_config.py`): `reviewer_mode`, `reviewer_model_name`, `reviewer_command`, `pre_submission_capture_char_limit`, `char_range_allowed_above_threshold`, `min_char_range_length`, and the agent-guidance text templates.
- Idempotent — safe to re-run after pulling a newer repo.

To remove cleanly:

```bash
python3 uninstall.py
```

Removes the on-PATH `source-of-truth` stub and scrubs the matching hook entries from `settings.json`. It deliberately does **not** delete `~/.claude/skills/source-of-truth-agent-tool/` (it may be an in-place clone) — remove that folder manually for a full uninstall. Your captured raw input logs, requirements trees, and global settings under `~/.source-of-truth/` are NOT touched.

## Agent pre-text capture (Stop hook)

Each raw-input log entry stores `pre_submission_content`: the agent's output from the **previous** turn. This is what lets a one-word reply (`yes`, `option B`) be captured as a requirement — the pre-text carries the question/plan the user was responding to, so a node citing that short answer still resolves to meaningful context for the reviewer.

How it's populated (installed by `install.py`):
1. A **`Stop` hook** (`stop_hook_capture_agent_output.py`) fires at the end of every agent turn. It reads the session transcript and extracts the assistant's text **since the last user prompt — including tool-result summaries** (tool *calls* are omitted as noise), via `claude_cli_get_recent_agent_messages.py`. It writes that to `projects/<project_id>/pending_pre_text_for_session_<session_id>.txt`.
2. On the **next** prompt, the `UserPromptSubmit` hook reads (and deletes — consume-once) that file, truncates it to the per-project `pre_submission_capture_char_limit` (default 2000, kept from the bottom), and stores it as the new entry's `pre_submission_content`.

Self-gating: the Stop hook no-ops for any session not registered to a project. The capture is Claude-Code-specific (transcript jsonl + Stop event); other platforms would supply their own adapter for the same `pre_submission_content` field.

### Per-node pre-text selection

A quote-reference node cites that pre-text. **By default a new node includes the whole pre-text** (`raw_input_reference.pre_text_line_range` absent). An agent can narrow or drop it later:

```bash
source-of-truth pretext <node_id> <start> <end>   # cite only these 1-indexed pre-text lines
source-of-truth pretext <node_id> --all           # whole pre-text (default)
source-of-truth pretext <node_id> --none          # exclude the pre-text from this node
```

`read <node_id> …` shows each node's pre-text **line-numbered** (so the agent knows which lines to pick) and prints one reminder of the `pretext` verb (on stderr) after all nodes. `resolve_quote_text_from_reference` always includes the selected pre-text, so the reviewer and `search-nodes` see exactly what each node cites. Like all runtime verbs, `pretext` and `read` take **no project id** — they resolve the project from the current session and refuse if it isn't enrolled.

A session may belong to **only one** project; `add-session`/`init-and-register` refuse to add a session that's already in a different project (remove it there first).

## Storage layout

```
~/.source-of-truth/
    global-settings.json                              # optional defaults
    pending_messages_for_raw_input_sender.jsonl       # outbound queue (per-message tagged with target_project_id)
    projects/
        <project_id>/                                 # project_id = session_id of initializing session
            project-<project_id>-source-of-truth.json # the requirements tree (sole writer = our app)
            project-settings.json                     # member sessions; reviewer history; `overrides` map + dedicated mode/model overrides
            raw_input_log.json                        # rolling log, grouped by session_id, raw_input_id sequential from 0
            reviewer_thinking.log                     # full streamed log of reviewer NDJSON events
            deferred_change_sets_queue.jsonl          # only used in deferred mode
            pending_pre_text_for_session_<sid>.txt    # Stop-hook agent-output capture; consumed by next UserPromptSubmit
```

## Change-set schema

Node ids are strings throughout: quote-leaf ids are decimal-counter strings (`"1"`, `"2"`, …) and group ids are letter strings (`"a"`, `"b"`, …, `"aa"`, …). The string `"0"` is reserved as the top-level parent sentinel — any node whose `parent_id == "0"` is a root.

```json
{
  "submitter_rationale": "free-text",
  "operations": [
    {"op": "add",              "parent_id": "12", "raw_input_reference": {"raw_input_id": 23, "char_range": [120, 180]}, "short_neutral_title": "vendor placement"},
    {"op": "add",              "parent_id": "0",  "raw_input_reference": {"raw_input_id": 7},  "short_neutral_title": "back end stack"},
    {"op": "add_group",        "parent_id": "0",  "short_neutral_title": "vendor rules"},
    {"op": "reparent",         "node_id": "23", "new_parent_id": "33"},
    {"op": "remove",           "node_id": "47"},
    {"op": "modify_reference", "node_id": "23", "raw_input_reference": {"raw_input_id": 11}},
    {"op": "reorder_children", "parent_id": "12", "child_order": ["4", "23", "9"]}
  ]
}
```

Op rules:
- **`add`** requires `parent_id` (use `"0"` for top-level), `raw_input_reference`, and `short_neutral_title` (1–50 chars, the SUBJECT of the requirement, not the spec).
- **`add_group`** requires `parent_id` and `short_neutral_title`. The new group's letter id is auto-allocated (`a`, `b`, …, `aa`).
- The reviewer may return `amended_short_title` per op when a title overreaches the cited slice; that amended title is persisted automatically (no rejection).

`raw_input_id` is a per-project integer assigned at log time, starting at 0.

`char_range` rules (the threshold is the per-project setting `char_range_allowed_above_threshold`, default **500**, overridable per project):
- **Forbidden** when submission length ≤ threshold (cite the whole entry).
- **Allowed but optional** above the threshold.
- `[start, end]` inclusive, ≥ `min_char_range_length` chars (default 1).

`pre_text_line_range` (optional, selects the entry's agent pre-text on a node): absent ⇒ whole pre-text, `[start, end]` ⇒ those 1-indexed lines, `"none"` ⇒ excluded. Set it with the `pretext` verb.

## Status

149 unit tests passing. Live haiku reviewer round-trip verified end-to-end with single-op, two-op, and four-call sequential tests. Hooks installed and self-gating verified across registered/unregistered/missing-package/malformed-input cases.

Schema highlights as of the latest refactor:
- Node ids are strings: `"1"`, `"2"`, … for quote leaves; `"a"`, `"b"`, …, `"aa"` for groups.
- Every node carries `short_neutral_title` (1–50 chars, the subject not the spec).
- `parent_id == "0"` is the top-level sentinel; agents must always pick a parent.
- Group nodes (`add_group` op) organize the tree; the combo shortcut (`--new-group "<title>"`) creates a group + a leaf inside it in one change-set. New projects are pre-scaffolded with default top-level groups.
- A node's citation can include the entry's agent pre-text (whole / line-range / `"none"`) via `pre_text_line_range`, set with the `pretext` verb.
- All tunable settings live in JSON (`default-global-settings.json` overlaid by the live `global-settings.json`), each overridable per project.
- Reviewer can emit `amended_short_title` per op when a title overreaches; the amended title is persisted automatically.
