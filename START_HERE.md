# Start here

Six steps, about 30 minutes. Do them in order.

## 1. Make your copy private

This repo will hold your deadlines, your diary and your rules. Push it only to a **private** remote:

```bash
git remote set-url origin git@github.com:<you>/<your-private-repo>.git
```

Documents you never want in git (scans, contracts) go in `private/`. It is gitignored.

## 2. Fill the two templates

- **`ABOUT_ME.md`**: who you are, how you work, what you escape into. Keep it short. Every line must change how an agent works for you.
- **`DEADLINES.md`**: delete the example row, then add every dated obligation you have. One row each. The detail stays in the file the `Detail in` column names.

Then put your name on the **Owner** line of `AGENTS.md`.

## 3. Run setup

```bash
./setup.sh            # hooks path, skill links, lint
./setup.sh --sync     # optional: the laptop sync timer, every 5 minutes
```

The last line of the lint must read `lint: clean`.

## 4. First session checklist

Open the repo in Claude Code (or Antigravity, or Hermes) and check:

- [ ] The session starts with a block from `scripts/hooks/context.py` that lists your deadlines. If not: run `./setup.sh` again, and check that the runtime trusts this folder's hooks.
- [ ] Ask the agent "what are the working terms?". It answers from `skills/working-terms/SKILL.md`.
- [ ] Ask the agent to run `git reset --hard`. `scripts/hooks/guard.py` refuses it.
- [ ] Ask the agent to log the setup. A new entry appears at the top of `logs/system_log.md`.

## 5. Your first skill

Pick one workflow you repeat every week. Create `skills/<name>/SKILL.md`:

```markdown
---
name: <name>
description: "What it does, and the exact phrases or situations that should fire it. Not for <the near miss>."
---

# <name>

The steps, the stop where the agent waits for your yes, and pointers to the files that hold the facts.
```

Then add the skill to the tables in `AGENTS.md`, `README.md` and `skills/README.md`, and fix the counts in `skills/context-layers.svg`. Run `make check`. The lint names any doc you missed. Design rules: `skills/README.md`.

## 6. Your first lint failure

Make one on purpose, to see the net work. Copy a future date from `DEADLINES.md` into `ABOUT_ME.md` next to a word from the same row, then run `make check`. Check 1 refuses it and names the file and line. Put a pointer to `DEADLINES.md` there instead.

## Optional: a server

If an agent on a server writes the same repo (Hermes on Telegram, for example), clone the repo there and install the server units: `scripts/systemd/README.md`. The server never holds rule files back, so its agent must ask you before a rule edit. Keep `private/` off the server.

## Before you publish anything from your copy

Write your personal terms (names, handles, places, server names) to `~/.config/divan/sanitise-terms.txt`, one per line, and run `make sanitise`. It also finds e-mails, phone numbers, IPs and home paths without a list. Publish from a **fresh repo with fresh history**, never from your private one: git history keeps every file you ever committed.
