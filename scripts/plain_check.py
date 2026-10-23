#!/usr/bin/env python3
"""plain_check.py: count the places where a text breaks the plain-English rules.

The rules are `skills/working-terms/SKILL.md` section 1a: short sentences after ASD-STE100
(20 words for an instruction, 25 for a description), active voice, condition before command,
no contractions, no hedging, no hype words, no semicolons or em-dashes. This script finds
patterns. It cannot judge meaning, so a hit is a place to look at, not a verdict.

Not checked, because the rules exempt them: fenced code, `inline code`, "quoted text", table
rows, headings, URLs and file paths.

  python3 scripts/plain_check.py FILE [FILE ...]            descriptions: 25 words
  python3 scripts/plain_check.py --instructions FILE        instructions: 20 words
  python3 scripts/plain_check.py --gate FILE                exit 1 when anything is found
  python3 scripts/plain_check.py --self-test
  cat text.md | python3 scripts/plain_check.py -

Output: one line per hit (file:line: kind: the words), then a count per kind.
Stdlib only, no network.
"""
from __future__ import annotations

import re
import sys
from collections import Counter

HYPE = ("robust", "seamless", "seamlessly", "crucial", "leverage", "leverages", "leveraging",
        "cutting-edge", "game-changer", "game-changing", "groundbreaking", "revolutionary",
        "unlock", "unlocks", "empower", "empowers", "supercharge", "synergy", "holistic",
        "world-class", "best-in-class", "next-generation", "transformative", "unparalleled",
        "effortless", "effortlessly", "powerful", "innovative", "state-of-the-art")
HEDGES = ("should", "would", "may", "might")
CONTRACTION = re.compile(r"\b\w+(?:n't|'re|'ve|'ll|'d|'m)\b|\b(?:it|that|there|what|here|he|she)'s\b", re.I)
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?(\w+(?:ed|en))\b", re.I)
NOT_PARTICIPLE = {"open", "often", "even", "seven", "eleven", "golden", "hidden", "given", "listen",
                  "kitchen", "garden", "token", "broken", "children", "women", "men", "ten", "then",
                  "when", "seen", "been", "between", "screen", "green", "need", "needed", "used", "based"}
IMPERATIVE_START = re.compile(r"^(?:Run|Read|Open|Write|Add|Use|Check|Delete|Copy|Move|Set|Start|Stop|"
                              r"Fix|Give|Name|Send|Make|Put|Keep|Ask|Tell|Close|Save|Install|Push|Pull|"
                              r"Commit|Build|Remove|Do|Never|Always)\b")
SKIP_LINE = re.compile(r"^\s*(?:\||#|<!--|---|```|~~~)")
STRIP = [re.compile(p) for p in (r"`[^`]*`", r"\"[^\"]*\"", r"“[^”]*”", r"https?://\S+", r"\S+/\S+",
                                  r"<[^>]+>")]
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def clean(line: str) -> str:
    """The line with the exempt parts removed and markdown marks dropped."""
    line = LINK.sub(r"\1", line)
    for pat in STRIP:
        line = pat.sub(" ", line)
    return re.sub(r"[*_]+", "", line)


def sentences(text: str) -> list[tuple[int, str]]:
    """(line number, sentence) for the prose in text. A list item or a blank line ends a sentence."""
    out, buf, start, fence = [], [], 0, False
    for n, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        item = re.match(r"^\s*(?:[-*+]|\d+[.)])\s", raw)
        if fence or SKIP_LINE.match(raw) or not raw.strip() or item:
            if buf:
                out += split(start, " ".join(buf))
                buf = []
            if fence or SKIP_LINE.match(raw) or not raw.strip():
                continue
            raw = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", raw)
        if not buf:
            start = n
        buf.append(clean(raw))
    if buf:
        out += split(start, " ".join(buf))
    return out


def split(line_no: int, para: str) -> list[tuple[int, str]]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", para.strip())
    return [(line_no, p.strip()) for p in parts if re.search(r"[A-Za-z]", p)]


def words(s: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9](?:[A-Za-z0-9'’-]|[.,](?=\d))*", s)   # 18.09 and 1,234 are one word


def check(text: str, limit: int) -> list[tuple[int, str, str]]:
    hits = []
    for n, s in sentences(text):
        w = words(s)
        low = [x.lower() for x in w]
        if len(w) > limit:
            hits.append((n, "long sentence", f"{len(w)} words (limit {limit}): {' '.join(w[:8])} ..."))
        for h in HEDGES:
            if h in low:
                hits.append((n, "hedge", h))
        for h in HYPE:
            if h in low:
                hits.append((n, "hype word", h))
        for m in CONTRACTION.finditer(s):
            hits.append((n, "contraction", m.group(0)))
        for m in PASSIVE.finditer(s):
            if m.group(1).lower() not in NOT_PARTICIPLE:
                hits.append((n, "passive (check)", m.group(0)))
        if ";" in s:
            i = s.index(";")
            hits.append((n, "semicolon", s[max(0, i - 30):i + 10].strip()))
        if "—" in s or re.search(r"\s--\s", s):
            hits.append((n, "em-dash", "—"))
        if IMPERATIVE_START.match(s) and re.search(r",?\s+(?:if|when|unless)\s", s):
            hits.append((n, "condition after command", " ".join(w[:8])))
    return hits


def self_test() -> int:
    bad = ("You should run it; it's robust — really.\n"
           "Run the build if the tests pass.\n"
           "The file was deleted by the script.\n"
           "This sentence has far too many words in it because it keeps going and going and going "
           "past every sensible limit that a tired reader can follow without a break.\n")
    good = ("If the tests pass, run the build. The script deletes the file.\n\n"
            "```\nx = 1; y = 2  # code is exempt\n```\n| a; b | table rows are exempt |\n"
            "Use `a; b` and \"it's fine\" freely.\n")
    kinds = {k for _, k, _ in check(bad, 25)}
    want = {"hedge", "semicolon", "contraction", "hype word", "em-dash", "condition after command",
            "passive (check)", "long sentence"}
    clean_hits = check(good, 25)
    ok = want <= kinds and not clean_hits
    print("self-test:", "ok" if ok else f"FAILED: missing {want - kinds}, clean text hits {clean_hits}")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    limit = 20 if "--instructions" in argv else 25
    gate = "--gate" in argv
    files = [a for a in argv if not a.startswith("--") or a == "-"]
    if not files:
        print(__doc__)
        return 2
    total = Counter()
    for f in files:
        text = sys.stdin.read() if f == "-" else open(f, encoding="utf-8").read()
        for n, kind, what in check(text, limit):
            print(f"{f}:{n}: {kind}: {what}")
            total[kind] += 1
    summary = ", ".join(f"{k} {v}" for k, v in total.most_common()) or "nothing found"
    print(f"plain_check: {sum(total.values())} hit(s). {summary}")
    return 1 if gate and total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
