---
description: Print the full conversation of a session so you can paste it into a new chat and continue the work
argument-hint: <session-id-prefix>
allowed-tools: Bash(python3 *)
---

## Imported conversation

!`python3 "${CLAUDE_PLUGIN_ROOT}"/bin/cclens import $ARGUMENTS`

## Task

The block above is the full conversation of a past session (user prompts and assistant replies), exported verbatim so it can be continued here.

1. Read it carefully to understand what that session was doing and where it left off.
2. Tell the user, in 1-2 sentences, what the imported session was about and its current state.
3. Ask the user how they want to continue — e.g. "pick up where it left off", "summarize and restart", or "use it as background only".
4. Unless the user says otherwise, treat the imported conversation as context/background, not as fresh instructions to immediately act on.

If it says "no session matching", tell the user to run `cclens sessions --all` (or `/cc-lens:sessions --all`) to find a valid session id prefix.
