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

## MUST-CAPTURE rule

**Not everything is captured.** A question, discussion, brainstorming, or thinking-aloud is **NOT** a requirement — do not file it. But every prompt that **is** an **explicit instruction, decision, request, or answer** is a requirement and MUST be stored — *before* you act on it. This includes:
- direct commands ("do X", "add Y", "remove Z")
- dependency/choice statements ("use library Y", "make it blue", "put it top-right")
- answers to a question you asked ("yes", "no", "option B")
- **answers to an `AskUserQuestion` multiple-choice prompt** — these are auto-captured too (see below), so a `raw_input_id` is waiting for you to file

**`AskUserQuestion` answers are auto-logged.** When the user submits answers to an `AskUserQuestion` prompt, a `PostToolUse` hook records **one `raw_input_id` per question** (the selected label, comma-joined labels for multi-select, or the verbatim "Other" text) and hands you those ids back in `additionalContext`. These are explicit user decisions — file each under `pending-instructions` (or the fitting group) just like a typed prompt. (A dismissed/unanswered prompt logs nothing.)

File these under the **`pending-instructions`** group. When an instruction is carried out, reparent it to **`completed-instructions`**; when it's dropped/superseded, reparent it to **`deprecated-instructions`**. Capturing is not optional and not deferred until after the task — store first, then do the work.

**MAINTAIN — prune conflicts after every addition.** Capture is not only additive. After you add a requirement, **review the existing tree for conflicts**: if the new prompt supersedes, changes, or contradicts an existing requirement node, **reparent that now-stale node to `deprecated-instructions`** (or `remove` it) so the tree holds **only current, non-conflicting truth**. These structural ops auto-approve — just notify the user in one line. A tree that only ever grows drifts from reality; keeping it pruned is part of the per-turn duty.

**You manage this tree — you don't ask permission to use it.** Add, reparent, and re-cite on your own judgement. When you move a node to `completed-instructions` or `deprecated-instructions`, just **notify** the user in one line (e.g. "Moved 'vendor placement' to completed-instructions") — no approval needed. Using the tool is **required**, not optional: it is the only mechanism that stores guaranteed verbatim user quotes as requirements. You have no other tool that does this.

## Pre-registration items: recapture by asking

Anything the user said **before this session was registered** with the SoT project — or any
instruction that never reached the raw log (e.g. plan-mode / tool-rejection feedback, messages
sent before enrollment) — has **no `raw_input_id`**, so it cannot be cited. Do **not** fabricate
a node for it and do **not** paraphrase it into the tree. The procedure is: **ask the user a
question** that re-elicits the instruction. Their reply is auto-logged with a fresh
`raw_input_id` (an `AskUserQuestion` answer is auto-captured the same way), so you can then file
that captured reply under `pending-instructions` and act on it. In short: if it wasn't captured,
re-ask so it gets captured, then use the captured quote.

## Expected workflow (each user turn)

1. The user sends a prompt; it's auto-logged and you receive its `raw_input_id` in your turn context.
2. If it's an instruction/decision/answer, file it under `pending-instructions`; otherwise file it under the fitting group: `submit-change-set --add <raw_input_id> --parent <group> --title "<subject>"`
3. The reviewer approves (or rejects with a reason — fix and resubmit).
4. `read <node_id>` → the verbatim quote + line-numbered pre-text.
5. Trim if noisy: `pretext <node_id> <start> <end> | --all | --none`.
6. A brief reply ("yes") is fine — the pre-text carries the question, so a short answer is still a complete, citable requirement.

Do NOT dump all instructions at once. Walk the user step by step. After each step, confirm what you did and only then move to the next.

## Setup

`project-start-wizard.md` (next to this file) is the step-by-step setup — follow from the top, one step per turn.
- "skip ahead" / "already did X" → fast-forward, but first confirm prior steps produced the expected on-disk state

## After setup — capture model

- **Pre-text is auto-captured.** On each prompt the `UserPromptSubmit` hook reads the session transcript, extracts your prior turn (assistant text + tool-result summaries) — including a partial turn you interrupted/canceled — and stores it as the next entry's `pre_submission_content`.
  - So a brief reply (`yes`, `option B`) is a complete requirement — the pre-text already holds the question/plan. Don't restate it.
- **Pre-text defaults to whole.** `read` shows it line-numbered; narrow if noisy: `pretext <node_id> <start> <end>` (those lines) · `--all` (whole) · `--none` (drop).

Capture via the on-PATH `source-of-truth` wrapper. Three rules:

1. **Every node has a parent.** `parent_id` is required on every `add` op. Use `"0"` for top-level only when no appropriate parent exists. Prefer organizing under a group node (letter id like `a`, `b`, `aa`).
2. **Every node has a title.** `short_neutral_title` is required, 1–50 chars, the SUBJECT of the requirement (not the spec). The reviewer will rewrite (via `amended_short_title`) if a title overreaches the cited slice; ops aren't rejected for that.
3. **Node ids vs raw input ids.** Tree **node ids** display as `nd-<id>` (e.g. `nd-2`, `nd-e`); raw-log **input ids** display as `raw-<id>` (e.g. `raw-22`). Every id argument accepts either the prefixed or the bare form (`--parent nd-c` ≡ `--parent c`; `--add raw-7` ≡ `--add 7`); it's stripped to the bare canonical id and stored bare. Tree operations are **node-id-only** — never operate on a node by its raw input id.
4. **Group nodes organize the tree.** `add_group` op (or the combo shortcut) creates a group with auto-allocated letter id. New projects start **pre-scaffolded** with seven top-level groups — `resources` (links/paths/docs the user supplies), `user-interaction-preferences`, `technical-requirements`, `current-project-documentation`, and the instruction-lifecycle groups `pending-instructions`, `completed-instructions`, `deprecated-instructions` — so file new nodes under the fitting one (add more groups as needed).

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
source-of-truth list-raw               # raw-<id>: first 30 chars of each captured input (review what to file)
source-of-truth read-raw <raw_input_id> # one raw entry in full (submission + agent pre-text)
```

JSON form is still available for multi-op change-sets (`submit-change-set '<json>'` or `@file.json` or `-` for stdin). See `README.md` for the full op schema (add, add_group, reparent, remove, modify_reference, reorder_children).

**Reviewer scope.** Only citation-bearing ops (`add`, `add_group`, `modify_reference`) are reviewed. Structural ops (`reparent`, `remove`, `reorder_children`) carry no quote to verify, so they **auto-approve** and skip the reviewer — lifecycle moves to `completed-`/`deprecated-instructions` apply immediately even in `live` mode.
