---
name: focus-guard
description: "Stops the agent before it helps the owner avoid the work that moves their life: the priorities in ABOUT_ME.md and the dated obligations in DEADLINES.md. Use when the owner proposes setting up a local model, trying a new tool, cloning a repo or tuning the machine while a deadline is close, when they say they are stuck or ask 'what should we do next', or when the session-start [FOCUS-GUARD] alert is present."
---

# focus-guard

Under stress or deadline pressure, many builders escape into building: new tools, new models, infrastructure. The work that moves the owner's life is the priorities in `ABOUT_ME.md` and the dates in `DEADLINES.md`. `scripts/hooks/context.py` puts a `[FOCUS-GUARD]` alert into the session start when an open deadline is 7 days away or less.

## When it fires

1. The owner asks to install, research, benchmark or explore a tool, library, model or repo that meets no close dated obligation and serves no priority in `ABOUT_ME.md`.
2. The owner says they are stuck, unmotivated or overwhelmed, or asks "what should we do next?".
3. The `[FOCUS-GUARD]` alert is present and the owner is working on tooling or infrastructure that is not essential.

## What to do

1. **Stop before acting.** Do not run the research, fetch the repo or benchmark the model.
2. **Name it.** In your own words, without hostility and without softening: what this request is, the nearest deadline it displaces (from the alert or `DEADLINES.md`, with days left), and that this work does not move it.
3. **One sentence of empathy, no enabling.** Why the pull is real (building feels like progress), then point back at the deadline.
4. **One micro-step under 3 minutes.** Never "work on it for 2 hours". Name the first physical action: open one file, write one sentence, send one message. Take it from the deadline's "Detail in" file.

When the micro-step is done, name the win and offer the next one.
