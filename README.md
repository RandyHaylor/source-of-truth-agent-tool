# source-of-truth-agent-tool

**Stop your AI coding agent from drifting away from what you actually asked for.**

## The problem

You ask an AI agent for X. Twenty turns later it has paraphrased X into something subtly different and is now defending the paraphrase. By turn fifty the original requirement is gone — never written down verbatim, only restated through the agent's filter. There is no way to point at a single line and say "this is what was asked for."

This tool fixes that.

## How it fixes it

1. **Every raw input you send is captured verbatim** to a per-project log file at write-time, untouched.
2. The agent is allowed to maintain a **requirements tree**, but every node in that tree is **only a reference to a verbatim quote** in the log — never agent prose. Nothing the agent can write goes into the tree directly.
3. Every proposed edit to the tree (add, move, remove, modify reference, reorder) is sent to a **separate AI reviewer subprocess** (Haiku by default — fast and cheap) which returns a per-operation approve/reject verdict with reasons.
4. Only approved operations land on disk. Rejected ones come back to the agent with the reviewer's reasoning.
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
# 1. Clone
git clone git@github.com:RandyHaylor/source-of-truth-agent-tool.git
cd source-of-truth-agent-tool

# 2. (Optional but recommended) Drop a small wrapper on PATH
cat > ~/.local/bin/sot <<EOF
#!/usr/bin/env bash
exec python3 -c "import sys; sys.path.insert(0, '$(pwd)'); from source_of_truth.cli_entrypoint import _main; sys.exit(_main())" "\$@"
EOF
chmod +x ~/.local/bin/sot

# 3. Run the unit tests
python3 -m pytest tests/ -q

# 4. Initialize a project for your CURRENT Claude Code session.
#    Find the session id from ~/.claude/projects/<encoded-cwd>/<session_id>.jsonl
#    or from your Claude Code UI.
sot init-and-register <your_session_id> ~/.claude/projects/<encoded-cwd>/<your_session_id>.jsonl

# 5. Pick a reviewer mode. Default is "live" (every submit gets reviewed).
sot set-mode <your_session_id> live    # or: none, deferred
```

After that, install the two global hooks (see "Hook installation" below). With the hooks installed, every user prompt in any registered session is auto-logged, and any reviewer outcome messages auto-surface to you via Claude Code's `systemMessage`.

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
        {"op": "add_top_level",
         "raw_input_reference": {"raw_input_id": 41}},
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
sot init-and-register <session_id> <conversation_path>      # one-shot project setup
sot init-project       <project_id>                         # init only
sot add-session        <project_id> <session_id> <conversation_path>
sot add-path           <project_id> <filesystem_path>       # add to project-paths special node
sot set-mode           <project_id> live|none|deferred
sot show-top-level     <project_id>
sot user-prompt-submit-hook                                 # consumed by the hook wrapper, not by you
```

By convention `project_id == initializing session_id` (what `init-and-register` does in one step). Any unique string works otherwise.

## Hook installation

Two global hooks. Both fire on every Claude Code session but **self-gate on project membership** — they silently no-op for any session whose `session_id` is not in a project's `member_sessions` list. Safe to leave installed.

Install thin wrapper scripts that do their own `sys.path` setup and emit `{}` on any error (so unrelated sessions never see import errors):

`~/.claude/hooks/source_of_truth_user_prompt_submit_hook.py`:
```python
#!/usr/bin/env python3
import sys
def _emit_empty_and_exit_silently(): print("{}"); sys.exit(0)
def _main():
    try:
        sys.path.insert(0, "/abs/path/to/source-of-truth")
        from source_of_truth.cli_entrypoint import _handle_user_prompt_submit_hook
    except Exception: _emit_empty_and_exit_silently(); return
    try: sys.exit(_handle_user_prompt_submit_hook())
    except Exception: _emit_empty_and_exit_silently()
if __name__ == "__main__": _main()
```

`~/.claude/hooks/source_of_truth_post_tool_use_hook.py`: same shape, importing `source_of_truth.post_tool_use_show_messages_to_raw_input_sender._main`.

Then in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {"matcher": "*", "hooks": [{
        "type": "command",
        "command": "python3 /home/<you>/.claude/hooks/source_of_truth_user_prompt_submit_hook.py"
      }]}
    ],
    "PostToolUse": [
      {"matcher": "Bash", "hooks": [{
        "type": "command",
        "command": "python3 /home/<you>/.claude/hooks/source_of_truth_post_tool_use_hook.py"
      }]}
    ]
  }
}
```

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

```json
{
  "submitter_rationale": "free-text",
  "operations": [
    {"op": "add",              "parent_id": 12, "raw_input_reference": {"raw_input_id": 23, "char_range": [120, 180]}},
    {"op": "add_top_level",                       "raw_input_reference": {"raw_input_id": 7}},
    {"op": "reparent",         "node_id": 23, "new_parent_id": 33},
    {"op": "remove",           "node_id": 47},
    {"op": "modify_reference", "node_id": 23, "raw_input_reference": {"raw_input_id": 11}},
    {"op": "reorder_children", "parent_id": 12, "child_order": [4, 23, 9]}
  ]
}
```

`raw_input_id` is a per-project integer assigned at log time, starting at 0. Session and timestamp are stored on the entry as data but the reference is just the integer.

`char_range` rules per spec:
- **Forbidden** when the cited submission's length is at or under the threshold (500 chars). The whole entry is the citation.
- **Allowed but optional** when the submission length is over the threshold.
- When provided it's `[start, end]` inclusive character indices and must be at least 1 character long.

## Status

57 unit tests passing. Live haiku reviewer round-trip verified end-to-end with single-op, two-op, and four-call sequential tests. Hooks installed and self-gating verified across registered/unregistered/missing-package/malformed-input cases. Tree on disk for the bootstrap project (`be2988e2-...`) holds 14 captured requirement nodes from the build of this tool itself.
