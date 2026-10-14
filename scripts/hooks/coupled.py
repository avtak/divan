#!/usr/bin/env python3
"""coupled.py: tell the agent which docs describe a file the moment it edits that file.

Claude Code PostToolUse hook (Edit|Write). Reads the COUPLED map in scripts/lint.py, the one
list of "if X changes, check Y", and prints {"hookSpecificOutput": {"additionalContext": ...}},
which Claude Code shows the model as a reminder. Once per session per file.

Why: lint check 14 sees the same map, but only at commit time, as a warning, after the work
is done. Docs that describe a changed file go stale even when every check passes.
"""
import json
import re
import sys
import tempfile
from pathlib import Path


def repo_root(path: Path) -> Path | None:
    for p in path.parents:
        if (p / ".git").exists() and (p / "scripts" / "lint.py").is_file():
            return p
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    file_path = (data.get("tool_input") or {}).get("file_path")
    if not file_path:
        return 0
    path = Path(file_path).resolve()
    root = repo_root(path)
    if root is None:
        return 0
    rel = path.relative_to(root).as_posix()
    sys.path.insert(0, str(root / "scripts"))
    try:
        from lint import COUPLED
    except Exception:
        return 0
    lines = []
    for pat, docs, what in COUPLED:
        if re.search(pat, rel):
            others = [d for d in docs if d != rel]
            if others:
                lines.append(f"{rel} is part of {what}. Check that {', '.join(others)} still "
                             "describe it, and update them in this same change.")
    if not lines:
        return 0
    seen_file = Path(tempfile.gettempdir()) / f"divan-coupled-{data.get('session_id', 'none')}.json"
    try:
        seen = set(json.loads(seen_file.read_text()))
    except Exception:
        seen = set()
    if rel in seen:
        return 0
    seen.add(rel)
    try:
        seen_file.write_text(json.dumps(sorted(seen)))
    except Exception:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": "divan coupled files: " + " ".join(lines)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
