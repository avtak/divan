# System change log

What changed in this repo's machinery, and why: the hooks, the lint, the sync, the skills, the plan. **This is a change log, not a diary.** What happened on a given day and how it went goes in `diary/<YYYY-MM>.md`.

Newest entries at the top, directly under `## Log`. Format and rules: skill `record`.

---

## Log

- **09.11.2026**: **Release 2: lessons from daily use.** `focus-guard`: an explicit instruction is not a trigger (the guard had stopped an install the owner had decided on). `working-terms`: answer only what the owner asked, and ask once per task. `context.py`: the session summary is background only, and `[FOCUS-GUARD]` is a count and the nearest date. Lint COUPLED map: a changed `SKILL.md` names the docs that list skills. Lessons L007 and L008.
- **02.11.2026**: **arXiv link added.** README citation, BibTeX (`eprint`, `doi`, `url`) and the page's Cite box now carry arXiv:2610.32578, DOI 10.48550/arXiv.2610.32578. Closes the 23.10 Owed.
- **23.10.2026**: **Lessons from the harness study (`docs/lessons-outlive-their-failures.html`).** `guard.py` reads shell words (catches git global flags before reset, allows quoted mentions; `--probe`). Lint check 8 adds identifiers and a `commit-msg` hook, check 16 heading pointers, check 17 a rule budget, check 18 the lesson register `logs/lessons.csv`. `make audit-docs` runs three times and merges. `make replay` retires lessons that no longer change the agent. **Owed:** the arXiv link once announced.
- **DD.MM.YYYY**: **Started from divan Release 0.** Hooks, lint, sync and five skills installed with `setup.sh`.
