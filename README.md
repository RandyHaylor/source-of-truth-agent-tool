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

**Stop your AI coding agent from drifting away from what you actually asked for.**

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
cannot paraphrase or drift from what the user actually said.
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

## Quickstart

Requires Python 3.10+ and (for the reviewer) the `claude` CLI logged in.

```bash
# 1. Clone the repo (anywhere -- install.py will deploy it to your skill folder).
git clone git@github.com:RandyHaylor/source-of-truth-agent-tool.git
cd source-of-truth-agent-tool

# 2. Install. This copies the repo into ~/.claude/skills/source-of-truth-agent-tool/,
#    writes the two hook wrapper scripts, patches ~/.claude/settings.json, and
#    initializes ~/.source-of-truth/global-settings.json.
python3 install.py

# 3. (Optional) Drop a small wrapper on PATH so you can run `sot <verb>` anywhere.
cat > ~/.local/bin/sot <<EOF
#!/usr/bin/env bash
exec python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/skills/source-of-truth-agent-tool'); from source_of_truth.cli_entrypoint import _main; sys.exit(_main())" "\$@"
EOF
chmod +x ~/.local/bin/sot

# 4. Open a new Claude Code session in your project, then in that session
#    register it as a source-of-truth project. Find the session id from
#    ~/.claude/projects/<encoded-cwd>/<session_id>.jsonl or from the UI.
sot init-and-register <your_session_id> ~/.claude/projects/<encoded-cwd>/<your_session_id>.jsonl

# 5. Pick a reviewer mode. Default is "live" (every submit gets reviewed).
sot set-mode <your_session_id> live    # or: none, deferred
```

If you'd rather skip the wrapper script, you can also clone directly into `~/.claude/skills/source-of-truth-agent-tool/` and run `python3 install.py` from there — install.py detects the case and skips the copy step.

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

Set via `reviewer_mode` in `~/.source-of-truth/global-settings.json` or `reviewer_mode_override` in any project's `project-settings.json` (use `sot set-mode`).

| Mode | Behavior | Use when |
|------|---------|----------|
| `live` (default) | Every submit hits the reviewer immediately. | You want maximum safety. |
| `none` | Reviewer never called. Local validation runs (refs must resolve), then ops apply directly. | You trust the agent and want raw speed. |
| `deferred` | Submits validate locally and queue. Tree unchanged until the agent calls `flush_deferred_change_sets_for_review()`, which merges all queued ops and reviews in one round-trip. | Agent is doing extended planning and will batch decisions later. |

Live haiku round-trip in steady state is roughly 13–18s per call after a one-time priming step.

## Reviewer model

Set via `reviewer_model_name` in `global-settings.json` or `reviewer_model_name_override` per project. Default `claude-haiku-4-5-20251001` for cost and speed. Override per project to use a stronger model when needed.

## CLI verbs

```bash
# Setup
source-of-truth init-and-register <session_id> <conversation_path>
source-of-truth init-project       <project_id>
source-of-truth add-session        <project_id> <session_id> <conversation_path>
source-of-truth add-path           <project_id> <filesystem_path>
source-of-truth set-mode           <project_id> live|none|deferred

# Runtime (agent-facing)
source-of-truth show-tree          <project_id> [--show-all]
source-of-truth read               <project_id> <node_id> [<node_id> ...]
source-of-truth search-nodes       <project_id> <query>
source-of-truth show-top-level     <project_id>
source-of-truth flush-deferred     <project_id>

# Submit a change-set (combo shortcut FIRST to encourage tree organization)
source-of-truth submit-change-set <pid> --add <rid> --parent <pid_or_letter> --title "<leaf>" --new-group "<group title>"
source-of-truth submit-change-set <pid> --add <rid> --parent <pid_or_letter> --title "<leaf title>"
source-of-truth submit-change-set <pid> --add-group --parent <pid_or_letter> --title "<group title>"
source-of-truth submit-change-set <pid> '<raw json>'  # or @file.json or - for stdin

# Hooks (consumed by the harness, not by you)
source-of-truth user-prompt-submit-hook
```

By convention `project_id == initializing session_id` (what `init-and-register` does in one step). Any unique string works otherwise.

## Hook installation

Both global hooks are installed by `python3 install.py` (see Quickstart). They fire on every Claude Code session but **self-gate on project membership** — they silently no-op for any session whose `session_id` is not in a project's `member_sessions` list, so leaving them installed is safe even when you're not using the tool.

`install.py`:
- Deploys the repo into `~/.claude/skills/source-of-truth-agent-tool/` (skipping the copy if you cloned directly into that folder).
- Writes the two wrapper scripts in that dir. Each adds the install dir to `sys.path`, calls into the `source_of_truth` package next to it, and emits `{}` on any error.
- Patches `~/.claude/settings.json` to register both hooks if not already present. Other hook entries are left untouched. `settings.json` is backed up with a timestamp.
- Initializes `~/.source-of-truth/global-settings.json` with defaults (`reviewer_mode: live`, `reviewer_model_name: claude-haiku-4-5-20251001`).
- Idempotent — safe to re-run after pulling a newer repo.

To remove cleanly:

```bash
python3 uninstall.py
```

Removes `~/.claude/skills/source-of-truth-agent-tool/` and scrubs the matching hook entries from `settings.json`. Your captured raw input logs, requirements trees, and global settings under `~/.source-of-truth/` are NOT touched.

## Storage layout

```
~/.source-of-truth/
    global-settings.json                              # optional defaults
    pending_messages_for_raw_input_sender.jsonl       # outbound queue (per-message tagged with target_project_id)
    projects/
        <project_id>/                                 # project_id = session_id of initializing session
            project-<project_id>-source-of-truth.json # the requirements tree (sole writer = our app)
            project-settings.json                     # member sessions; mode override; model override; reviewer history
            raw_input_log.json                        # rolling log, grouped by session_id, raw_input_id sequential from 0
            reviewer_thinking.log                     # full streamed log of reviewer NDJSON events
            deferred_change_sets_queue.jsonl          # only used in deferred mode
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

`char_range` rules:
- **Forbidden** when submission length ≤ 500 chars (cite the whole entry).
- **Allowed but optional** above the threshold.
- `[start, end]` inclusive, ≥ 1 char.

## Status

116 unit tests passing. Live haiku reviewer round-trip verified end-to-end with single-op, two-op, and four-call sequential tests. Hooks installed and self-gating verified across registered/unregistered/missing-package/malformed-input cases.

Schema highlights as of the latest refactor:
- Node ids are strings: `"1"`, `"2"`, … for quote leaves; `"a"`, `"b"`, …, `"aa"` for groups.
- Every node carries `short_neutral_title` (1–50 chars, the subject not the spec).
- `parent_id == "0"` is the top-level sentinel; agents must always pick a parent.
- Group nodes (`add_group` op) organize the tree; the combo shortcut (`--new-group "<title>"`) creates a group + a leaf inside it in one change-set.
- Reviewer can emit `amended_short_title` per op when a title overreaches; the amended title is persisted automatically.
