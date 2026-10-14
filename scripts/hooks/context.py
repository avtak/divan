#!/usr/bin/env python3
"""context.py: put the open rows of DEADLINES.md in front of a session without asking it to read.

Claude Code  SessionStart hook: plain stdout is added to the model's context.
Hermes       pre_llm_call shell hook (--hermes): prints {"context": "..."} on the FIRST turn only
             (Hermes fires pre_llm_call every turn; the payload's extra.is_first_turn says which).
Antigravity  PreInvocation hook (--antigravity): prints {"injectSteps": [{"ephemeralMessage":
             "..."}]} when invocationNum is 0, else {}.

Why: AGENTS.md "Before you start" (read DEADLINES.md) is a pointer, and pointers are followed
sometimes. An injected block is read every time. It lists what is overdue and what falls due in
the next 7 days, and raises the [FOCUS-GUARD] alert (skills/focus-guard/SKILL.md) for the latter.
Stdlib only. Never breaks a session: any error becomes one line in the briefing.
"""
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HEADER = "Session context (scripts/hooks/context.py, from DEADLINES.md):\n"
SOON_DAYS = 7
DONE = re.compile(r"^\W*(done|closed|resolved)\b", re.I)


def _trace(who: str, line: str) -> None:
    """One line per firing into .agents/hooks.log (gitignored): the only way to see whether
    Antigravity ran a hook and with what payload, since its logs are not readable from a repo."""
    try:
        log_file = ROOT / ".agents" / "hooks.log"
        if log_file.exists() and log_file.stat().st_size > 500_000:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            log_file.write_text("\n".join(lines[-1000:]) + "\n", encoding="utf-8")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {who}: {line}\n")
    except Exception:
        pass


def plain(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def first_date(cell: str) -> datetime.date | None:
    """The earliest day a 'When' cell can bite: '15.09.2026', '~03.10.2026', '08-14.06.2027'
    (day range: the first day) or '2026-09-15'. None when no date can be read."""
    m = re.search(r"(\d{1,2})\s*[-–]\s*\d{1,2}\.(\d{1,2})\.(\d{4})", cell) \
        or re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", cell)
    try:
        if m:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", cell)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        pass
    return None


def day_phrase(days: int) -> str:
    if days < 0:
        return f"{-days} day(s) overdue"
    return {0: "today", 1: "tomorrow"}.get(days, f"in {days} days")


def briefing(today: datetime.date | None = None) -> str:
    today = today or datetime.date.today()
    path = ROOT / "DEADLINES.md"
    if not path.is_file():
        return HEADER + "DEADLINES.md is missing. Every dated obligation lives there.\n"
    open_rows, soon, undated = [], [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|-") or line.startswith("| When"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or DONE.match(plain(cells[3])):
            continue
        when, what = plain(cells[0]), plain(cells[1])[:150]
        due = first_date(cells[0])
        if due is None:
            undated.append(f"- {when} | {what}")
            continue
        days = (due - today).days
        if days <= SOON_DAYS:
            open_rows.append((days, f"- {when} | {day_phrase(days)}\n> {what}"))
            if days >= 0:
                soon.append(f"{when} | {day_phrase(days)}: {what[:65]}")
    out = [HEADER, f"Today: {today:%A %d.%m.%Y}\n"]
    if soon:
        out.append("\n[FOCUS-GUARD] Open deadline(s) within 7 days: " + " ; ".join(soon) +
                   "\nIf the owner asks for non-essential tooling or infrastructure work, trigger "
                   "skills/focus-guard/SKILL.md.\n")
    if open_rows:
        out.append("\n* OVERDUE AND THIS WEEK\n" + "\n".join(r for _, r in sorted(open_rows)) + "\n")
    else:
        out.append("\nNothing overdue and nothing due in the next 7 days.\n")
    if undated:
        out.append("\nRows without a readable date (fix the When cell):\n" + "\n".join(undated) + "\n")
    return "".join(out)[:8000]


def safe_briefing() -> str:
    try:
        return briefing()
    except Exception as e:                          # never break a session over a briefing
        return HEADER + f"(briefing unavailable: {e})\n"


def main(argv: list[str]) -> int:
    if "--hermes" in argv:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
        if not (payload.get("extra") or {}).get("is_first_turn", False):
            print("{}")
            return 0
        print(json.dumps({"context": safe_briefing()}))
        return 0
    if "--antigravity" in argv:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
        n = payload.get("invocationNum")
        steps = payload.get("initialNumSteps") or 0
        _trace("context", f"invocationNum={n!r} initialNumSteps={steps!r}")
        if n != 0 or steps > 2:
            print("{}")
            return 0
        print(json.dumps({"injectSteps": [{"ephemeralMessage": safe_briefing()}]}))
        return 0
    print(safe_briefing())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
