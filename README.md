# source-of-truth-agent-tool

A Python system that prevents AI coding agents from drifting, paraphrasing, or inventing requirements over long projects.

## The idea

Every raw input the agent receives (typically from a human user, but the system is agnostic — could be an upstream agent) is captured verbatim. Requirements are then represented as a tree whose nodes contain *only references back to those raw quotes* — never agent-paraphrased text. An optional second AI agent reviews every proposed change to that tree, so the only path for hallucination to enter requirements is via deliberately misleading quote selection — which the reviewer catches.

The system is cross-AI-CLI capable via a thin adapter (Claude Code is the first concrete adapter; others can be added).

## Storage layout

```
~/.source-of-truth/
    global-settings.json                              # optional; defaults if absent
    pending_messages_for_raw_input_sender.jsonl       # global queue (per-message tagged with target_project_id)
    projects/
        <project_id>/                                 # project_id = session_id of initializing session
            project-<project_id>-source-of-truth.json # the requirements tree (sole writer = our app)
            project-settings.json                     # optional; can override global, also lists member sessions
            raw_input_log.json                        # rolling log, grouped by session_id
            reviewer_thinking.log                     # full streamed log of reviewer NDJSON events
            deferred_change_sets_queue.jsonl          # only used in deferred reviewer mode
```

## Reviewer modes

Set via `reviewer_mode` in `global-settings.json` or `reviewer_mode_override` in `project-settings.json`.

- `live` (default) — every `submit_requirements_tree_change_set` call hits the reviewer immediately. Safest, slowest, most expensive.
- `none` — reviewer is never called. Local validation runs (every reference must resolve to a real raw entry, char_range must be in bounds), then the change-set is applied directly. Fastest and cheapest; relies entirely on agent honesty.
- `deferred` — submits validate locally and queue to disk. The tree is not modified. When the agent calls `flush_deferred_change_sets_for_review()`, all queued change-sets are merged into one and reviewed in a single round-trip, then applied on approval.

## Reviewer model

Set via `reviewer_model_name` in `global-settings.json` or `reviewer_model_name_override` in `project-settings.json`. Default is `claude-haiku-4-5-20251001` for cost and speed. Override per project to use a stronger model when needed.

## Public API (agent-facing)

`source_of_truth.requirements_tree_controlled_api.RequirementsTreeControlledApi(project_id, ai_cli_adapter)`:

- `submit_requirements_tree_change_set(change_set_dict)` — main entry point. Behavior depends on the active reviewer mode.
- `flush_deferred_change_sets_for_review()` — only meaningful in deferred mode.
- `search_requirements_nodes(query)` — substring search over resolved quotes and project paths.
- `get_node_by_id(node_id, include_children=True)` — fetch a node and (optionally) its children.
- `get_top_level_node()` — render the small top-level summary that gets injected into the agent's context every turn.
- `add_project_path(filesystem_path)` / `remove_project_path(filesystem_path)` — manage the special project-paths node (paths must exist on disk; the reviewer is bypassed for these because paths are facts, not user statements).

Every API call returns or surfaces the constant `INTERACTION_TIME_AGENT_GUIDANCE` from `config.py` so the agent always has the reminder text close at hand.

## Change-set schema

A change-set is a JSON object:

```json
{
  "submitter_rationale": "free-text explanation",
  "operations": [
    {"op": "add", "parent_id": 12, "raw_input_reference": {"raw_input_id": 23, "char_range": [120, 180]}},
    {"op": "add_top_level", "raw_input_reference": {"raw_input_id": 7}},
    {"op": "reparent", "node_id": 23, "new_parent_id": 33},
    {"op": "remove", "node_id": 47},
    {"op": "modify_reference", "node_id": 23, "raw_input_reference": {"raw_input_id": 11}},
    {"op": "reorder_children", "parent_id": 12, "child_order": [4, 23, 9]}
  ]
}
```

`raw_input_id` is a per-project integer (assigned at log time, starting at 0). It is the only thing needed to identify a quote — session_id and timestamp are stored as data on the entry but are not part of the reference.

`char_range` rules per spec:
- **Forbidden** when the cited submission's length is at or under the threshold (500 chars). The whole entry is the citation.
- **Allowed but optional** when the submission length is over the threshold. Use it for precision; omit to cite the whole entry.
- When provided, it's `[start, end]` inclusive character indices and must be at least 1 character long.

## How agents are notified

Every `UserPromptSubmit` hook fires `cli_entrypoint user-prompt-submit-hook` (configured in `~/.claude/settings.json`). The hook:

1. Reads the session id from the hook stdin JSON.
2. Looks up the project via `project_identifier_resolver` (a standalone script, no package imports).
3. If the session is not registered to any source-of-truth project, the hook does nothing.
4. Otherwise it appends the submission to the project's raw input log and emits `additionalContext` containing both an acknowledgement of the log entry and the small top-level requirements summary.

## How the human is notified

Source-of-truth API calls append messages tagged with `target_project_id` to a global queue. After every Bash tool call, Claude Code fires a PostToolUse hook (also configured globally) that runs `post_tool_use_show_messages_to_raw_input_sender.py`. That hook:

1. Reads the session id from the hook stdin JSON.
2. Resolves the project; if unregistered, emits `{}` and exits.
3. Drains only messages targeted at that project; leaves others in place.
4. Emits a `systemMessage` containing the drained text, which Claude Code shows the user but does NOT inject into the agent's context.

## Reviewer subprocess

In `live` and `deferred` modes, the reviewer runs as a separate `claude -p` subprocess. Persistence is achieved via `--session-id <uuid>` on first call and `--resume <uuid>` afterwards, so server-side context is preserved without keeping a long-running child process.

Output uses `--output-format stream-json --include-partial-messages --verbose`, and every NDJSON event is appended to `reviewer_thinking.log` immediately. If the call later times out, the log still contains the full record up to the kill.

Tool sandbox: `--allowed-tools Read,WebFetch,WebSearch` and `--add-dir <project-dir>`. The reviewer does not use `--bare`.

## Hook installation

The hooks are global (they fire on every Claude Code session) but self-gate on project membership — they silently no-op for any session whose `session_id` is not in a project's `member_sessions` list. Safe to leave installed.

Because the hooks must be findable from any cwd in any session, install thin wrapper scripts that do their own `sys.path` setup and swallow all errors (so unrelated sessions never see import errors).

1. Copy these wrappers somewhere absolute, e.g. `~/.claude/hooks/`:
   - `source_of_truth_user_prompt_submit_hook.py`
   - `source_of_truth_post_tool_use_hook.py`

   Each is a small file that inserts the package directory into `sys.path` and calls into either `source_of_truth.cli_entrypoint._handle_user_prompt_submit_hook` or `source_of_truth.post_tool_use_show_messages_to_raw_input_sender._main`. On any exception (missing package, malformed stdin, etc.) they emit `{}` and exit 0.

2. Register them in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {"matcher": "*", "hooks": [{
        "type": "command",
        "command": "python3 /home/aikenyon/.claude/hooks/source_of_truth_user_prompt_submit_hook.py"
      }]}
    ],
    "PostToolUse": [
      {"matcher": "Bash", "hooks": [{
        "type": "command",
        "command": "python3 /home/aikenyon/.claude/hooks/source_of_truth_post_tool_use_hook.py"
      }]}
    ]
  }
}
```

## Initializing a project

```bash
python3 -m source_of_truth.cli_entrypoint init-project <project_id>
python3 -m source_of_truth.cli_entrypoint add-session <project_id> <session_id> <conversation_path>
python3 -m source_of_truth.cli_entrypoint add-path <project_id> <filesystem_path>
python3 -m source_of_truth.cli_entrypoint show-top-level <project_id>
```

By convention `project_id` is the session id of the session that initialized the project, but any unique string works.

## Tests

```bash
python3 -m pytest tests/ -q
```

44 unit tests covering: file lock concurrency, change-set application for every operation type, reference validation (out-of-bounds, missing range when over the threshold, missing entry), the standalone project resolver, raw log writer truncation and grouping, project-path validation, queued user-message routing per project, model resolution priority (project override → global → default), the three reviewer modes including deferred flush behavior, and the streaming reviewer subprocess (mocked Popen).

## Status

Capture, validation, application, queuing, and all three reviewer modes are implemented and unit-tested. The live reviewer subprocess is implemented but the round-trip latency on Opus is impractical; defaulting the reviewer model to Haiku is a workaround. Live end-to-end smoke testing of the reviewer round-trip is the open work item.

## License

MIT
