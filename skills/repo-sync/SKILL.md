---
name: repo-sync
description: "Checks or repairs the git sync of this repo between the owner's machines. Use when the owner says 'sync', 'pull', 'push didn't go through', 'is the server's change on my laptop', when a 'divan sync stopped' notification appears, or when a sync log shows ABORT or HOLD."
---

# repo-sync: keeping every clone on the same repo

**User-invoked.** Fires when the owner says 'sync', 'pull', or a sync error appears.

Every machine that writes this repo runs `scripts/divan-sync`; git is the only sync. Pull first, one machine per file: `AGENTS.md` ("Before you start"). How it is wired and who writes what: `scripts/AGENTS.md`. This skill covers how to check it and what each `ABORT` means.

## Check

On the laptop:

```bash
make sync                       # runs divan-sync now and prints the last 3 log lines
git status -sb | head -1        # want: ## main...origin/main, no [ahead]/[behind]
```

On a server: run `scripts/divan-sync` as the user that owns the clone. Both write `~/.local/state/divan-sync.log` unless `DIVAN_LOG` says otherwise.

These lines are normal:
- `WAIT changes still settling`, `SKIP fetch failed (offline?)`.
- `HOLD rule files not committed` (laptop). It repeats every run until the owner approves the held rule files: commit them by hand or write a `.sync-message`.
- `SKIP agent session active` (laptop). The timer pauses while Claude Code or Antigravity works in the repo; `make sync` still runs.
- `CLEAN removed worktree` or `CLEAN deleted branch`: its work was already in main.
- `HOLD worktree … not in main`: push that worktree's work to main, or tell the owner.

Only `ABORT` lines need a person. On the laptop an ABORT also raises one desktop notification.

## Each ABORT, and the fix

Read the line, then act. Never `git reset --hard`, never force-push (`AGENTS.md` Hard rules).

| ABORT says | Fix |
|---|---|
| `uncommitted edits clashed with incoming changes` / `unresolved conflict in <file>` | Open the file; both versions are there between the `<<<<<<<`, `=======` and `>>>>>>>` lines. Keep the right one, delete the markers, `git add <file>`, then `git stash drop`. The next run syncs. |
| `pull/rebase failed` | A committed change clashes with another machine. `git fetch && git log --oneline HEAD..origin/main` shows what came in; `git rebase origin/main`, resolve as above, `git rebase --continue`. If you are stuck, read `git show` of the stuck commit and ask the owner. |
| `rebase/merge in progress` | Someone started one by hand. Finish it (`git rebase --continue`) or `git rebase --abort`. |
| `possible secret in staged changes` | Nothing was committed. Move the secret out of the repo (a password manager or `private/`), then let it run. |
| `conflict markers in staged changes` | A file still contains `<<<<<<<` lines. Clean it up. |
| `commit failed (pre-commit lint?)` | `python3 scripts/lint.py` after `git add -A` prints the file:line; fix it. |
| `push failed` | Usually offline or GitHub down; it retries by itself. If it persists: `git push` by hand and read the error. |
| `not on main` | `git switch main`. |
