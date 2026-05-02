# source-of-truth-agent-tool

A small Python system that prevents AI coding agents from drifting, paraphrasing, or inventing requirements over long projects.

The core idea: store every raw input submission verbatim, then build a separate **requirements tree** that contains *only references* to those raw quotes — never agent-paraphrased text. A second AI agent reviews every proposed change to that tree, so the only path for hallucination to enter requirements is via deliberately misleading quote selection — which the reviewer catches.

The system is cross-AI-CLI capable via a thin adapter (Claude Code first; other CLIs later).

## Storage layout

```
~/.source-of-truth/
    global-settings.json
    projects/
        <project_id>/                                     # project_id = session_id of initializing session
            project-<project_id>-source-of-truth.json     # the requirements tree (sole writer = our app)
            project-settings.json                         # OPTIONAL — overrides/extends global; lists member sessions
            raw_input_log.json                            # rolling, session-grouped
            reviewer_thinking.log                         # tail this to watch the reviewer in real time
```

## Status

Initial implementation. 27 unit tests passing. Local capture half exercised end-to-end; live reviewer subprocess integration is the next concrete work.

## License

MIT
