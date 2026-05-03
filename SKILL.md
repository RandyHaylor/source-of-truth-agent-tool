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
