#!/usr/bin/env bash
# setup.sh: wire a fresh clone. Safe to run again.
#   ./setup.sh          hooks path, skill links, executable bits, then the lint
#   ./setup.sh --sync   also install the laptop sync timer (systemd user units, no sudo)
set -euo pipefail
cd "$(dirname "$0")"
REPO=$(pwd)

say() { printf '  %s\n' "$*"; }

# 1. python3, 3.10 or newer: the hooks and the lint use it, and nothing else.
command -v python3 >/dev/null || { echo "setup: python3 not found. Install it, then run setup.sh again." >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
  || { echo "setup: python3 is $(python3 -V 2>&1 | cut -d' ' -f2); divan needs 3.10 or newer." >&2; exit 1; }
say "python3 $(python3 -V 2>&1 | cut -d' ' -f2)"

# 2. git: the pre-commit hook runs the lint on every commit.
[ -d .git ] || git init -q -b main
git config core.hooksPath scripts/hooks
say "git hooks path: scripts/hooks"

# 3. One skills folder, linked where each runtime looks for it.
for d in .claude .agents; do
  mkdir -p "$d"
  if [ -L "$d/skills" ]; then
    :
  elif [ -e "$d/skills" ]; then
    say "WARNING: $d/skills exists and is not a link; leaving it. Move it away and run setup.sh again."
    continue
  else
    ln -s ../skills "$d/skills"
  fi
  say "$d/skills -> ../skills"
done

# 4. Executable bits (a zip download loses them).
chmod +x scripts/divan-sync scripts/divan-watch scripts/hooks/* scripts/*.py setup.sh

# 5. A CLAUDE.md makes Claude Code ignore AGENTS.md. The lint refuses one; say it early.
if [ -e CLAUDE.md ] || [ -e CLAUDE.local.md ]; then
  say "WARNING: CLAUDE.md found. Move its rules into AGENTS.md and delete it."
fi

# 6. Optional: the laptop sync timer.
if [ "${1:-}" = "--sync" ]; then
  command -v systemctl >/dev/null || { echo "setup: no systemctl; run scripts/divan-sync from cron or by hand (make sync)." >&2; exit 1; }
  git remote get-url origin >/dev/null 2>&1 || { echo "setup: no git remote 'origin'; add one before the sync timer." >&2; exit 1; }
  unit_dir="$HOME/.config/systemd/user"
  mkdir -p "$unit_dir" "$HOME/.local/state"
  for f in scripts/systemd/laptop/divan-sync.service scripts/systemd/laptop/divan-sync.timer; do
    sed "s|@REPO@|$REPO|g" "$f" > "$unit_dir/$(basename "$f")"
  done
  systemctl --user daemon-reload
  systemctl --user enable --now divan-sync.timer
  say "sync timer on: every 5 minutes, log ~/.local/state/divan-sync.log"
fi

# 7. The definition of done, once, so a broken clone shows now and not at the first commit.
echo
python3 scripts/lint.py || { echo "setup: lint failed; the lines above name file and line." >&2; exit 1; }
echo
echo "Next: open START_HERE.md."
