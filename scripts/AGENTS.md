# scripts/: sync mechanics, and which machine writes which file

*How the git sync works and which machine writes which file. The root `AGENTS.md` keeps only the rule.*

## How the sync works

**`scripts/divan-sync` is how this repo syncs, on every machine.** It pulls with `--rebase --autostash`, refuses to commit anything that looks like a secret, commits, and pushes. It aborts rather than guessing. On the laptop a user timer runs it every 5 minutes (`scripts/systemd/laptop/`, installed by `setup.sh --sync`). `make sync` runs it once now. On an optional server, `scripts/divan-watch` runs it once changes settle (`scripts/systemd/server/`). Every setting is an environment variable named in the script's header.

**The laptop commits only settled files.** It commits edits only after the changed files sat untouched for 10 minutes (`DIVAN_SETTLE=600`), so half-edited work is never committed. The quiet time is measured before the rebase, because the autostash stamps every file with the current time. Hand-written commits and `.sync-message` are preferred. What each ABORT means and how to fix it: skill `repo-sync`.

**The laptop timer pauses during agent sessions, and tidies worktrees after them.** Why: a run in the middle of a session stashed and re-applied the agent's open edits. While a `claude` or Antigravity process works inside the repo, the timer logs `SKIP agent session active` and does nothing; the session syncs itself, and `make sync` (`DIVAN_MANUAL=1`) always runs. Each run also removes a worktree in `.claude/worktrees/` that is clean, not locked or in use, and whose every commit is already in origin/main, with its branch. It deletes any other local `claude/*` or `worktree-*` branch whose commits are all in main. It never merges: a worktree with work not in main stays and gets a `HOLD worktree` line.

**The laptop holds back rule files.** Without a `.sync-message`, the laptop timer holds every rule file named in the "Rule files" bullet of root `AGENTS.md` (the list is `DIVAN_RULES` in the script). It commits the rest and writes a `HOLD` line naming the held files to its log. Why: an agent's rule edit can still wait for the owner's yes, and the timer must not publish it. A hand commit or a `.sync-message` releases the hold. A server (`DIVAN_SETTLE=0`) never holds, so a server agent must ask the owner first itself.

**Edge cases the script handles.** Runs never overlap (`flock`). A rebase or merge already in progress, an unresolved conflict or a busy index make it stop or skip. Offline is a quiet skip, not an error. Uncommitted edits that clash with incoming changes are reported instead of passing silently. A staged `<<<<<<<` marker is never committed. Commits made by hand but never pushed get pushed. `*_log.md` and `diary/*.md` use git's union merge (`.gitattributes`), so two entries added at the top on two machines are both kept.

**`.sync-message`.** An agent writes a one-line `.sync-message` in the repo root. The sync uses its first line as the commit message and deletes the file. If it is absent, the message is `<prefix>: sync <changed paths>` (`DIVAN_PREFIX`, default the role). It is gitignored. For a commit with a body, write a `.commit-*.txt` and use `git commit -F`.

**`scripts/hooks/pre-commit`** runs `scripts/lint.py` on every commit. The lint refuses any `CLAUDE.md` or `CLAUDE.local.md`, because with one present Claude Code ignores `AGENTS.md`. `setup.sh` enables the hook with `git config core.hooksPath scripts/hooks`. `scripts/hooks/commit-msg` runs the same secret and identifier patterns on the commit message, because a message stays in git history like a file.

## Who writes what

Two writers on the same lines inside one sync window is a conflict, so every file has one home:

| File | Writer | Everyone else |
|---|---|---|
| `*_log.md`, `diary/*.md` | append-only, any machine | append at the top, never rewrite an old entry |
| `DEADLINES.md` rows | an agent or the owner, **on one machine per sync window** | sync first |
| Rule files (`AGENTS.md`, `skills/`, `ABOUT_ME.md`, `README.md`, `START_HERE.md`) | **any machine, one at a time** | sync first. A rule edit needs the owner's yes before it |
| `private/` | nobody in git | stays on the laptop |

Add a row when a file gets a single writer, for example a data file only a server job writes.

## When it goes wrong

Two edits to the same paragraph of a prose file on two machines in one window is the one case the table cannot prevent. The sync then stops safely (`ABORT pull/rebase failed` in the log). A human resolves it after reading `git show` of the stuck commit. Never `git reset --hard` to get out of it: a rebase that stops has lost nothing yet, and a hard reset destroys unpushed edits.
