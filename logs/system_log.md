# System change log

What changed in this repo's machinery, and why: the hooks, the lint, the sync, the skills, the plan. **This is a change log, not a diary.** What happened on a given day and how it went goes in `diary/<YYYY-MM>.md`.

Newest entries at the top, directly under `## Log`. Format and rules: skill `record`.

---

## Log

- **23.10.2026**: **Lessons from the harness study (`docs/lessons-outlive-their-failures.html`).** `guard.py` reads shell words (catches git global flags before reset, allows quoted mentions; `--probe`). Lint check 8 adds identifiers and a `commit-msg` hook, check 16 heading pointers, check 17 a rule budget, check 18 the lesson register `logs/lessons.csv`. `make audit-docs` runs three times and merges. `make replay` retires lessons that no longer change the agent. **Owed:** the arXiv link once announced.
- **DD.MM.YYYY**: **Started from divan Release 0.** Hooks, lint, sync and five skills installed with `setup.sh`.
