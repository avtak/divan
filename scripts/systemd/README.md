# systemd user units for `scripts/divan-sync`

Each unit file holds the placeholder `@REPO@`. Replace it with the clone's absolute path.

## Laptop: a timer every 5 minutes

`setup.sh --sync` installs these two units with the path filled in. By hand, without sudo:

```bash
mkdir -p ~/.config/systemd/user ~/.local/state
for f in scripts/systemd/laptop/divan-sync.*; do
  sed "s|@REPO@|$PWD|g" "$f" > ~/.config/systemd/user/"$(basename "$f")"
done
systemctl --user daemon-reload && systemctl --user enable --now divan-sync.timer
```

The timer commits a changed file after it sat untouched for 10 minutes (`DIVAN_SETTLE=600`). It holds rule files back, and it pauses while an agent session works in the repo. Log: `~/.local/state/divan-sync.log`.

## Server (optional): a watcher plus a 15-minute pull

Use this only if an agent on a server writes the same repo. Run it as the user that owns the clone:

```bash
mkdir -p ~/.config/systemd/user
for f in scripts/systemd/server/divan-*; do
  sed "s|@REPO@|$PWD|g" "$f" > ~/.config/systemd/user/"$(basename "$f")"
done
loginctl enable-linger "$USER"          # needs root once; keeps user units running after logout
systemctl --user daemon-reload && systemctl --user enable --now divan-watch.service divan-sync.timer
```

`divan-sync.service` has no `[Install]` section on purpose: the timer starts it. The watcher needs `inotify-tools`. The server never holds rule files (`DIVAN_SETTLE=0`), so the server agent must ask the owner before a rule edit.
