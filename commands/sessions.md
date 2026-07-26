---
description: List Claude Code sessions and each one's context window usage
argument-hint: [--all] [--limit N]
allowed-tools: Bash(python3 *)
---

## Session overview

!`python3 "${CLAUDE_PLUGIN_ROOT}"/bin/cclens sessions $ARGUMENTS`

## Task

Present the session listing above to the user inside a code block, verbatim and complete (bars and percentages included).
Briefly note: percentage = current context footprint (input + cache read + cache creation + output tokens of the latest turn) against that session's model context window (200k, or 1M for 1M-context models). `--all` covers every project, default is the current project only.
Add at the end: the same view is available directly in any terminal via `cclens sessions`.
