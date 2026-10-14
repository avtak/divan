#!/usr/bin/env python3
"""guard.py: a pre-tool hook that refuses the commands AGENTS.md says never to run.

One script for three runtimes:
  Claude Code  PreToolUse    (.claude/settings.json, exec form)
  Hermes       pre_tool_call (hooks: block in ~/.hermes/config.yaml, fail_closed: true)
    both pipe {"tool_input": {"command": "..."}} on stdin. Exit code 2 blocks the call, and the
    first lines of stderr become the reason the agent sees. Anything else: exit 0, print nothing.
  Antigravity  PreToolUse    (.agents/hooks.json, matcher run_command)
    pipes {"toolCall": {"name": "run_command", "args": {"CommandLine": "..."}}} and reads a JSON
    decision from stdout: {"decision": "deny", "reason": "..."} blocks, {"decision": "ask"}
    hands the command to Antigravity's normal permission flow. A missing decision is treated
    as deny ({} blocked `git status` in a test), so every path prints one. "allow" is never
    printed: it would skip Antigravity's own approval prompts. Detected by the payload shape,
    no flag needed. Hooks run with cwd = .agents/, hence ../ in hooks.json.

The prose rule is in AGENTS.md (Hard rules, "The owner runs the dangerous commands"). This is
the part that holds when the prose is not read.
"""
import json
import re
import sys
from pathlib import Path


def _trace(line: str) -> None:
    """Antigravity only: one line per firing into .agents/hooks.log (gitignored)."""
    try:
        import datetime
        root = Path(__file__).resolve().parent.parent.parent
        log_file = root / ".agents" / "hooks.log"
        if log_file.exists() and log_file.stat().st_size > 500_000:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            log_file.write_text("\n".join(lines[-1000:]) + "\n", encoding="utf-8")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")
    except Exception:
        pass

BLOCK = [
    (r"\bgit\s+reset\s+(-\S*\s+)*--hard\b",
     "git reset --hard is blocked: it destroys unpushed edits. A stopped rebase has lost nothing yet; read what it is asking, or hand the command to the owner."),
    (r"\bgit\s+push\b[^\n|;&]*\s(--force|-f|--force-with-lease)\b",
     "force-push is blocked: other clones pull from this branch. Hand the command to the owner."),
    (r"\bgit\s+filter-repo\b",
     "git filter-repo rewrites history; the owner runs it (AGENTS.md, secrets in history)."),
    (r"\bgit\s+clean\s+(-\S*\s+)*-\S*[fx]",
     "git clean -f/-x deletes untracked work. Blocked; hand it to the owner."),
    (r"\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)",
     "git checkout/restore . discards every uncommitted edit. Blocked; name the file instead."),
    (r"\brm\s+(?=(?:-\S*\s+)*-\S*[rR])(?=(?:-\S*\s+)*-\S*[fF])",
     "rm -rf is blocked everywhere except a temp directory (/tmp, $TMP, the scratchpad). Delete named files, or hand it to the owner."),
    (r"\b(shred|userdel|groupdel|mkfs(\.\w+)?)\b|\bdd\s+if=",
     "destructive system command blocked (AGENTS.md hard rules). Hand it to the owner."),
    (r"\bssh\b[^\n|;&]*\b(userdel|groupdel|usermod|sshd|iptables|ufw|rm\s+-[rf]|mkfs|dd\s+if=)\b",
     "changing remote server users, the firewall, or running destructive commands over SSH is blocked (AGENTS.md hard rules). Hand it to the owner."),
]
TEMP_OK = re.compile(r"\brm\s+(-\S+\s+)+(/tmp/|\$TMP|\$TEMP|\$\{?TMPDIR|/sessions/[^ ]*/scratchpad|\S*scratchpad\S*)", re.I)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                                   # not a tool payload: nothing to judge
    antigravity = isinstance(payload.get("toolCall"), dict)
    if antigravity:
        cmd = (payload["toolCall"].get("args") or {}).get("CommandLine") or ""
        _trace(f"guard: run_command {cmd[:80]!r}")
    else:
        cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        if antigravity:
            print(json.dumps({"decision": "ask"}))
        return 0
    for pat, reason in BLOCK:
        if re.search(pat, cmd):
            if pat.startswith(r"\brm") and TEMP_OK.search(cmd):
                continue
            msg = f"blocked by scripts/hooks/guard.py: {reason}"
            if antigravity:
                print(json.dumps({"decision": "deny", "reason": msg}))
                return 0
            sys.stderr.write(msg + "\n")
            return 2
    if antigravity:
        print(json.dumps({"decision": "ask"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
