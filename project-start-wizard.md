# project-start-wizard

Step-by-step setup walkthrough for source-of-truth-agent-tool. Triggered by SKILL.md.

Run **one step per turn**. After each step, summarize what you confirmed and ask the user before continuing. Use plain language; do not paste large blocks of code unless the user asks.

---

## Step 0 — One-time install (skip if `source-of-truth` already works)

First time on this machine only: run `python3 ~/.claude/skills/source-of-truth-agent-tool/install.py` once (or from wherever the user cloned the repo) so the hooks and the `source-of-truth` command get set up. If it's already installed, skip to Step 1.

Then ask: "ready to register your current Claude Code session as a source-of-truth project?"

---

## Step 1 — Find the current session_id

**Reliable way — read the environment variable.** The live session id is available to this session's shell, so read it directly:

```bash
printenv CLAUDE_CODE_SESSION_ID
```

That prints the real, current session id — use it directly, no guessing. (This works *before* registration; the `what-is-session-id` sentinel hook is gated on project membership like every other SoT hook, so it only responds once the session is already enrolled — it's a post-registration confirmation, not a bootstrap.)

**Fallback** (only if the env var is empty): list recent transcripts under `~/.claude/projects/<encoded-cwd>/` and confirm the right `<session_id>.jsonl` with the user.

```bash
ls -lt ~/.claude/projects/<encoded-cwd>/*.jsonl | head -5
```

Where `<encoded-cwd>` is the working directory with `/` replaced by `-` (and a leading `-`). Show the candidate(s) and confirm which is current.

---

## Step 2 — Initialize and register the project

Once the session_id is confirmed, run:

```bash
source-of-truth init-and-register <session_id> ~/.claude/projects/<encoded-cwd>/<session_id>.jsonl
```

This creates `~/.source-of-truth/projects/<session_id>/` with an empty tree and adds the session as a member. By convention `project_id == initializing session_id`.

If `source-of-truth` isn't on PATH, fall back to:

```bash
python3 -c "import sys; sys.path.insert(0, '/path/to/source-of-truth'); from source_of_truth.cli_entrypoint import _main; sys.exit(_main())" init-and-register <session_id> <conversation_path>
```

Confirm the output says `initialized` and `added`.

---

## Step 3 — Pick a reviewer mode

Ask the user which mode they want, with this short explanation:

- **live** (default) — every requirement-capture submit hits a Haiku reviewer (~13–18s/call). Safest. Pick this if you want maximum protection against the agent miscapturing.
- **none** — reviewer never called; ops apply directly after local validation. Fastest and free. Pick this if you trust the agent and want raw speed.
- **deferred** — submits queue up. Tree stays unchanged until the agent runs `source-of-truth flush-deferred` (or calls the equivalent in-process API) to merge and review the batch. Pick this if the agent will do extended planning before any review is useful.

Then run:

```bash
source-of-truth set-mode live          # or none, or deferred (project resolved from your session)
```

Confirm the output says the override was set.

---

## Step 4 — Optional: pin project paths

Ask if the user wants the agent to know about specific filesystem paths (e.g. their working repo, reference dirs):

```bash
source-of-truth add-path <session_id> /absolute/path/to/their/repo
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
- That this session is now enrolled in a source-of-truth project (commands resolve it automatically — no project id to pass)
- The active reviewer mode
- Any pinned paths
- That every prompt from now on is auto-logged
- That the agent can capture nodes by running `source-of-truth submit-change-set --add <raw_input_id> --parent <parent_id_or_letter> --title "<subject>"` (or the combo form with `--new-group "<group>"`); see SKILL.md for the full shortcut + JSON forms

This grounds future turns: the agent now knows the project is live and can start using the API as the canonical capture mechanism.

---

## Step 7 — Optional: tell future sessions

If the user works across multiple Claude Code sessions in the same project, suggest they drop a `CLAUDE.md` (or note in their existing one) at the working dir saying:

> "This directory is registered to source-of-truth project `<project_id>`. To use SoT, run `source-of-truth add-session <project_id> $CURRENT_SESSION_ID <path-to-jsonl>` once at the start of any new session."

That way new sessions know to enroll themselves into the same project rather than starting fresh ones.

---

## Done

Stop the wizard. Answer any follow-up questions naturally. Don't keep narrating the wizard once setup is complete.
