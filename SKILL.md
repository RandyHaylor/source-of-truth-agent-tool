---
name: source-of-truth-agent-tool
description: Walk the user through getting started with the source-of-truth-agent-tool (a verbatim-quote-based requirements ledger that prevents AI agents from drifting on long projects). Trigger when the user has cloned or installed the repo and asks how to get started, how to use it, how to set it up for their project, how to register a session, how to pick a reviewer mode, or anything similar about post-install setup.
---

# source-of-truth-agent-tool — start-here skill

Goal: get the user from "the hooks are installed" to "this project is registered, the mode is picked, the next prompt I type will be captured and the agent can build the requirements tree."

Do NOT dump all instructions at once. Walk the user step by step. After each step, confirm what you did and only then move to the next.

The full step-by-step wizard lives at `project-start-wizard.md` next to this file. Read that file and follow it from the top, one step per turn.

If the user says "skip ahead" or "I already did X," you can fast-forward, but always confirm the prior steps actually produced the expected on-disk state before moving on.

If at any point you find a missing prerequisite (install dir not present, settings.json missing the hook entries, etc.), say so plainly and point at `install.py` rather than improvising a workaround.
