#!/usr/bin/env python3
"""Claude Code UserPromptSubmit and Antigravity PreInvocation hook: say when a session has grown big.

Claude Code: reads the real context size from the last assistant message's token usage in the session
transcript (input + cache read + cache write = what the last request carried).
Antigravity (--antigravity): checks the transcriptPath byte size (or invocationNum >= 25) and injects an
ephemeralMessage once per band.
When the size crosses a band, it adds one note to the model's context, once per band, so it reminds
without nagging. The agent then offers the handover in skills/working-terms/SKILL.md §6.
Never blocks, never fails a prompt: any error prints nothing (or {} in Antigravity).
"""
import json
import os
import sys

# A warm cache read is cheap, so a large active session is cheap. The expensive case is the first
# message after the cache has lapsed: the whole context is written again. Tune FIRST to your model's
# window. With automatic compaction off, this warning is the only signal, and the owner decides.
FIRST = int(os.environ.get("DIVAN_HANDOVER_FIRST", 700_000))   # first warning (Claude tokens)
STEP = 100_000    # then one more per 100k
AGY_FIRST_BYTES = 600_000  # ~150k tokens of transcript JSONL in Antigravity
AGY_STEP_BYTES = 400_000
TAIL = 2_000_000  # bytes read from the end of the transcript; the last usage is always near it


def last_context_tokens(path):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL))
        lines = f.read().decode("utf-8", "ignore").splitlines()
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        u = (o.get("message") or {}).get("usage") or {}
        n = sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if n:
            return n
    return 0


def main(argv: list[str]) -> int:
    antigravity = "--antigravity" in argv
    try:
        data = json.load(sys.stdin)
        if antigravity:
            if data.get("invocationNum", 0) != 0:
                print("{}")
                return 0
            path = data.get("transcriptPath") or ""
            full_path = path.replace("transcript.jsonl", "transcript_full.jsonl") if path else ""
            check_path = full_path if (full_path and os.path.exists(full_path)) else path
            size = os.path.getsize(check_path) if (check_path and os.path.exists(check_path)) else 0
            steps = data.get("initialNumSteps") or 0
            effective = max(size, steps * 12_000)
            if effective < AGY_FIRST_BYTES:
                print("{}")
                return 0
            band = (effective - AGY_FIRST_BYTES) // AGY_STEP_BYTES
            approx_k = max(size // 4000, steps * 3)
        else:
            path = data.get("transcript_path") or ""
            n = last_context_tokens(path) if path else 0
            if n < FIRST:
                return 0
            band = (n - FIRST) // STEP
            approx_k = n // 1000
        state = path + ".handover-band"
        try:
            with open(state) as f:
                if int(f.read().strip() or -1) >= band:
                    if antigravity:
                        print("{}")
                    return 0
        except (OSError, ValueError):
            pass
        with open(state, "w") as f:
            f.write(str(band))
        if antigravity:
            msg = (f"[HANDOVER REQUIRED: session context ~{approx_k}k tokens]: Every message re-sends all of it. "
                   "Offer the owner the handover in this reply (skills/working-terms/SKILL.md §6): "
                   "update the log, commit and push, and output a 2-3 line paste-ready prompt for a fresh session.")
            print(json.dumps({"injectSteps": [{"ephemeralMessage": msg}]}))
        else:
            msg = (f"This session's context is about {approx_k}k tokens. Tell the owner once, in one line, at the "
                   "end of this reply. The owner decides whether to run /compact, continue, or start fresh. "
                   "Do not suggest ending the session yourself.")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}))
    except Exception:
        if antigravity:
            print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
