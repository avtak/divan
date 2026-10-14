#!/usr/bin/env python3
"""sanitise.py: find personal data before it is published. Run it before every public commit.

Two kinds of rule:
  personal terms  your names, handles, places, server names. One term per line in a file that
                  lives OUTSIDE the repo, so the list itself is never published:
                  $DIVAN_SANITISE_TERMS, else ~/.config/divan/sanitise-terms.txt.
                  A line is a case-insensitive word; "re:" starts a regex; "allow:" names an
                  exact string that may appear (for example your public repo URL); "#" is a comment.
  generic rules   e-mail addresses, phone numbers, IPv4 addresses, home paths, tailnet host
                  names, SSH aliases and ports. They need no list.

It scans every file in the working tree (not .git, not private/) and, if commits exist, every
author and committer identity and every commit message. A hit prints file:line and the rule.

Usage:  python3 scripts/sanitise.py [PATH]      (default: the repo this script is in)
Exit 0 clean, 1 on any hit, 2 when the terms file is missing (generic rules still run).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "private", "__pycache__", "node_modules"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".zip"}
# Built from pieces so this file does not match its own rules.
AT = "@"
GENERIC = [
    ("e-mail", re.compile(r"[A-Za-z0-9._%+-]+" + AT + r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<![\w.])\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,}[\s-]?\d{2,}")),
    ("IPv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("home path", re.compile(r"/(?:home|Users)/(?!user\b|you\b|me\b|<)[A-Za-z0-9._-]+|[A-Z]:\\Users\\[A-Za-z0-9._-]+")),
    ("tailnet name", re.compile(r"[a-z0-9-]+\.ts" + r"\.net\b", re.I)),
    ("SSH alias", re.compile(r"\bssh\s+(?:-\w+\s+)*(?!-)(?!user\b|host\b|server\b|you\b)[A-Za-z][\w.-]*(?=[\s'\"]|$)")),
    ("SSH config Host", re.compile(r"^\s*Host\s+(?!\*)[A-Za-z][\w.-]*\s*$", re.M)),
    ("port", re.compile(r"\b(?:ssh\s+-p|Port)\s+\d{2,5}\b")),
]
# Not personal: placeholders, loopback, documentation domains, GitHub's no-reply addresses,
# version numbers that look like IPs.
ALLOW_GENERIC = re.compile(
    r"127\.0\.0\.1|0\.0\.0\.0|"
    r"(?:example\.(?:com|org|net)|users\.noreply\.github\.com|noreply" + AT + r"anthropic\.com)\b|"
    r"\bgit" + AT + r"github\.com\b", re.I)


def load_terms() -> tuple[list[tuple[str, re.Pattern]], list[str], Path | None]:
    path = Path(os.environ.get("DIVAN_SANITISE_TERMS", Path.home() / ".config/divan/sanitise-terms.txt"))
    if not path.is_file():
        return [], [], None
    terms, allow = [], []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("allow:"):
            allow.append(line[6:].strip())
        elif line.startswith("re:"):
            terms.append((line, re.compile(line[3:], re.I)))
        else:
            terms.append((line, re.compile(r"(?<![A-Za-z0-9])" + re.escape(line) + r"(?![A-Za-z0-9])", re.I)))
    return terms, allow, path


def scan_text(label: str, text: str, terms, allow, generic: bool) -> list[str]:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        clean = line
        for a in allow:
            clean = clean.replace(a, "")
        for name, pat in terms:
            if pat.search(clean):
                hits.append(f"{label}:{i}: personal term '{name}'")
        if not generic:
            continue
        for name, pat in GENERIC:
            for m in pat.finditer(clean):
                if ALLOW_GENERIC.search(m.group(0)):
                    continue
                if name == "IPv4" and not all(int(x) <= 255 for x in m.group(0).split(".")):
                    continue
                hits.append(f"{label}:{i}: {name} '{m.group(0)}'")
    return hits


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent.parent
    terms, allow, terms_path = load_terms()
    hits: list[str] = []
    files = 0
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not (Path(d) / x).is_symlink()]
        for n in names:
            p = Path(d) / n
            if p.suffix.lower() in SKIP_SUFFIX or p.is_symlink():
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                hits.append(f"{p.relative_to(root)}: binary or unreadable file; check it by hand")
                continue
            files += 1
            r = p.relative_to(root).as_posix()
            hits += scan_text(r, r + "\n" + text, terms, allow, generic=(r != "scripts/sanitise.py"))
    log = subprocess.run(["git", "log", "--all", "--format=%an <%ae> | %cn <%ce>%n%B"], cwd=root,
                         capture_output=True, text=True)
    if log.returncode == 0 and log.stdout.strip():
        hits += scan_text("git log", log.stdout, terms, allow, generic=True)
    for h in hits:
        print("  HIT", h)
    if terms_path is None:
        print("sanitise: no personal terms file; only the generic rules ran. "
              "Write ~/.config/divan/sanitise-terms.txt (see the docstring).")
    print(f"sanitise: {len(hits)} hit(s) in {files} text files"
          + (f", {len(terms)} personal terms from {terms_path}" if terms_path else ""))
    if hits:
        return 1
    return 2 if terms_path is None else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
