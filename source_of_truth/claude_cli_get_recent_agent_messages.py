#!/usr/bin/env python3
"""
claude_cli_get_recent_agent_messages.py
========================================

A Claude Code Stop-hook handler that extracts the assistant's text replies
emitted since the most recent user message in the session transcript.

This is a READ-ONLY extractor. It produces output on stdout. It does NOT
make decisions about Claude's flow (no block/continue signaling). Pipe its
output into another script that consumes it and decides what to do.


CLI USAGE
---------

Standalone (for testing, with explicit transcript path):

    python3 claude_cli_get_recent_agent_messages.py \\
        --transcript-path ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl

Hook context (reads JSON payload from stdin per Claude Code's hook contract):

    echo '{"transcript_path": "/path/to/session.jsonl"}' \\
        | python3 claude_cli_get_recent_agent_messages.py

Get raw NDJSON instead of plain text:

    python3 claude_cli_get_recent_agent_messages.py \\
        --transcript-path <path> --json

Include tool calls as one-line summaries (text mode only):

    python3 claude_cli_get_recent_agent_messages.py \\
        --transcript-path <path> --include-tool-calls

Custom separator between messages:

    python3 claude_cli_get_recent_agent_messages.py \\
        --transcript-path <path> --separator "---"


FLAGS
-----

--json
    Emit raw JSON events (NDJSON) for the collected assistant messages
    instead of stripped text. Use when piping to a consumer that wants
    structure.

--include-tool-calls
    In text mode, also emit a compact summary line for each tool_use
    block:  `[tool: <name>] <one-line JSON of input>`. Default omits
    tool calls entirely. Has no effect in --json mode (which already
    preserves everything).

--transcript-path PATH
    Bypass stdin payload reading and use the given path directly. Useful
    for testing the script outside the hook context.

--separator SEP
    String inserted between assistant messages in text mode. Default is
    a single blank line ("\\n\\n"). Use "\\n" for tighter output or a
    custom marker like "---" for downstream parsing.


EXIT CODES
----------

  0 — success; output written to stdout
  1 — usage error or transcript not found
  2 — payload malformed (no transcript_path)


SUGGESTED HOOK WIRING
---------------------

In ~/.claude/settings.json (user scope) or .claude/settings.json (project scope):

    {
      "hooks": {
        "Stop": [
          {
            "hooks": [
              {
                "type": "command",
                "command": "python3 /absolute/path/to/claude_cli_get_recent_agent_messages.py | python3 /absolute/path/to/your_consumer.py"
              }
            ]
          }
        ]
      }
    }

The pipe sends the extractor's stdout into your consumer's stdin. The
consumer is whatever script you write to act on the assistant's last
replies — log them, scan for tokens, ship to a webhook, etc.

Examples of useful consumers:

    # Just log to a file
    ... | tee -a ~/claude-replies.log >/dev/null

    # Look for sentinel tokens (DONE, FEATURE_COMPLETE) on their own line
    ... | grep -xE '(DONE|FEATURE_COMPLETE)' && touch /tmp/turn_done

    # Pipe NDJSON to a Python consumer that parses each event
    python3 claude_cli_get_recent_agent_messages.py --json | python3 my_parser.py


WHY NOT JUST PARSE THE TRANSCRIPT YOURSELF?
-------------------------------------------

You can. This script exists because:

  - It handles the stdin-payload contract correctly (hooks pass a JSON
    object containing `transcript_path`).
  - It correctly defines "replies since the last user message" — there
    can be multiple assistant turns between user messages (tool-use
    loops, continued generation, etc.), and all of them should be
    captured.
  - It strips tool_use, tool_result, and thinking blocks by default,
    leaving only text the assistant emitted toward the user.
  - It's a single-file, stdlib-only utility you can drop in anywhere.


DESIGN NOTES
------------

  - Pure stdlib; no external dependencies.
  - Pipe-friendly: text output is plain text, JSON output is NDJSON.
  - Does NOT modify the transcript or make decisions about the hook flow.
    The hook's exit code from settings.json controls Claude's flow;
    this script's exit code only signals its own success/failure.
  - If you want this script's output to be acted on, pipe it to another
    script that consumes stdout and decides what to do.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract assistant replies since the last user message from a Claude Code transcript.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON events (NDJSON) instead of stripped text.",
    )
    parser.add_argument(
        "--include-tool-calls",
        action="store_true",
        help="In text mode, also emit a one-line summary for each tool_use block (the CALL).",
    )
    parser.add_argument(
        "--tool-results",
        action="store_true",
        dest="tool_results",
        help="In text mode, also include tool_result OUTPUT blocks (the result "
             "returned to the assistant), summarized as '[tool_result] <text>'. "
             "Distinct from --include-tool-calls, which summarizes the call.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        dest="max_chars",
        help="If set, emit only the LAST N characters of the text output (the "
             "'most recent, from the bottom' capture window). Intentionally has "
             "NO default: the caller supplies the value from settings so the "
             "window size is never hard-coded in this portable script.",
    )
    parser.add_argument(
        "--transcript-path",
        type=str,
        default=None,
        help="Override transcript path (bypass stdin). For testing.",
    )
    parser.add_argument(
        "--separator",
        type=str,
        default="\n\n",
        help="Separator between assistant messages in text mode. Default: blank line.",
    )
    return parser.parse_args()


def read_hook_payload() -> dict:
    """Read the JSON payload from stdin (Claude Code hook input)."""
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"ERROR: stdin payload is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)


def resolve_transcript_path(args: argparse.Namespace) -> Path:
    """Either use the CLI override or read from the hook payload."""
    if args.transcript_path:
        path = Path(args.transcript_path)
    else:
        payload = read_hook_payload()
        if "transcript_path" not in payload:
            print(
                "ERROR: hook payload missing 'transcript_path' field. "
                "Are you sure this script was invoked from a Stop hook?",
                file=sys.stderr,
            )
            sys.exit(2)
        path = Path(payload["transcript_path"])

    if not path.exists():
        print(f"ERROR: transcript not found at {path}", file=sys.stderr)
        sys.exit(1)
    return path


def parse_events(path: Path) -> Iterator[dict]:
    """Yield parsed events from a JSONL file. Tolerates malformed lines."""
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines (e.g., partial trailing writes).
                continue


def _is_genuine_user_prompt(event: dict) -> bool:
    """True only for a real user prompt, NOT a tool result.

    Claude Code records tool results as type=="user" events whose
    message.content is a list containing tool_result blocks. A genuine user
    prompt has message.content as a plain string (or a list with no
    tool_result blocks, e.g. text+attachment prompts). Tool results must not
    count as the "last user message" boundary, otherwise assistant text
    emitted during a tool-use loop (the common case) is missed and the
    extractor returns empty.
    """
    if event.get("type") != "user":
        return False
    content = event.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


def find_assistant_events_since_last_user(events: list[dict]) -> list[dict]:
    """Return all assistant events after the most recent genuine user prompt.

    Tool-result events (also type=="user") are skipped when locating the
    boundary so that all assistant text across a within-turn tool-use loop
    is captured, per this module's stated contract.
    """
    last_user_index = -1
    for i, event in enumerate(events):
        if _is_genuine_user_prompt(event):
            last_user_index = i

    return [
        event
        for event in events[last_user_index + 1 :]
        if event.get("type") == "assistant"
    ]


def extract_text_blocks(assistant_event: dict, include_tool_calls: bool) -> list[str]:
    """Extract text content from an assistant event.

    Returns a list of strings, one per content block. Text blocks become
    their text; tool_use blocks become a summary line (only when
    include_tool_calls is True).
    """
    message = assistant_event.get("message", {})
    content = message.get("content", [])
    if not isinstance(content, list):
        return []

    pieces: list[str] = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text", "")
            if text:
                pieces.append(text)
        elif block_type == "tool_use" and include_tool_calls:
            tool_name = block.get("name", "<unknown>")
            tool_input = block.get("input", {})
            try:
                input_repr = json.dumps(tool_input, separators=(",", ":"))
            except (TypeError, ValueError):
                input_repr = str(tool_input)
            pieces.append(f"[tool: {tool_name}] {input_repr}")
        # Other block types (tool_result, thinking, etc.) ignored.
    return pieces


def extract_tool_result_blocks(user_event: dict) -> list[str]:
    """Extract tool_result OUTPUT text from a user event.

    Claude Code stores tool results as type=='user' events whose
    message.content is a list of tool_result blocks. Each tool_result block's
    own 'content' is usually a plain string, but may be a list of text blocks.
    Returns one '[tool_result] <text>' string per non-empty result.
    """
    message = user_event.get("message", {})
    content = message.get("content", [])
    if not isinstance(content, list):
        return []

    pieces: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        result_content = block.get("content", "")
        if isinstance(result_content, str):
            text = result_content
        elif isinstance(result_content, list):
            parts = []
            for inner_block in result_content:
                if isinstance(inner_block, dict) and inner_block.get("type") == "text":
                    parts.append(inner_block.get("text", ""))
                elif isinstance(inner_block, str):
                    parts.append(inner_block)
            text = "\n".join(part for part in parts if part)
        else:
            text = ""
        if text:
            pieces.append(f"[tool_result] {text}")
    return pieces


def find_events_since_last_user_prompt(events: list[dict]) -> list[dict]:
    """Return ALL events (any type, in chronological order) after the most
    recent genuine user prompt.

    Unlike find_assistant_events_since_last_user, this keeps the interleaved
    tool-result (type=='user') events so a consumer can include tool output.
    Tool-result events are not treated as the boundary.
    """
    last_user_index = -1
    for i, event in enumerate(events):
        if _is_genuine_user_prompt(event):
            last_user_index = i
    return events[last_user_index + 1 :]


def emit_text(
    relevant_events: list[dict],
    include_tool_calls: bool,
    include_tool_results: bool,
    separator: str,
    max_chars: "int | None",
) -> None:
    """Print plain text: assistant text (and optionally tool_use call summaries
    and/or tool_result output) since the last user prompt, in chronological
    order.

    When max_chars is set, only the LAST max_chars characters of the assembled
    output are emitted -- the 'most recent, from the bottom' capture window.
    """
    messages: list[str] = []
    for event in relevant_events:
        event_type = event.get("type")
        if event_type == "assistant":
            pieces = extract_text_blocks(event, include_tool_calls)
            if pieces:
                messages.append("\n".join(pieces))
        elif event_type == "user" and include_tool_results:
            pieces = extract_tool_result_blocks(event)
            if pieces:
                messages.append("\n".join(pieces))

    if not messages:
        return
    output_text = separator.join(messages)
    if max_chars is not None and max_chars >= 0:
        output_text = output_text[-max_chars:]
    sys.stdout.write(output_text)
    if not output_text.endswith("\n"):
        sys.stdout.write("\n")


def emit_json(assistant_events: list[dict]) -> None:
    """Print raw JSON events as NDJSON, one per line."""
    for event in assistant_events:
        sys.stdout.write(json.dumps(event, separators=(",", ":")))
        sys.stdout.write("\n")


def main() -> int:
    args = parse_args()
    transcript_path = resolve_transcript_path(args)

    events = list(parse_events(transcript_path))
    relevant_events = find_events_since_last_user_prompt(events)

    if args.json:
        assistant_events = [
            event for event in relevant_events if event.get("type") == "assistant"
        ]
        emit_json(assistant_events)
    else:
        emit_text(
            relevant_events,
            args.include_tool_calls,
            args.tool_results,
            args.separator,
            args.max_chars,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
