# project-start-wizard

Step-by-step setup walkthrough for source-of-truth-agent-tool. Triggered by SKILL.md.

Run **one step per turn**. After each step, summarize what you confirmed and ask the user before continuing. Use plain language; do not paste large blocks of code unless the user asks.

---

## Step 0 — Verify install

Check that the install ran. The hooks are installed if both of these exist:
- `~/.claude/hooks/source-of-truth-agent-tool/source_of_truth/cli_entrypoint.py`
- An entry in `~/.claude/settings.json` under `hooks.UserPromptSubmit` whose command path contains `source-of-truth-agent-tool`

If either is missing, tell the user to run `python3 install.py` from the cloned repo root, then come back. Do NOT proceed without this.

If both exist, say so briefly and ask "ready to register your current Claude Code session as a source-of-truth project?"

---

## Step 1 — Find the current session_id

Locate the session id of the Claude Code session the user is in right now. The most reliable source is the user's terminal/UI, but you can also help by listing recent jsonl files:

```bash
ls -lt ~/.claude/projects/<encoded-cwd>/*.jsonl | head -5
```

Where `<encoded-cwd>` is the user's working directory with `/` replaced by `-` (and a leading `-`). If you can't infer it, ask the user where they're running Claude Code from and offer to look.

Show the user the candidate session_id(s) you found and confirm which one is current.

---

## Step 2 — Initialize and register the project

Once the session_id is confirmed, run:

```bash
sot init-and-register <session_id> ~/.claude/projects/<encoded-cwd>/<session_id>.jsonl
```

This creates `~/.source-of-truth/projects/<session_id>/` with an empty tree and adds the session as a member. By convention `project_id == initializing session_id`.

If `sot` isn't on PATH, fall back to:

```bash
python3 -c "import sys; sys.path.insert(0, '/path/to/source-of-truth'); from source_of_truth.cli_entrypoint import _main; sys.exit(_main())" init-and-register <session_id> <conversation_path>
```

Confirm the output says `initialized` and `added`.

---

## Step 3 — Pick a reviewer mode

Ask the user which mode they want, with this short explanation:

- **live** (default) — every requirement-capture submit hits a Haiku reviewer (~13–18s/call). Safest. Pick this if you want maximum protection against the agent miscapturing.
- **none** — reviewer never called; ops apply directly after local validation. Fastest and free. Pick this if you trust the agent and want raw speed.
- **deferred** — submits queue up. Tree stays unchanged until the agent calls `flush_deferred_change_sets_for_review()` to merge and review the batch. Pick this if the agent will do extended planning before any review is useful.

Then run:

```bash
sot set-mode <session_id> live          # or none, or deferred
```

Confirm the output says the override was set.

---

## Step 4 — Optional: pin project paths

Ask if the user wants the agent to know about specific filesystem paths (e.g. their working repo, reference dirs):

```bash
sot add-path <session_id> /absolute/path/to/their/repo
```

Paths must exist (validated via `os.path.exists`). Stored on a special project-paths node, not subject to reviewer (paths are facts, not statements).

Skip this if the user has nothing they want pinned.

---

## Step 5 — Confirm hooks are firing

Tell the user: "Type any message in this session. After you send, you should see the SoT additionalContext block confirming the submission was logged with a `raw_input_id`."

If they don't see it after sending one message, something is wrong — most likely the hooks weren't actually installed, or this session was started BEFORE the hooks were installed (settings.json is read at session startup; existing sessions need a restart). Ask them to start a new Claude Code session and re-run from Step 1 if needed.

---

## Step 6 — Tell the agent it's set up (this turn)

In the agent's response after the wizard completes, the agent should briefly state:
- The project_id
- The active reviewer mode
- Any pinned paths
- That every prompt from now on is auto-logged
- That the agent can call `submit_requirements_tree_change_set(...)` to add nodes referencing logged `raw_input_id`s

This grounds future turns: the agent now knows the project is live and can start using the API as the canonical capture mechanism.

---

## Step 7 — Optional: tell future sessions

If the user works across multiple Claude Code sessions in the same project, suggest they drop a `CLAUDE.md` (or note in their existing one) at the working dir saying:

> "This directory is registered to source-of-truth project `<project_id>`. To use SoT, run `sot add-session <project_id> $CURRENT_SESSION_ID <path-to-jsonl>` once at the start of any new session."

That way new sessions know to enroll themselves into the same project rather than starting fresh ones.

---

## Done

Stop the wizard. Answer any follow-up questions naturally. Don't keep narrating the wizard once setup is complete.
