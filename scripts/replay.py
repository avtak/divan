#!/usr/bin/env python3
"""replay.py: does a lesson still change what the agent does? `make replay`.

A lesson is a prose rule or a code check you added after an agent failure. Models improve, and a
lesson can outlive the failure it was written for. This script tests that. For each scenario, a
throwaway clone at the commit before the lesson (condition A, no lesson) and the same clone with
only the lesson added (B) get the original task, headless, RUNS times each. If the failure no
longer happens in A, the lesson is a retirement candidate. The owner decides. A retired prose rule
moves to logs/archive/ with this result, and its row in logs/lessons.csv gets status retired.
Keep code checks unless they misfire: they cost nothing per session.

Why: in the harness study, three of four finished replays did not fail with or without the fix on
a current model, while the one drift failure (a stale count) came back every time without its
lint check. The study also found a confound: the agent reads the host date, so a clone's old
deadlines looked close and the focus-guard skill refused the task in 7 of 30 runs.
`--clock shift` (default) moves every date in the clone's DEADLINES.md forward by the days since
the base commit, the same in A and B. `--clock faketime` runs the agent under libfaketime at the
base commit's date instead; it needs the `faketime` program, and whether it works on the `claude`
executable is not verified.

Add a scenario to scenarios.json next to this script (or pass --scenarios FILE):

  {"stale-count": {
     "kind": "lint",                      # rule, lint or hook: only "rule" can be a retire candidate
     "base": "abc1234",                   # the commit the clones start from
     "A_files": {"scripts/lint.py": "abc1234^"},   # files taken from another commit in A ...
     "B_files": {},                       # ... or in B (B_insert: [path, line-prefix, text] adds a line)
     "prompt": "Add a skill called follow-up-check and commit it.",
     "fail_if": {"command": "regex on any shell command the agent ran",
                 "text": "regex on the agent's answer",
                 "file": ["path/in/clone.md", "regex on that file after the run"]}}}

Any fail_if test that matches marks the run failed. Write tests that a reader can check.

  python3 scripts/replay.py WORKDIR [--runs 10] [--model sonnet] [--clock shift|faketime|none] [scenario ...]
  python3 scripts/replay.py WORKDIR --summary

WORKDIR must be outside the repo and outside ~/.claude. A finished run is skipped, so a stopped
batch resumes. One run at a time, 1 GB memory cap, lowest priority. Delete WORKDIR afterwards.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

DENY = ["WebFetch", "WebSearch", "Agent", "Task", "Workflow", "Bash(ssh:*)", "Bash(scp:*)", "Bash(curl:*)", "Bash(wget:*)",
        "Bash(git push:*)", "Bash(make sync:*)"]
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(cwd, *a, check=True):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr[-300:]}")
    return r.stdout


def shift_deadlines(d: str, days: int) -> None:
    """Move every DD.MM.YYYY and YYYY-MM-DD date in the clone's DEADLINES.md forward by days."""
    p = os.path.join(d, "DEADLINES.md")
    if not os.path.exists(p) or days <= 0:
        return
    delta = datetime.timedelta(days=days)

    def de(m):
        try:
            return (datetime.date(int(m[3]), int(m[2]), int(m[1])) + delta).strftime("%d.%m.%Y")
        except ValueError:
            return m[0]

    def iso(m):
        try:
            return (datetime.date(int(m[1]), int(m[2]), int(m[3])) + delta).isoformat()
        except ValueError:
            return m[0]

    text = open(p, encoding="utf-8").read()
    text = re.sub(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", de, text)
    text = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", iso, text)
    open(p, "w", encoding="utf-8").write(text)


def build(sc, cond, d, clock):
    os.makedirs(d)
    git(d, "init", "-q", "-b", "main")
    sha = git(REPO, "rev-parse", sc["base"]).strip()
    git(d, "fetch", "-q", REPO, sha)
    git(d, "checkout", "-q", "-B", "main", sha)
    git(d, "config", "user.name", "replay"); git(d, "config", "user.email", "replay")
    git(d, "config", "core.hooksPath", "scripts/hooks")
    for path, rev in sc.get(f"{cond}_files", {}).items():
        content = git(REPO, "show", f"{git(REPO, 'rev-parse', rev).strip()}:{path}")
        os.makedirs(os.path.dirname(os.path.join(d, path)) or d, exist_ok=True)
        open(os.path.join(d, path), "w", encoding="utf-8").write(content)
    if cond == "B" and sc.get("B_insert"):
        path, prefix, text = sc["B_insert"]
        lines = open(os.path.join(d, path), encoding="utf-8").read().split("\n")
        i = next(n for n, l in enumerate(lines) if l.startswith(prefix))
        lines.insert(i + 1, text)
        open(os.path.join(d, path), "w", encoding="utf-8").write("\n".join(lines))
    base_day = datetime.date.fromtimestamp(int(git(d, "log", "-1", "--format=%ct").strip()))
    if clock == "shift":
        shift_deadlines(d, (datetime.date.today() - base_day).days)
    git(d, "add", "-A")
    git(d, "commit", "-q", "--allow-empty", "--no-verify", "-m", "sync")   # same neutral commit in A and B
    return base_day


def transcript(d):
    tag = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(d))
    files = glob.glob(os.path.expanduser(f"~/.claude/projects/{tag}/*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def commands(tpath):
    cmds = []
    for line in open(tpath, encoding="utf-8") if tpath else []:
        ev = json.loads(line)
        for b in (ev.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                cmds.append(b.get("input", {}).get("command", ""))
    return cmds


def judge(sc, d, row) -> str:
    """failed, ok or declined for one run."""
    text = row.get("result") or ""
    if "focus-guard" in text.lower() and not row["bash_cmds"]:
        return "declined"
    f = sc.get("fail_if", {})
    if f.get("command") and any(re.search(f["command"], c) for c in row["bash_cmds"]):
        return "failed"
    if f.get("text") and re.search(f["text"], text):
        return "failed"
    if f.get("file"):
        path, pat = f["file"]
        p = os.path.join(d, path)
        if os.path.exists(p) and re.search(pat, open(p, encoding="utf-8", errors="replace").read()):
            return "failed"
    return "ok"


def run_one(work, scenarios, name, cond, run, model, clock):
    sc = scenarios[name]
    d = os.path.join(work, f"{name}_{cond}_{run}")
    base_day = build(sc, cond, d, clock)
    cap = ["timeout", "900", "systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=1G", "nice", "-n", "19"]
    if clock == "faketime":
        cap += ["faketime", base_day.isoformat() + " 12:00:00"]
    cmd = cap + ["claude", "-p", sc["prompt"], "--model", model, "--output-format", "json", "--setting-sources",
                 "project", "--strict-mcp-config", "--allowedTools", "Read", "Edit", "Write", "Grep", "Glob", "Bash",
                 "Skill", "--disallowedTools", *DENY]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    try:
        res = json.loads(r.stdout)
    except ValueError:
        res = {"result": ""}
    row = {"scenario": name, "cond": cond, "run": run, "model": model, "clock": clock, "exit": r.returncode,
           "wall_s": round(time.time() - t0), "cost_usd": res.get("total_cost_usd"),
           "result": (res.get("result") or "")[:3000], "bash_cmds": commands(transcript(d))}
    row["verdict"] = judge(sc, d, row)
    with open(os.path.join(work, "results.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    shutil.rmtree(d, ignore_errors=True)       # the result row holds what the clone showed
    print(f"{name} {cond} {run}: {row['verdict']} ({row['wall_s']} s)", flush=True)


def summary(work, scenarios) -> int:
    p = os.path.join(work, "results.jsonl")
    rows = [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []
    print(f"{len(rows)} runs, API-equivalent ${sum(r.get('cost_usd') or 0 for r in rows):.2f}")
    for name in sorted({r["scenario"] for r in rows}):
        cells = {}
        for c in "AB":
            vs = [r["verdict"] for r in rows if r["scenario"] == name and r["cond"] == c]
            cells[c] = (vs.count("failed"), vs.count("failed") + vs.count("ok"), vs.count("declined"))
        (fa, na, xa), (fb, nb, xb) = cells["A"], cells["B"]
        kind = scenarios.get(name, {}).get("kind", "?")
        if na < 10:
            verdict = f"too few finished A runs ({na}); need 10"
        elif fa == 0:
            verdict = ("RETIRE CANDIDATE: no failure without the lesson" if kind == "rule"
                       else "keep (code check), but the failure no longer happens without it")
        else:
            verdict = "keep: the failure still happens without the lesson"
        print(f"{name:14} A failed {fa}/{na}  B failed {fb}/{nb}  declined A {xa} B {xb}  [{kind}] {verdict}")
    return 0


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    work = os.path.abspath(os.path.expanduser(argv[0]))
    if work.startswith(os.path.expanduser("~/.claude")) or work.startswith(REPO):
        raise SystemExit("WORKDIR must be outside the repo and outside ~/.claude")
    opts = {"--runs": "10", "--model": "sonnet", "--clock": "shift",
            "--scenarios": os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios.json")}
    names, i = [], 1
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i] == "--summary":
            i += 1
        else:
            names.append(argv[i])
            i += 1
    scenarios = json.load(open(opts["--scenarios"], encoding="utf-8")) if os.path.exists(opts["--scenarios"]) else {}
    os.makedirs(work, exist_ok=True)
    if "--summary" in argv:
        return summary(work, scenarios)
    if not scenarios:
        raise SystemExit(f"no scenarios: write {opts['--scenarios']} (format in this script's docstring)")
    if opts["--clock"] == "faketime" and not shutil.which("faketime"):
        raise SystemExit("faketime is not installed; use --clock shift")
    names = names or list(scenarios)
    p = os.path.join(work, "results.jsonl")
    done = {(r["scenario"], r["cond"], r["run"]) for r in map(json.loads, open(p, encoding="utf-8"))} if os.path.exists(p) else set()
    for run in range(1, int(opts["--runs"]) + 1):
        for name in names:
            for cond in "AB":
                if (name, cond, run) not in done:
                    shutil.rmtree(os.path.join(work, f"{name}_{cond}_{run}"), ignore_errors=True)  # a stopped run
                    run_one(work, scenarios, name, cond, run, opts["--model"], opts["--clock"])
    return summary(work, scenarios)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
