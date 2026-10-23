---
name: record
description: "Writes the session's record in the right place: a change to the system in the area's *_log.md, what happened to the owner (their day, their mood) in diary/<YYYY-MM>.md. Use at the end of any session that changed files or where something happened to the owner, and when they say 'log it', 'update the log', 'note that down', 'add to diary', 'skipped it today', 'wasted the day', 'felt stuck'."
---

# record

**Model-invoked.** Write it at the end of any session that changed files or where something happened to the owner, without being asked, and say so in one line. Standing permission covers both outputs; do not ask.

## Which output

| What happened | Where it goes |
|---|---|
| Something **changed in the system** | **A. The area log.** `logs/system_log.md` for the machinery (hooks, lint, sync, skills, the plan). Each life area you add gets its own `<area>_log.md` |
| Something **happened to the owner**: what they did, their mood and feelings, a skipped session, a day that went badly or well | **B. The diary.** `diary/<YYYY-MM>.md` |

A session that changed the system **and** had a day worth recording writes both. Never put a human episode ("skipped the gym, felt flat") in a log, and never put a file path or a config in the diary.

## A. A change to the system: the area log

One entry goes in one log, where its centre of gravity is. Never duplicate it across logs.

```markdown
- **DD.MM.YYYY**: **Short bold headline.** Then the detail in plain sentences.
```

- Newest at the top of `## Log`.
- Routine work: the headline alone, or one or two sentences. A large change: the headline carries the conclusion, the body the reasoning.
- **Length: a headline and at most three sentences, under 800 characters** (lint check 15 warns). The full detail goes in the commit message, which `git log` keeps.
- Every entry carries four things: **the date** (`DD.MM.YYYY`), **what changed** (files, flags, numbers), **why** (what the diff cannot show), **what is owed next**, if anything.
- Correcting an earlier entry: say so, and say who was wrong.
- Leave out: general context, a tool's generic purpose, headings on short entries, hedging, empty adjectives ("significant improvement"). Give the number or the fact.

**Promote the lesson.** When a session finds a mistake that would repeat, log it, then move the rule where it belongs:
- Agent behaviour everywhere: `AGENTS.md` "Hard rules"
- Answer shape and stops: `skills/working-terms/SKILL.md`
- A workflow: that workflow's `SKILL.md`
- A fact or decision: the file that owns it

State the rule in one sentence. The story stays in the log.

Then add a row to `logs/lessons.csv`: where the lesson lives, an exact anchor phrase, the log entry, the model in use, and in `expect` what it should stop and how to see that. A new code check also adds one passing and one failing case to its `--probe`. Why: lessons outlive their failures, and only a recorded model and prediction let a later replay (`make replay`) retire them.

**Coupled files.** `make check` names the file and line when a skill, a skill count or a script is missing from the docs that list them. It cannot judge whether a description is still true: read each doc that describes what you changed (`README.md`, `skills/README.md`, `scripts/AGENTS.md`) and fix it in the same commit. In Claude Code, `scripts/hooks/coupled.py` names those docs right after the edit.

## B. Something happened to the owner: the diary

If the owner describes their day, record it in their words. A diary the owner writes is canon about the owner: it stops agents guessing habits from inferred memory.

**Two rules that do not bend:**

1. **Never tidy an entry.** If the owner says "wasted the whole day, felt stuck", write that. Never soften it to "limited progress" or "a slower day": a tidied diary is useless. The rule binds agents, not the owner: the owner may edit or delete entries. Agents append new entries and never edit old ones.
2. **Never invent a feeling.** Write what the owner said, in their register. Never infer burnout, low motivation or avoidance unless the owner said it.

**What belongs here:**
- What the owner did: sessions done, skipped or cut short, shifts, errands, people, rest.
- What they actually worked on against what was planned.
- Their mood and state in their words: stuck, energised, tired.

**Format.** One file per month, `diary/<YYYY-MM>.md`, newest entry at the top:

```markdown
## DD.MM.YYYY

Free text or short bullets in the owner's words. Bold leads when there are several strands:
**Mood.** Tired after the shift, but calm.
**Study.** Session completed.
```

**Patterns.** At the bottom of each month, `## Patterns: <Month> <YYYY>`. Only a pattern visible across several dated entries, citing those dates. Never a mood summary. Propose it to the owner; insert it only with their yes.
