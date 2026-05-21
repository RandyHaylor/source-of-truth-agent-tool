---
name: source-of-truth-agent-tool
description: Walk the user through getting started with the source-of-truth-agent-tool (a verbatim-quote-based requirements ledger that prevents AI agents from drifting on long projects). Trigger when the user has cloned or installed the repo and asks how to get started, how to use it, how to set it up for their project, how to register a session, how to pick a reviewer mode, or anything similar about post-install setup.
---

# source-of-truth-agent-tool — start-here skill

Goal: get the user from "the hooks are installed" to "this project is registered, the mode is picked, the next prompt I type will be captured and the agent can build the requirements tree."

Do NOT dump all instructions at once. Walk the user step by step. After each step, confirm what you did and only then move to the next.

## Always run install.py first as a health check

Before doing anything else with this skill, run `python3 install.py` from the install dir. It is **idempotent and safe to re-run**:
- If everything is already correctly installed, it reports each step as a no-op.
- If the hook entries in `~/.claude/settings.json` are missing, stale, or pointing at an old location, it scrubs them and writes the correct ones.
- If the wrapper scripts or copied package are missing or out of date, it rewrites them.
- If `~/.source-of-truth/global-settings.json` is missing, it writes the defaults.

Do this every time you start setting up a project with this skill. It's the canonical way to be sure the hooks and on-disk state are healthy before relying on them.

The install dir is `~/.claude/skills/source-of-truth-agent-tool/` (where this SKILL.md lives). If the user cloned the repo elsewhere, use the install.py at the cloned location — it will deploy itself into the skill folder.

## Then follow the wizard

The full step-by-step setup walkthrough lives at `project-start-wizard.md` next to this file. Read it and follow it from the top, one step per turn.

If the user says "skip ahead" or "I already did X," you can fast-forward, but always confirm the prior steps actually produced the expected on-disk state before moving on.

If at any point you find a missing prerequisite (install dir not present, settings.json missing the hook entries, etc.), re-run `install.py` rather than improvising a workaround.

## After setup — capture model in one screen

**Pre-text is captured for you automatically.** A `Stop` hook records your previous turn's output (assistant text + tool-result summaries) and a `UserPromptSubmit` hook stores it as the next entry's `pre_submission_content`. So when you ask the user a question and they answer briefly (`yes`, `option B`), you can capture that short reply as a requirement node — the pre-text already carries the question/plan they were answering. You don't need to restate it.

A new node includes the **whole** pre-text by default. When you `read` a node you'll see its pre-text line-numbered; if it's noisy, narrow it: `source-of-truth pretext <node_id> <start> <end>` (cite only those lines), `--all` (whole), or `--none` (drop it). No project id needed — it's resolved from your session.

Once the wizard finishes, the agent captures requirements via the on-PATH `source-of-truth` wrapper. Three rules to remember:

1. **Every node has a parent.** `parent_id` is required on every `add` op. Use `"0"` for top-level only when no appropriate parent exists. Prefer organizing under a group node (letter id like `a`, `b`, `aa`).
2. **Every node has a title.** `short_neutral_title` is required, 1–50 chars, the SUBJECT of the requirement (not the spec). The reviewer will rewrite (via `amended_short_title`) if a title overreaches the cited slice; ops aren't rejected for that.
3. **Group nodes organize the tree.** `add_group` op (or the combo shortcut) creates a group with auto-allocated letter id. New projects start **pre-scaffolded** with four top-level groups — `resources` (links/paths/docs the user supplies), `user-interaction-preferences`, `technical-requirements`, `current-project-documentation` — so file new nodes under the fitting one (add more groups as needed).

Three convenience-flag shortcuts for `submit-change-set`, listed in promotion order:

```bash
# Combo (encouraged) — creates a new group AND a leaf inside it in one change-set
source-of-truth submit-change-set <project_id> \
  --add <raw_input_id> --parent <pid_or_letter> --title "<leaf>" --new-group "<group title>"

# Leaf only — under an existing parent (group letter id, leaf id, or "0")
source-of-truth submit-change-set <project_id> \
  --add <raw_input_id> --parent <pid_or_letter> --title "<leaf title>"

# Group only
source-of-truth submit-change-set <project_id> \
  --add-group --parent <pid_or_letter> --title "<group title>"
```

Read / view:

```bash
source-of-truth show-tree   <project_id>            # default: indented "<id> <title>" only
source-of-truth show-tree   <project_id> --show-all # add inlined raw quote text for top 2 levels
source-of-truth read        <project_id> <id> [<id> ...]   # mixed leaf + group ids
source-of-truth search-nodes <project_id> <query>
```

JSON form is still available for multi-op change-sets (`submit-change-set <pid> '<json>'` or `@file.json` or `-` for stdin). See `README.md` for the full op schema (add, add_group, reparent, remove, modify_reference, reorder_children).
