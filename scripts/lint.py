#!/usr/bin/env python3
"""lint.py: the checks that stop a correct edit from going stale in another file.

Why this exists: in a repo that agents edit, nearly every fault is a copy of a fact that lives
somewhere else and was never updated, and the repo usually already knew. This turns "the repo
knew" into "the commit is refused until someone acts". It runs from scripts/hooks/pre-commit
on every clone. Stdlib only.

Checks (F = failure blocks the commit, W = warning only):
  1 F  a DEADLINES.md date restated in a file that is not a log, diary or archive. Rows dated
       today or earlier are skipped (history); `--probe` runs a self-check of this. A line
       carrying `<!-- lint:other-subject -->` is a confirmed coincidence and is skipped
  2 F  a backticked repo path that does not exist (dead pointer)
  3 W  a "not yet / still open / TODO" line in a file untouched for 30+ days
  4 F  a Hermes prompt-injection pattern in a context file or a SKILL.md
       (Hermes blocks the WHOLE file on a hit; list copied from
        NousResearch/hermes-agent tools/threat_patterns.py; MIT notice: THIRD_PARTY_NOTICES.md)
  5 F  any AGENTS.md (root or nested) over 20,000 chars or 200 lines (W over 15,000). 20,000 is
       Hermes' truncation floor, the tightest limit found. 15,000 is cost: every session loads it
  6 F  any CLAUDE.md or CLAUDE.local.md on disk, tracked or not. Once a CLAUDE.md exists,
       Claude Code stops reading AGENTS.md, nested ones included
  7 F  a symlink in a tool's home config (~/.claude, ~/.gemini) that resolves into this repo.
       Project links (.claude/skills, .agents/skills) are the supported way
  8 F  a staged line that looks like a secret, or a staged .env file. Same pattern as
       scripts/divan-sync, so a hand commit gets the net the auto-sync has
  9 F  a skill on disk missing from the docs that list them (SKILL_DOCS), or a wrong skill count
       in skills/context-layers.svg
 10 F  a count of skills in a live file ("seven skills", "the other 6 skills") that does not
       match skills/ on disk; only counts of 5 or more are read
 11 F  a file in scripts/ or scripts/hooks/ that README.md never names
 12 W  a status 'as of / Stand / status on DD.MM.YYYY' older than 14 days in a live file
       ('checked' or 'verified' dates are evidence for a fact, not a status, and are not read)
 13 F  a retired name in a live file (RETIRED below), so a replaced name or path cannot come back
 14 W  a changed file whose docs did not change in the same work (COUPLED below): staged,
       unstaged, untracked and unpushed files all count. Printed even with --quiet.
       scripts/hooks/coupled.py reads the same map at edit time
 15 W  a new log entry (an added "- **" line in a *_log.md) over 800 characters. The format is a
       headline and at most three sentences; the detail goes in the commit message (skill record)

Usage:  python3 scripts/lint.py [--quiet] [--probe]
Exit 0 clean (warnings allowed), 1 on any failure.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

# ----------------------------------------------------------------------------- config
# Everything repo-specific is here. Rename a folder, change it here.

RECORD_DIRS = ("diary/", "logs/archive/", "private/", ".git/")   # dated records: never linted for staleness
RECORD_FILES: tuple[str, ...] = ()                 # single dated records, never edited for a lint
LOG_SUFFIX = "_log.md"
CONTEXT_FILES = ("AGENTS.md",)                     # basename match, any depth
SKILL_GLOB = "skills/*/SKILL.md"
SKILL_DOCS = ("AGENTS.md", "README.md", "skills/README.md")   # each must name every skill
BANNED_NAMES = ("CLAUDE.md", "CLAUDE.local.md")     # anywhere on disk, .claude/ included
WALK_SKIP = (".git", ".claude/worktrees")            # other checkouts carry their own
AGENTS_WARN, AGENTS_FAIL, AGENTS_LINES = 15_000, 20_000, 200
STALE_DAYS = 30
STATUS_DAYS = 14   # check 12: a status "as of" a date goes stale faster than a TODO line
STALE_WORDS = re.compile(r"\b(not yet|still open|still to do|TODO|NEXT:)\b", re.I)
PATH_EXT = r"(?:md|py|sh|json|csv|svg|tex|yaml|yml|html|js|css|txt|png|pdf|service|timer)"
PATH_IN_TICKS = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./ -]*?\." + PATH_EXT + r")`")
ROOT_FILES = {"AGENTS.md", "ABOUT_ME.md", "DEADLINES.md", "README.md", "START_HERE.md"}
# a line that talks about a file in the past tense is history, not a pointer
HISTORY_WORDS = re.compile(r"deleted|used to|no longer|gone|renamed|formerly|until |should be|~~|replaced|removed", re.I)
PLACEHOLDER = re.compile(r"(^|[_/a-z])N([_.]|$)|<|>|\*|YYYY|\.\.\.|\$| ")


def history_near(lines: list[str], ln: int) -> bool:
    """True if the line (1-based) or the two before it read as history, not as a live pointer."""
    return any(HISTORY_WORDS.search(x) for x in lines[max(0, ln - 3):ln])

# ------------------------------------------------------------- Hermes threat patterns
# (regex, id, scope). scope "all" and "context" apply to context files; "strict" adds
# the patterns Hermes runs on skills at scan time. Kept verbatim so a false positive here
# is a true positive there.
_F = r"(?:\w+\s+){0,8}"
_PATTERNS = [
    (rf"ignore\s+{_F}(previous|all|above|prior)\s+{_F}instructions", "prompt_injection", "all"),
    (r"system\s+prompt\s+override", "sys_prompt_override", "all"),
    (rf"disregard\s+{_F}(your|all|any)\s+{_F}(instructions|rules|guidelines)", "disregard_rules", "all"),
    (rf"act\s+as\s+(if|though)\s+{_F}you\s+{_F}(have\s+no|don\'t\s+have)\s+{_F}(restrictions|limits|rules)", "bypass_restrictions", "all"),
    (r"<!--[^>]{0,512}(?:ignore|override|system|secret|hidden)[^>]{0,512}-->", "html_comment_injection", "all"),
    (r"<\s*div\s+style\s*=\s*[\"'][^>]{0,2048}display\s*:\s*none", "hidden_div", "all"),
    (r"translate\s+[^\n]{0,512}\s+into\s+[^\n]{0,512}\s+and\s+(execute|run|eval)", "translate_execute", "all"),
    (rf"do\s+not\s+{_F}tell\s+{_F}the\s+user", "deception_hide", "all"),
    (rf"you\s+are\s+{_F}now\s+(?:a|an|the)\s+", "role_hijack", "context"),
    (rf"pretend\s+{_F}(you\s+are|to\s+be)\s+", "role_pretend", "context"),
    (rf"output\s+{_F}(system|initial)\s+prompt", "leak_system_prompt", "context"),
    (rf"(respond|answer|reply)\s+without\s+{_F}(restrictions|limitations|filters|safety)", "remove_filters", "context"),
    (rf"you\s+have\s+been\s+{_F}(updated|upgraded|patched)\s+to", "fake_update", "context"),
    (r"\bname\s+yourself\s+\w+", "identity_override", "context"),
    (r"register\s+(as\s+)?a?\s*node", "c2_node_registration", "context"),
    (r"(heartbeat|beacon|check[\s\-]?in)\s+(to|with)\s+", "c2_heartbeat", "context"),
    (r"pull\s+(down\s+)?(?:new\s+)?task(?:ing|s)?\b", "c2_task_pull", "context"),
    (r"connect\s+to\s+the\s+network\b", "c2_network_connect", "context"),
    (r"you\s+must\s+(?:\w+\s+){0,3}(register|connect|report|beacon)\b", "forced_action", "context"),
    (r"only\s+use\s+one[\s\-]?liners?\b", "anti_forensic_oneliner", "context"),
    (rf"never\s+{_F}(?:create|write)\s+{_F}(?:script|file)\s+{_F}disk", "anti_forensic_disk", "context"),
    (r"unset\s+\w*(?:CLAUDE|CODEX|HERMES|AGENT|OPENAI|ANTHROPIC)\w*", "env_var_unset_agent", "context"),
    (r"\b(?:cobalt\s*strike|sliver|havoc|mythic|metasploit|brainworm)\b", "known_c2_framework", "context"),
    (r"\bc2\s+(?:server|channel|infrastructure|beacon)\b", "c2_explicit", "context"),
    (r"\bcommand\s+and\s+control\b", "c2_explicit_long", "context"),
    (r"curl\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl", "all"),
    (r"wget\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_wget", "all"),
    (r"cat\s+[^\n]{0,2048}(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)", "read_secrets", "all"),
    (r"(send|post|upload|transmit)\s+[^\n]{0,2048}\s+(to|at)\s+https?://", "send_to_url", "strict"),
    (rf"(include|output|print|share)\s+{_F}(conversation|chat\s+history|previous\s+messages|full\s+context|entire\s+context)", "context_exfil", "strict"),
    (r"authorized_keys", "ssh_backdoor", "strict"),
    (r"\$HOME/\.ssh|\~/\.ssh", "ssh_access", "strict"),
    (r"\$HOME/\.hermes/\.env|\~/\.hermes/\.env", "hermes_env", "strict"),
    (r"(update|modify|edit|write|change|append|add\s+to)\s+[^\n]{0,2048}(?:AGENTS\.md|CLAUDE\.md|\.cursorrules|\.clinerules)", "agent_config_mod", "strict"),
    (r"(update|modify|edit|write|change|append|add\s+to)\s+[^\n]{0,2048}\.hermes/(config\.yaml|SOUL\.md)", "hermes_config_mod", "strict"),
    (r"(?:api[_-]?key|token|secret|password)\s*[=:]\s*[\"'][A-Za-z0-9+/=_-]{20,}", "hardcoded_secret", "strict"),
]
_INVISIBLE = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0x2062, 0x2063, 0x2064, 0xFEFF,
                                0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069)}


def threats(text: str, scope: str) -> list[str]:
    hits = [f"invisible_unicode_U+{ord(c):04X}" for c in set(text) & _INVISIBLE]
    norm = unicodedata.normalize("NFKC", text[:65_536])
    for pat, pid, sc in _PATTERNS:
        if sc == "all" or sc == scope or (scope == "strict" and sc == "context"):
            if re.search(pat, norm, re.I):
                hits.append(pid)
    return hits


# ----------------------------------------------------------------------------- helpers

def repo_root() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, check=True).stdout.strip()
        return Path(out)
    except Exception:
        return Path(__file__).resolve().parent.parent


def tracked_md(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "*.md"], cwd=root,
                             capture_output=True, text=True, check=True).stdout
        return [root / p for p in out.split("\0") if p and (root / p).is_file()]
    except Exception:
        return [p for p in root.rglob("*.md") if ".git" not in p.parts and "private" not in p.parts and p.is_file()]


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def is_record(r: str) -> bool:
    return r.endswith(LOG_SUFFIX) or r in RECORD_FILES or any(r.startswith(d) for d in RECORD_DIRS)


def last_commit_age_days(root: Path, r: str) -> float | None:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", r], cwd=root,
                             capture_output=True, text=True, check=True).stdout.strip()
        return (time.time() - int(out)) / 86400 if out else None
    except Exception:
        return None


# ----------------------------------------------------------------------------- checks

MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def row_end(cell: str) -> tuple[int, int, int] | None:
    """The last day a DEADLINES 'When' cell covers, as (year, month, day): '30.11.2026',
    '2–9 Nov 2026' -> 9 Nov, 'Feb–Mar 2027' -> 31 Mar. None when the cell cannot be read."""
    num = re.findall(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", cell)
    if num:
        d, m, y = num[-1]
        return int(y), int(m), int(d)
    named = re.findall(r"(?:(\d{1,2})\s+)?([A-Za-z]{3})[a-z]*\.?\s+(\d{4})", cell)
    for d, mon, y in reversed(named):
        if mon.lower() in MONTHS:
            m = MONTHS[mon.lower()]
            last = 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30 if m != 2 else 28
            return int(y), m, int(d) if d else last
    return None


def deadline_dates(root: Path, today: tuple[int, int, int] | None = None) -> list[tuple[str, set[str]]]:
    """The 'When' cell of every table row in DEADLINES.md, cleaned to the bare date text.
    A row whose date is today or earlier is skipped: a past date is history, and on its own day
    every other mention of that date (a dated log line, a 'since' note) was a false warning."""
    if today is None:
        t = time.localtime()
        today = (t.tm_year, t.tm_mon, t.tm_mday)
    text = (root / "DEADLINES.md").read_text(encoding="utf-8")
    dates = []
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("| When") or line.startswith("|---"):
            continue
        cols = [c.strip() for c in line.split("|")]
        cell = cols[1].strip("*").strip()
        cell = re.sub(r"^(~|by\s+)", "", cell).strip()
        status = cols[4] if len(cols) > 4 else ""
        what = cols[2].lower() if len(cols) > 2 else ""
        keywords = {w for w in re.findall(r"[a-zäöüß]{6,}", what)} - {"before", "should", "within", "cannot"}
        end = row_end(cell)
        if end is not None and end <= today:
            continue                        # today or earlier: history, not a live obligation
        if re.search(r"\d{4}", cell) and not re.search(r"\bDone\b", status):
            dates.append((cell, keywords))  # a fired obligation is history; later mentions are fine
    return dates


def check_dates(root: Path, files: list[Path],
                today: tuple[int, int, int] | None = None) -> tuple[list[str], list[str]]:
    """A DEADLINES date in another file fails when the line is about the same obligation
    (shares a keyword with the row's What cell); otherwise it is a coincidence (a wage
    rate that changes on 01.01.2027) and only a warning."""
    fails, warns = [], []
    for d, keywords in deadline_dates(root, today):
        forms = {re.escape(f) for f in (d, d.replace("–", "-"), d.replace("-", "–"))}
        pat = re.compile("|".join(forms))
        for p in files:
            r = rel(root, p)
            if r == "DEADLINES.md" or is_record(r):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            for m in pat.finditer(text):
                ln = text.count("\n", 0, m.start()) + 1
                if history_near(lines, ln) or "lint:other-subject" in lines[ln - 1]:
                    continue
                near = " ".join(lines[max(0, ln - 2):ln + 1]).lower()
                msg = f"{r}:{ln}: restates DEADLINES.md date '{d}'"
                if any(k in near for k in keywords):
                    fails.append(msg + " for the same obligation; point at DEADLINES.md instead")
                else:
                    warns.append(msg + " (different subject? if so, ignore)")
    return fails, warns


def check_pointers(root: Path, files: list[Path]) -> list[str]:
    fails = []
    for p in files:
        r = rel(root, p)
        if is_record(r):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        top = {e.name for e in root.iterdir() if not e.name.startswith(".")}
        for m in PATH_IN_TICKS.finditer(text):
            tok = m.group(1)
            if PLACEHOLDER.search(tok) or tok.startswith(("~", "/", "http")):
                continue
            if "/" not in tok and tok not in ROOT_FILES:
                continue                      # a bare filename like `main.tex`: not a repo pointer
            ln = text.count("\n", 0, m.start()) + 1
            if history_near(lines, ln):
                continue                      # "`x` was deleted on ..." is a record, not a pointer
            if (root / tok).exists() or (p.parent / tok).exists():
                continue
            hits = [d for d in top if (root / d / tok).exists()]
            if len(hits) == 1:
                fails.append(f"{r}:{ln}: pointer `{tok}` should be `{hits[0]}/{tok}` (paths are relative to the repo root)")
                continue
            first = tok.split("/")[0]
            if first not in top and tok not in ROOT_FILES:
                continue                      # a path in some other project (Hermes source etc.)
            fails.append(f"{r}:{ln}: dead pointer `{tok}`")
    return fails


def check_stale(root: Path, files: list[Path]) -> list[str]:
    warns = []
    for p in files:
        r = rel(root, p)
        if is_record(r):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not STALE_WORDS.search(text):
            continue
        age = last_commit_age_days(root, r)
        if age is not None and age >= STALE_DAYS:
            n = len(STALE_WORDS.findall(text))
            warns.append(f"{r}: {n} open-status phrase(s), last commit {age:.0f} days ago")
    return warns


def check_threats(root: Path, files: list[Path]) -> list[str]:
    fails = []
    for p in files:
        r = rel(root, p)
        if p.name in CONTEXT_FILES:
            scope = "context"
        elif p.match(SKILL_GLOB):
            scope = "strict"
        else:
            continue
        hits = threats(p.read_text(encoding="utf-8", errors="replace"), scope)
        if hits:
            fails.append(f"{r}: Hermes would block or quarantine this file: {', '.join(hits)}")
    return fails


def check_agents_size(root: Path) -> tuple[list[str], list[str]]:
    """Root and every nested AGENTS.md. Each is loaded whole when an agent works in its
    folder, so each gets the same limits as the root."""
    fails, warns = [], []
    nested = sorted(p for p in root.rglob("AGENTS.md")
                    if p.parent != root and not any(s in p.parts for s in (".git", ".claude", "private")))
    for p in [root / "AGENTS.md"] + nested:
        text = p.read_text(encoding="utf-8")
        n, lines = len(text), text.count("\n") + (0 if text.endswith("\n") else 1)
        name = rel(root, p)
        if n > AGENTS_FAIL or lines > AGENTS_LINES:
            fails.append(f"{name}: {n} chars / {lines} lines (limit {AGENTS_FAIL} / {AGENTS_LINES})")
        elif n > AGENTS_WARN:
            warns.append(f"{name}: {n} chars, over the {AGENTS_WARN} target")
    return fails, warns


def check_no_claude_md(root: Path) -> list[str]:
    fails = []
    for d, dirs, names in os.walk(root):
        here = Path(d)
        dirs[:] = [x for x in dirs if rel(root, here / x) not in WALK_SKIP]
        for n in names:
            if n not in BANNED_NAMES:
                continue
            r = rel(root, here / n)
            fails.append(f"{r}: delete it; the rules are AGENTS.md, and with a CLAUDE.md present "
                         "Claude Code stops reading AGENTS.md")
    return fails


HOME_CONFIGS = (".claude", ".gemini")
HOME_SKIP = {"projects", "worktrees", "brain", "conversations", "shell-snapshots", "todos"}


def check_home_links(root: Path) -> list[str]:
    fails, real = [], root.resolve()
    for cfg in HOME_CONFIGS:
        base = Path.home() / cfg
        for d, dirs, names in os.walk(base):
            here = Path(d)
            depth = len(here.relative_to(base).parts)
            dirs[:] = [x for x in dirs if x not in HOME_SKIP and depth < 3]
            for n in dirs + names:
                p = here / n
                if p.is_symlink() and p.resolve().is_relative_to(real):
                    fails.append(f"~/{p.relative_to(Path.home())} -> {p.resolve()}: remove it "
                                 "(a tool can treat the target as its own internal data; use the project links)")
    return fails


SECRET = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY|ssh-(rsa|ed25519) AAAA|ghp_[A-Za-z0-9]{20}|xox[baprs]-"
                    r"|sk-[A-Za-z0-9]{20}|(api[_-]?key|secret|password|token)\s*[:=]\s*[A-Za-z0-9_/+-]{20}",
                    re.I)


def check_staged(root: Path) -> list[str]:
    """Check 8: a staged .env file, or an added line that looks like a secret."""
    names = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=AM"],
                           cwd=root, capture_output=True, text=True).stdout.split()
    fails = []
    for n in names:
        if Path(n).name == ".env" or Path(n).name.startswith(".env."):
            fails.append(f"{n}: a .env file is staged; it belongs in a password manager")
            continue
        diff = subprocess.run(["git", "diff", "--cached", "-U0", "--", n], cwd=root,
                              capture_output=True, text=True, errors="replace").stdout
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++") and SECRET.search(line):
                fails.append(f"{n}: a staged line looks like a secret; unstage it and move it to a password manager")
                break
    return fails


def check_skill_docs(root: Path) -> list[str]:
    """Check 9: every skill on disk is named in each doc that lists the skills."""
    fails = []
    skills = sorted(p.parent.name for p in root.glob(SKILL_GLOB))
    for doc in SKILL_DOCS:
        p = root / doc
        if not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        missing = [s for s in skills if s not in txt]
        if missing:
            fails.append(f"{doc}: missing skill(s) {', '.join(missing)} (update the docs that list skills)")
    layers_svg = root / "skills" / "context-layers.svg"
    if layers_svg.is_file():
        ltxt = layers_svg.read_text(encoding="utf-8", errors="replace")
        if f"{len(skills)} skill descriptions" not in ltxt or f"the other {len(skills) - 1} skills" not in ltxt:
            fails.append(f"skills/context-layers.svg: skill count out of sync with {len(skills)} skills on disk")
    return fails


NUM_WORDS = {"five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16}
SKILL_COUNT = re.compile(r"\b(?P<other>other\s+)?(?P<n>\d{1,2}|" + "|".join(NUM_WORDS) +
                         r")\s+(?:reusable\s+)?(?:skills|workflows)\b", re.I)
COUNT_DOCS = ("skills/context-layers.svg",)


def check_skill_counts(root: Path, files: list[Path]) -> list[str]:
    """Check 10: every 'N skills' / 'N workflows' in a live file matches skills/ on disk.
    Check 9 only looks for skill names; a count in prose ('ten skills') goes stale silently."""
    n = len(list(root.glob(SKILL_GLOB)))
    fails = []
    paths = [p for p in files if not is_record(rel(root, p))] + [root / d for d in COUNT_DOCS]
    for p in paths:
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in SKILL_COUNT.finditer(line):
                raw = m.group("n").lower()
                said = NUM_WORDS.get(raw) or int(raw)
                if said < 5:      # "two skills" in prose is not a count of all of them
                    continue
                want = n - 1 if m.group("other") else n
                if said != want:
                    fails.append(f"{rel(root, p)}:{i}: says '{m.group(0)}', skills/ has {n}: fix the number, or drop it from prose")
    return fails


def check_scripts_listed(root: Path) -> list[str]:
    """Check 11: every script in scripts/ and scripts/hooks/ is named in README.md, so a new tool
    cannot arrive unannounced."""
    readme = (root / "README.md").read_text(encoding="utf-8", errors="replace")
    skip = {"AGENTS.md", "__pycache__"}
    names = [p.name for p in sorted((root / "scripts").iterdir()) if p.is_file() and p.name not in skip]
    hooks = root / "scripts" / "hooks"
    if hooks.is_dir():
        names += [p.name for p in sorted(hooks.iterdir()) if p.is_file() and p.name not in skip]
    missing = [x for x in names if x not in readme]
    return [f"README.md: script(s) not named anywhere: {', '.join(missing)}"] if missing else []


# (pattern, why). Add a row when a name, path or tool is replaced, so a copy of the old one
# cannot come back. Example:
#   (re.compile(r"scripts/old_sync\.sh"), "replaced by scripts/divan-sync"),
RETIRED: tuple[tuple[re.Pattern, str], ...] = ()
RETIRED_EXT = (".md", ".tex", ".sh", ".py", ".html", ".svg")
RETIRED_SKIP = ("scripts/lint.py",)


def check_retired(root: Path) -> list[str]:
    """Check 13: a retired name in a live tracked file."""
    if not RETIRED:
        return []
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True).stdout
    fails = []
    for r in out.split("\0"):
        if not r.endswith(RETIRED_EXT) or is_record(r) or r.startswith(RETIRED_SKIP):
            continue
        p = root / r
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for pat, why in RETIRED:
                if pat.search(line):
                    fails.append(f"{r}:{i}: retired name '{pat.search(line).group(0)}': {why}")
    return fails


# trigger (repo path regex) -> docs that describe it -> what they describe. One of the docs must
# change in the same work, or the warning names them. Add a row when a new coupling is found.
COUPLED = (
    (r"^scripts/(divan-sync|divan-watch)$|^scripts/systemd/",
     ("scripts/AGENTS.md", "skills/repo-sync/SKILL.md", "scripts/systemd/README.md"),
     "sync mechanics"),
    (r"^(scripts/hooks/[^/]+|\.claude/settings\.json|\.agents/hooks\.json|scripts/lint\.py)$",
     ("README.md", "AGENTS.md", "skills/README.md"),
     "the safety gates"),
    (r"^setup\.sh$", ("START_HERE.md", "README.md"), "the install steps"),
    (r"^Makefile$", ("README.md",), "the make commands"),
)


def changed_files(root: Path) -> set[str]:
    """Staged, unstaged, untracked, and committed but not yet pushed."""
    def git(*a: str) -> list[str]:
        r = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)
        return r.stdout.split() if r.returncode == 0 else []
    names = set(git("diff", "--cached", "--name-only")) | set(git("diff", "--name-only"))
    names |= set(git("ls-files", "--others", "--exclude-standard"))
    for base in ("@{upstream}", "origin/main"):
        if git("rev-parse", "--verify", "--quiet", base):
            names |= set(git("diff", "--name-only", f"{base}...HEAD"))
            break
    return names


def check_cochange(root: Path) -> list[str]:
    """Check 14 (W): a changed file from COUPLED whose docs did not change with it."""
    changed = changed_files(root)
    warns = []
    for pat, docs, what in COUPLED:
        hits = sorted(n for n in changed if re.search(pat, n))
        if hits and not any(d in changed for d in docs):
            warns.append(f"{', '.join(hits)} changed ({what}); none of {', '.join(docs)} did. "
                         "Review them; if nothing there is stale, ignore this")
    return warns


def check_log_length(root: Path) -> list[str]:
    """Check 15 (W): an added log entry over 800 characters (unpushed, staged or unstaged)."""
    warns = []
    r = None
    for base in ("@{upstream}", "origin/main", None):
        cmd = ["git", "diff", "-U0"] + ([base] if base else []) + ["--", "*_log.md"]
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        if r.returncode == 0:
            break
    file = ""
    for line in r.stdout.splitlines():
        if line.startswith("+++ "):
            file = line[6:]
        elif line.startswith("+- **") and len(line) - 1 > 800:
            warns.append(f"{file}: new entry is {len(line) - 1} chars (limit 800): {line[1:60]}...")
    return warns


DATED_CLAIM = re.compile(r"\b(?:as of|Stand(?: vom)?|status on)\s+"
                         r"(\d{2})\.(\d{2})\.(\d{4})", re.I)


def check_dated_claims(root: Path, files: list[Path]) -> list[str]:
    """Check 12 (W): a status claimed 'as of / Stand / status on DD.MM.YYYY' that is now older
    than STATUS_DAYS, in a live file. A status with a date goes stale while the file looks fine."""
    today = time.localtime()
    now = time.mktime((today.tm_year, today.tm_mon, today.tm_mday, 0, 0, 0, 0, 0, -1))
    warns = []
    for p in files:
        r = rel(root, p)
        if is_record(r):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in DATED_CLAIM.finditer(line):
                try:
                    then = time.mktime((int(m.group(3)), int(m.group(2)), int(m.group(1)), 0, 0, 0, 0, 0, -1))
                except (OverflowError, ValueError):
                    continue
                age = int((now - then) // 86400)
                if age > STATUS_DAYS:
                    warns.append(f"{r}:{i}: '{m.group(0)}' is {age} days old: re-check it, or move it to a log")
    return warns


def probe() -> int:
    """Self-check for check 1 (`--probe`): a scratch DEADLINES.md with a past, a today and a
    future row, and one file that names all three dates. Only the future date may be reported."""
    import tempfile
    assert row_end("~03.10.2026") == (2026, 10, 3)
    assert row_end("2–9 Nov 2026") == (2026, 11, 9)
    assert row_end("Feb–Mar 2027") == (2027, 3, 31)
    assert row_end("someday") is None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "DEADLINES.md").write_text(
            "| When | What | Detail in | Status |\n|---|---|---|---|\n"
            "| 01.10.2026 | Past row | x | Open. |\n"
            "| ~03.10.2026 | Today row | x | Open. |\n"
            "| 2–9 Nov 2026 | Future window | x | Open. |\n", encoding="utf-8")
        note = root / "note.md"
        note.write_text("Met on 01.10.2026.\nSince 03.10.2026 it runs.\nWindow 2–9 Nov 2026.\n",
                        encoding="utf-8")
        fails, warns = check_dates(root, [note], today=(2026, 10, 3))
    hits = fails + warns
    ok = len(hits) == 1 and "2–9 Nov 2026" in hits[0]
    print("probe check_dates:", "ok" if ok else f"FAILED {hits}")
    return 0 if ok else 1


# ----------------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    if "--probe" in argv:
        return probe()
    quiet = "--quiet" in argv
    root = repo_root()
    files = tracked_md(root)

    fails, warns = [], []
    f, w = check_dates(root, files)
    fails += f
    warns += w
    fails += check_pointers(root, files)
    warns += check_stale(root, files)
    fails += check_threats(root, files)
    f, w = check_agents_size(root)
    fails += f
    warns += w
    fails += check_no_claude_md(root)
    fails += check_home_links(root)
    fails += check_staged(root)
    fails += check_skill_docs(root)
    fails += check_skill_counts(root, files)
    fails += check_scripts_listed(root)
    warns += check_dated_claims(root, files)
    warns += check_log_length(root)
    fails += check_retired(root)
    docs = check_cochange(root)

    if docs:            # printed even with --quiet: the commit is the moment to fix them
        print("lint: docs to review (not blocking)")
        for d in docs:
            print("  D ", d)
    if warns and not quiet:
        print("lint: warnings (not blocking)")
        for w in warns:
            print("  W ", w)
    if fails:
        print(f"lint: {len(fails)} failure(s); commit refused")
        for x in fails:
            print("  F ", x)
        return 1
    if not quiet:
        print(f"lint: clean ({len(files)} markdown files, {len(warns)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
