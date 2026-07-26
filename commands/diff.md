---
description: Show colored diff between original code (before this session's edits) and current code
argument-hint: [session-id-prefix | --list | --all-sessions]
allowed-tools: Bash(python3 *)
---

## Snapshot diff

!`python3 "${CLAUDE_PLUGIN_ROOT}"/bin/cclens diff $ARGUMENTS`

## Task

Present the diff output above to the user inside a ```diff code block, verbatim and complete.
If it says "no snapshots yet", explain that cc-lens starts recording baselines the moment Claude edits a file (via its PreToolUse hook), so diffs will appear after the first edit in a session.
Add at the end: the same view is available directly in any terminal via `cclens diff` (add `<plugin>/bin` to PATH or call it with its full path).
