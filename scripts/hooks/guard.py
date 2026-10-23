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
import shlex
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


# Each BLOCK pattern is matched against one simple command at a time, rebuilt from shell words,
# with "^" in front: a quoted mention ("echo 'git reset --hard'", a commit message, a grep) is
# not a command, and git's global flags (git -C <dir> reset --hard) are dropped first. Both were
# holes in the harness study (paper Section 5.1). If the shell text cannot
# be parsed, the whole string is matched as before, so an odd command fails closed.
WRAPPERS = {"sudo", "doas", "env", "nohup", "time", "command", "exec", "builtin", "nice", "ionice",
            "timeout", "xargs", "stdbuf", "systemd-run", "watch", "then", "do", "else", "!", "{", "("}
WRAPPER_ARG = {"-n", "-u", "-g", "-p", "-c", "-I", "-L", "-s", "-k", "--signal", "--property"}
GIT_GLOBAL_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
SHELLS = {"bash", "sh", "zsh", "dash"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&", ";;"}
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\s*\2\s*(\n|$)", re.S)


def _strip_heredocs(cmd: str) -> str:
    """A heredoc body is data fed to a program, not commands; keep only its first line."""
    return HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0] + "\n", cmd)


def _words(cmd: str) -> list[str]:
    lex = shlex.shlex(cmd.replace("\\\n", " ").replace("\n", " ; "), posix=True, punctuation_chars=";&|")
    lex.whitespace_split = True
    return list(lex)


def _commands(cmd: str, depth: int = 0) -> list[str]:
    """Every simple command in cmd as a word string, wrappers and git globals removed.
    Raises ValueError when the shell text cannot be parsed."""
    out, cur = [], []
    cmd = _strip_heredocs(cmd)
    words = _words(cmd)
    for w in words + [";"]:
        if w in SEPARATORS or set(w) <= set(";&|"):
            if cur:
                out += _simple(cur, depth)
            cur = []
        else:
            cur.append(w)
    for sub in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", cmd):     # command substitution
        if depth < 3:
            out += _commands(sub[0] or sub[1], depth + 1)
    return out


def _simple(ws: list[str], depth: int) -> list[str]:
    ws = list(ws)
    while ws:
        w = ws[0]
        if re.match(r"^[A-Za-z_]\w*=", w) or w in WRAPPERS or re.fullmatch(r"\d+[smhd]?", w):
            ws.pop(0)
            while ws and ws[0].startswith("-"):
                flag = ws.pop(0)
                if flag in WRAPPER_ARG and ws:
                    ws.pop(0)
            continue
        break
    if not ws:
        return []
    name = ws[0].rsplit("/", 1)[-1]
    if name in SHELLS and "-c" in ws[1:] and depth < 3:
        i = ws.index("-c", 1)
        return _commands(ws[i + 1], depth + 1) if i + 1 < len(ws) else []
    if name == "find":
        for i, w in enumerate(ws):
            if w in ("-exec", "-execdir", "-ok", "-okdir"):
                rest = ws[i + 1:]
                end = next((j for j, x in enumerate(rest) if x in (";", "+", "\\;")), len(rest))
                return [" ".join(ws)] + _simple(rest[:end], depth)
    if name == "git":
        rest = ws[1:]
        while rest and rest[0].startswith("-"):
            flag = rest.pop(0)
            if flag in GIT_GLOBAL_ARG and rest:
                rest.pop(0)
        ws = ["git"] + rest
    else:
        ws = [name] + ws[1:]
    return [" ".join(ws)]


def blocked(cmd: str) -> str | None:
    """The reason cmd is blocked, or None."""
    try:
        units, anchor = _commands(cmd), "^"
    except ValueError:
        units, anchor = [cmd], ""                  # unparseable: match the raw text, fail closed
    for unit in units:
        for pat, reason in BLOCK:
            if re.search(f"{anchor}(?:{pat})", unit):
                if pat.startswith(r"\brm") and TEMP_OK.search(unit):
                    continue
                return reason
    return None


# (command, should block). `--probe` runs these; add a case with every change to BLOCK.
_G, _R, _H, _P, _F = "git", "reset", "--hard", "push", "--force"
PROBE = [
    (f"{_G} {_R} {_H}", True),
    (f"{_G} -C /x {_R} {_H}", True),
    (f"{_G} -c a=b {_P} {_F}", True),
    (f"{_G} --git-dir=.git {_R} {_H} HEAD~1", True),
    (f"cd x && {_G} {_R} {_H}", True),
    (f"sudo {_G} {_R} {_H}", True),
    (f"bash -c '{_G} {_R} {_H}'", True),
    (f"echo $({_G} {_R} {_H})", True),
    (f"{_G} {_P} origin main {_F}", True),
    (f"{_G} {_P} -f", True),
    (f"{_G} clean -fdx", True),
    (f"{_G} checkout -- .", True),
    (f"{_G} filter-repo --path x", True),
    ("rm -rf build", True),
    ("rm -fr build", True),
    ("find . -name x -exec rm -rf {} ;", True),
    ("xargs rm -rf < list", True),
    ("rm -rf /tmp/x", False),
    ("rm -rf /tmp/x && rm -rf build", True),
    ('ssh "$HOST" "sudo userdel bob"', True),
    ("dd if=/dev/zero of=/dev/sda", True),
    ("rm -rf 'unclosed", True),                    # unparseable: raw match, fail closed
    (f"echo '{_G} {_R} {_H} is blocked'", False),
    (f"{_G} commit -m 'guard: block {_G} {_R} {_H}'", False),
    (f"grep -n 'rm -rf' scripts/hooks/guard.py", False),
    (f"python3 - <<'EOF'\nprint('{_G} {_R} {_H}')\nEOF", False),
    (f"python3 - <<'EOF'\ns = 'see `{_G} -C x {_R} {_H}` in the docs'\nEOF", False),
    (f"{_G} {_P} origin main", False),
    (f"{_G} {_R} --soft HEAD~1", False),
    (f"{_G} -C /x status", False),
    ("rm notes.txt", False),
]


def probe() -> int:
    bad = [(c, want) for c, want in PROBE if (blocked(c) is not None) != want]
    for c, want in bad:
        print(f"probe guard: FAILED ({'should block' if want else 'should allow'}): {c!r}")
    print("probe guard:", "ok" if not bad else f"{len(bad)} of {len(PROBE)} failed")
    return 1 if bad else 0


def main() -> int:
    if "--probe" in sys.argv[1:]:
        return probe()
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
    reason = blocked(cmd)
    if reason:
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
