#!/usr/bin/env python3
"""cc-lens Stop hook: maintain a rolling progress note per session.

Hook mode (default): reads the Stop event JSON on stdin, then re-spawns itself
detached (--work) and exits immediately — the turn is never delayed.

Worker mode (--work <state.json>): reads the transcript delta since the last
run, asks a cheap model to fold it into the running note, and stores it at
$CC_LENS_HOME/notes/<session_id>.json. Summarizer resolution: config override
-> claude -p (haiku) -> codex exec -> skip (handoff falls back to raw excerpts).

The note prompt forbids inference: the model may only restate what is in the
log. Never blocks, always exits 0.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.expanduser(os.environ.get("CC_LENS_HOME", "~/.claude/cc-lens"))
NOTES = os.path.join(BASE, "notes")
GUARD_ENV = "CC_LENS_SUMMARIZING"
MIN_DELTA_CHARS = 1500   # don't burn a model call on tiny turns
MAX_DELTA_CHARS = 24000  # cap what we feed the summarizer
NOTE_MAX_CHARS = 1200

PROMPT = """You maintain a factual progress note for a coding-agent session.

CURRENT NOTE (may be empty):
{note}

NEW CONVERSATION LOG (verbatim excerpts, oldest first):
{delta}

Rewrite the note folding in the new log. Hard rules:
- Only restate facts present in the note or the log. NEVER infer, guess or embellish; omit anything uncertain.
- Keep: the goal, what is DONE, key decisions (chosen X over Y because...), and what is PENDING/blocked.
- Drop pleasantries and superseded items. At most 120 words.
- Output ONLY the note text, no preamble, same language as the conversation."""


def load_config():
    try:
        with open(os.path.join(BASE, "config.json")) as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------- transcript

def extract_turn_texts(line):
    """Yield 'role: text' strings from one transcript line (claude or codex format)."""
    try:
        obj = json.loads(line)
    except Exception:
        return
    t = obj.get("type")
    if t in ("user", "assistant"):                     # claude code jsonl
        if obj.get("isSidechain") or obj.get("isMeta"):
            return
        content = (obj.get("message") or {}).get("content")
        texts = []
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [p.get("text", "") for p in content
                     if isinstance(p, dict) and p.get("type") == "text"]
        text = " ".join(" ".join(texts).split())
        if text and not text.startswith("<"):
            yield f"{t}: {text[:1500]}"
    elif t == "response_item":                          # codex rollout jsonl
        p = obj.get("payload") or {}
        if p.get("type") != "message" or p.get("role") not in ("user", "assistant"):
            return
        texts = [c.get("text", "") for c in p.get("content") or []
                 if isinstance(c, dict) and c.get("type") in ("input_text", "output_text")]
        text = " ".join(" ".join(texts).split())
        if text and not text.startswith("<"):
            yield f"{p['role']}: {text[:1500]}"


def read_delta(transcript, offset):
    try:
        size = os.path.getsize(transcript)
        if size <= offset:
            return "", offset
        with open(transcript, "rb") as f:
            f.seek(offset)
            chunk = f.read()
    except OSError:
        return "", offset
    new_offset = offset + len(chunk)
    lines = chunk.split(b"\n")
    parts = []
    for raw in lines:
        for s in extract_turn_texts(raw) or []:
            parts.append(s)
    delta = "\n".join(parts)
    if len(delta) > MAX_DELTA_CHARS:  # keep head+tail, the middle is least useful
        delta = delta[:MAX_DELTA_CHARS // 2] + "\n[...trimmed...]\n" + delta[-MAX_DELTA_CHARS // 2:]
    return delta, new_offset


# ---------------------------------------------------------------- summarizer

def clean_env():
    env = dict(os.environ)
    env[GUARD_ENV] = "1"
    for k in list(env):
        if k.startswith(("CLAUDE", "CODEX")):  # don't look like a nested agent
            env.pop(k, None)
    return env


def run_summarizer(prompt, cfg):
    scratch = os.path.join(BASE, "scratch")
    os.makedirs(scratch, exist_ok=True)
    candidates = []
    if cfg.get("summarizer_cmd"):                 # explicit override, e.g. for tests
        candidates.append(list(cfg["summarizer_cmd"]))
    else:
        pref = cfg.get("summarizer", "auto")
        if pref == "off":
            return None
        if pref in ("auto", "claude"):
            candidates.append(["claude", "-p", "--model", "claude-haiku-4-5-20251001"])
        if pref in ("auto", "codex"):
            candidates.append(["codex", "exec", "--skip-git-repo-check", "-s", "read-only"])
    for cmd in candidates:
        try:
            r = subprocess.run(cmd + [prompt], capture_output=True, text=True,
                               timeout=120, cwd=scratch, env=clean_env(),
                               stdin=subprocess.DEVNULL)
            out = (r.stdout or "").strip()
            if r.returncode == 0 and out:
                return out[:NOTE_MAX_CHARS]
        except Exception:
            continue
    return None


# ---------------------------------------------------------------- modes

def work(state_path):
    with open(state_path) as f:
        evt = json.load(f)
    try:
        os.unlink(state_path)
    except OSError:
        pass
    sid = evt.get("session_id")
    transcript = evt.get("transcript_path")
    if not sid or not transcript or not os.path.isfile(transcript):
        return
    os.makedirs(NOTES, exist_ok=True)
    note_path = os.path.join(NOTES, f"{sid}.json")
    lock = note_path + ".lock"
    try:  # one worker per session at a time
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        if time.time() - os.path.getmtime(lock) < 300:
            return
        # stale lock from a killed worker: take over
    try:
        state = {}
        if os.path.exists(note_path):
            try:
                with open(note_path) as f:
                    state = json.load(f)
            except Exception:
                state = {}
        delta, new_offset = read_delta(transcript, state.get("offset", 0))
        if len(delta) < MIN_DELTA_CHARS and state.get("note"):
            return  # not enough new material to be worth a call
        if not delta:
            return
        cfg = load_config()
        note = run_summarizer(
            PROMPT.format(note=state.get("note") or "(empty)", delta=delta), cfg)
        if not note:
            return  # no summarizer available; handoff will fall back to excerpts
        tmp = note_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"note": note, "offset": new_offset, "cwd": evt.get("cwd", ""),
                       "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
        os.replace(tmp, note_path)
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


def hook():
    if os.environ.get(GUARD_ENV):  # we ARE the summarizer's session: never recurse
        return
    try:
        evt = json.load(sys.stdin)
    except Exception:
        return
    if not evt.get("session_id") or not evt.get("transcript_path"):
        return
    os.makedirs(NOTES, exist_ok=True)
    state_path = os.path.join(NOTES, f".evt-{evt['session_id']}-{os.getpid()}.json")
    with open(state_path, "w") as f:
        json.dump(evt, f)
    # detach: the hook returns instantly, the note updates in the background
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--work", state_path],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 2 and sys.argv[1] == "--work":
            work(sys.argv[2])
        else:
            hook()
    except Exception:
        pass
    sys.exit(0)
