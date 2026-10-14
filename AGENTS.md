# AGENTS.md

This repo is the owner's system of record: plain markdown in git, so it outlives any tool or model. Every agent loads this file at session start.

**Owner:** <your name>. In every skill and hook, "the owner" means this person. Who they are: `ABOUT_ME.md`.

**Write less.** In a log entry, a doc or any `.md` file, write the fact and the reason. Nothing else: no retelling, no history, no explaining the obvious. Before you write to a file, ask: does each line change what the reader does? If not, cut it.

## Before you start

1. Run `git pull --rebase`. If more than one machine writes this repo, git is the only sync. Only one machine edits a file between syncs.
2. Read `DEADLINES.md`. Claude Code, Antigravity and Hermes show its open rows through a hook at session start. In any other tool, open it.
3. Read `skills/working-terms/SKILL.md` before your first answer. In Claude Code, start it with the Skill tool.

## Hard rules

- **`private/` stays out of git and out of anything public or hosted.** Never paste it into a cloud service or a hosted memory.
- **Identifiers live in a password manager.** No file here holds one, gitignored or not: an account, contract, document or case number, a PIN, a balance, or a third party's full name. Name the password-manager item instead. Prices, rates, rules and dates are not identifiers.
- **A committed secret stays in git history forever.** Check before every commit. Keys, tokens and `.env` files belong in a password manager. `scripts/lint.py` is a net, not the check.
- **Records are appended. Rules, statuses and decisions are asked.** You have standing permission to add a record: a log or diary entry. To change what a record means, get the owner's explicit yes in this conversation first. That covers a status, a plan date, a rule and a decided policy. When the owner asks for a change ("change X", "add Y"), that is the yes. When the owner is talking or asking what something is, explain it and change nothing. If you think a rule is wrong, say so and stop.
- **Rule files: one machine at a time.** That means `ABOUT_ME.md`, `AGENTS.md`, `README.md`, `START_HERE.md` and `skills/`. A rule edit needs the owner's yes before it. The laptop sync holds unapproved rule files back (`scripts/AGENTS.md`).
- **Facts live in one place. Skills point at them and never copy them.**
- **Check the machine before you claim what is on it.** Run the command, read the output, then speak. If you cannot, say "I have not verified this". Never invent a model name, flag, path or package. Say "I do not know".
- **The owner runs the dangerous commands.** Before a root command that changes a server, state the command and why, then wait for the owner's yes. Never force-push, rewrite history, run `git reset --hard`, `git clean -f` or `rm -rf`, or touch server users, sshd, the firewall or a VPN. Give the owner those commands to run. `scripts/hooks/guard.py` blocks most of them. A stopped rebase has lost nothing: read `git status`.
- **Never load everything at once.** Sample first, then stream one item at a time under `systemd-run --user --scope -p MemoryMax=1G nice -n 19 <command>` on Linux.
- **Agent memory holds impressions, not records.** Finished work and session history go in `diary/` or an area log.

## Which file wins

When two sources disagree, the higher one wins:

0. `DEADLINES.md`: every dated obligation. Its dates appear in no other file. Link to it.
1. Your fact sheets (add them here as you create them, for example a "Standing facts" file).
2. `ABOUT_ME.md`: the person.
3. Everything else.

An AI's inference, such as a memory store, never outranks a file.

## How to work with the owner

`skills/working-terms/SKILL.md` holds the terms: honest odds, the answer first, plain English, the owner's time before a task.

## Skills

Each workflow is a `skills/<name>/SKILL.md`. Read the whole file before you start one. In Claude Code, start a skill with the Skill tool. Other tools read the file. Do not improvise a workflow that a skill covers.

| Skill | Use when |
|---|---|
| `working-terms` | Every session, before the first answer |
| `record` | Something in the system changed (area log), or something happened to the owner (diary) |
| `focus-guard` | The owner feels stuck, avoids the work, or proposes new tools while a deadline is close |
| `repo-sync` | "Sync", a missing push, or a "divan sync stopped" alert |
| `delegate` | Search, research or audit work for a subagent |

## Done means

`make check` passes. The record is written (skill `record`). A mistake that could repeat is written as a rule where it belongs (skill `record`, "Promote the lesson"). The change is committed with a real message and pushed. If you worked in a worktree, push to main, then run `make sync` in the main folder. `make help` lists the commands.

## Where things are

| Path | What |
|---|---|
| `ABOUT_ME.md`, `DEADLINES.md` | Who the owner is. Every dated obligation |
| `logs/` | The area logs: what changed in the system and why |
| `diary/` | One file per month: what the owner did and how it went |
| `skills/` | The workflows. Design rules: `skills/README.md` |
| `scripts/` | The tools. Sync, and which machine writes which file: `scripts/AGENTS.md` |
| `private/` | Personal documents. Never in git |

`scripts/` has a nested `AGENTS.md`. Before you edit work in it, open that file with the Read tool.

All paths are relative to the repo root. Never hardcode the folder name.
