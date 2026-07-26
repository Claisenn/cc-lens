#!/usr/bin/env python3
"""cc-lens PreToolUse hook: snapshot a file's original content before the agent
first modifies it in a session. Baselines live under ~/.claude/cc-lens/baselines/<session_id>/.

Works for both Claude Code (Edit/Write: tool_input.file_path) and Codex
(apply_patch: file paths parsed from the patch text in tool_input.command).

Always exits 0 — this hook observes, it never blocks the edit.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time

BASE = os.path.expanduser(os.environ.get("CC_LENS_HOME", "~/.claude/cc-lens"))

PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)


def target_files(data):
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    if fp:
        return [fp]
    cmd = ti.get("command")
    if isinstance(cmd, list):
        cmd = " ".join(str(c) for c in cmd)
    if isinstance(cmd, str) and "*** Begin Patch" in cmd:
        return PATCH_FILE_RE.findall(cmd)
    return []


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    session_id = data.get("session_id") or "unknown"
    cwd = data.get("cwd") or os.getcwd()
    for file_path in target_files(data):
        if not os.path.isabs(file_path):
            file_path = os.path.join(cwd, file_path)
        snapshot_one(data, session_id, os.path.abspath(file_path))


def snapshot_one(data, session_id, file_path):

    sdir = os.path.join(BASE, "baselines", session_id)
    os.makedirs(sdir, exist_ok=True)

    index_path = os.path.join(sdir, "index.json")
    index = {}
    if os.path.exists(index_path):
        try:
            with open(index_path) as f:
                index = json.load(f)
        except Exception:
            index = {}

    meta = index.get("_meta") or {}
    meta.setdefault("cwd", data.get("cwd", ""))
    meta.setdefault("started", time.strftime("%Y-%m-%d %H:%M:%S"))
    index["_meta"] = meta

    files = index.setdefault("files", {})
    if file_path not in files:
        key = hashlib.sha1(file_path.encode()).hexdigest()[:16]
        if os.path.isfile(file_path):
            try:
                shutil.copy2(file_path, os.path.join(sdir, key))
                files[file_path] = key
            except Exception:
                return
        else:
            files[file_path] = None  # file did not exist yet: created by Claude
        tmp = index_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(index, f, indent=1)
        os.replace(tmp, index_path)


if __name__ == "__main__":
    main()
    sys.exit(0)
