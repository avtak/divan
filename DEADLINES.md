# Deadlines

Every dated obligation, in one place, soonest first. **The detail stays where it lives. This file carries only the date, the obligation, and where to look.**

**Rule 1: if a date appears here, it appears nowhere else.** Anything that needs the detail follows the pointer. `scripts/lint.py` check 1 refuses a commit that restates an open row's date in a live file.

**Rule 2: write the obligation, never the countdown.** "Tomorrow" or "in 16 days" is true for one day. `scripts/hooks/context.py` computes it at every session start.

**Format.** `When` holds one date: `15.09.2026`, `~03.10.2026` (approximate) or `08-14.06.2027` (a window). `Status` starts with `Done`, `Closed` or `Resolved` once the row has fired. A row the hook cannot date shows up as a warning, never disappears.

---

| When | What | Detail in | Status |
|---|---|---|---|
| **01.01.2026** | Example row: delete it, then add your first real deadline. | `ABOUT_ME.md` | Done. |
