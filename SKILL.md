---
name: source-of-truth-agent-tool
description: Walk the user through getting started with the source-of-truth-agent-tool (a verbatim-quote-based requirements ledger that prevents AI agents from drifting on long projects). Trigger when the user has cloned or installed the repo and asks how to get started, how to use it, how to set it up for their project, how to register a session, how to pick a reviewer mode, or anything similar about post-install setup.
---

> **YOU MUST REGISTER THE CURRENT SESSION WITH A SOURCE OF TRUTH (SOT) PROJECT FIRST**

# source-of-truth-agent-tool — start-here skill

The entire point of this skill is to have the script copy verbatim user quotes and allow the agent to arrange them into a convenient organized requirements doc.

This solves the issue of ai agents using interpretation and paraphrasing, losing critical requirement details.

Goal: take the user from *hooks installed* → *project registered, mode picked, prompts capturing, tree building*.

## What this system is

- The requirements tree is **pointers to the user's verbatim quotes** — auto-logged on every prompt.
- You never write requirement text. You only add **short subject titles** for nodes and groups.
- Commands take **no project id** — it's resolved from your session. (If you're not in a project yet, see setup below.)
- Each prompt hands you a `raw_input_id`. File it under a group:
  `submit-change-set --add <raw_input_id> --parent <group> --title "<subject>"`
- `read <node_id>` → the verbatim quote + line-numbered pre-text.
- `pretext <node_id> <start> <end> | --all | --none` → trim a node's pre-text.
- Payoff: requirements stay **verbatim, incorruptible, organized**.

## Expected workflow (each user turn)

1. The user sends a prompt; it's auto-logged and you receive its `raw_input_id` in your turn context.
2. File it under the fitting group: `submit-change-set --add <raw_input_id> --parent <group> --title "<subject>"`
3. The reviewer approves (or rejects with a reason — fix and resubmit).
4. `read <node_id>` → the verbatim quote + line-numbered pre-text.
5. Trim if noisy: `pretext <node_id> <start> <end> | --all | --none`.
6. A brief reply ("yes") is fine — the pre-text carries the question, so a short answer is still a complete, citable requirement.

Do NOT dump all instructions at once. Walk the user step by step. After each step, confirm what you did and only then move to the next.

## Setup

`project-start-wizard.md` (next to this file) is the step-by-step setup — follow from the top, one step per turn.
- "skip ahead" / "already did X" → fast-forward, but first confirm prior steps produced the expected on-disk state

## After setup — capture model

- **Pre-text is auto-captured.** A `Stop` hook records your prior turn (assistant text + tool-result summaries); a `UserPromptSubmit` hook stores it as the next entry's `pre_submission_content`.
  - So a brief reply (`yes`, `option B`) is a complete requirement — the pre-text already holds the question/plan. Don't restate it.
- **Pre-text defaults to whole.** `read` shows it line-numbered; narrow if noisy: `pretext <node_id> <start> <end>` (those lines) · `--all` (whole) · `--none` (drop).

Capture via the on-PATH `source-of-truth` wrapper. Three rules:

1. **Every node has a parent.** `parent_id` is required on every `add` op. Use `"0"` for top-level only when no appropriate parent exists. Prefer organizing under a group node (letter id like `a`, `b`, `aa`).
2. **Every node has a title.** `short_neutral_title` is required, 1–50 chars, the SUBJECT of the requirement (not the spec). The reviewer will rewrite (via `amended_short_title`) if a title overreaches the cited slice; ops aren't rejected for that.
3. **Group nodes organize the tree.** `add_group` op (or the combo shortcut) creates a group with auto-allocated letter id. New projects start **pre-scaffolded** with four top-level groups — `resources` (links/paths/docs the user supplies), `user-interaction-preferences`, `technical-requirements`, `current-project-documentation` — so file new nodes under the fitting one (add more groups as needed).

`submit-change-set` shortcuts (promotion order):

```bash
# Combo (encouraged) — creates a new group AND a leaf inside it in one change-set
source-of-truth submit-change-set \
  --add <raw_input_id> --parent <parent_id_or_letter> --title "<leaf>" --new-group "<group title>"

# Leaf only — under an existing parent (group letter id, leaf id, or "0")
source-of-truth submit-change-set \
  --add <raw_input_id> --parent <parent_id_or_letter> --title "<leaf title>"

# Group only
source-of-truth submit-change-set \
  --add-group --parent <parent_id_or_letter> --title "<group title>"
```

Read / view:

```bash
source-of-truth show-tree              # default: indented "<id> <title>" only
source-of-truth show-tree --show-all   # add inlined raw quote text for top 2 levels
source-of-truth read <id> [<id> ...]   # mixed leaf + group ids
source-of-truth search-nodes <query>
```

JSON form is still available for multi-op change-sets (`submit-change-set '<json>'` or `@file.json` or `-` for stdin). See `README.md` for the full op schema (add, add_group, reparent, remove, modify_reference, reorder_children).
