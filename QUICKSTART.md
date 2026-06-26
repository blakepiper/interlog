# InterLog Quick Start

## Installation

```bash
git clone https://github.com/blakepiper/interlog.git
cd interlog
pip install .

# Optional: add heatmap support (matplotlib, numpy, Pillow)
pip install ".[heatmap]"

# Confirm everything is working
interlog doctor
```

## Your First Session

```bash
# 1. Start recording
interlog record --name my_session

# 2. Use the computer normally (mouse, keyboard, scroll)

# 3. Press Ctrl+C to stop — session is saved automatically

# 4. Analyze
interlog analyze interlog-data/my_session

# 5. Generate a heatmap
interlog heatmap interlog-data/my_session
```

Everything goes into `interlog-data/my_session/` — nothing scattered in your
working directory.

## All-in-one: screen + interactions + synced viewer

If you have [ffmpeg](https://ffmpeg.org/download.html) installed:

```bash
# Record screen and interactions together
interlog record --screen --name p01

# Open the synced viewer — recording loads automatically, seeking works
interlog view interlog-data/p01 --serve
```

In the viewer, click a hot spot or anywhere on the intensity timeline to jump
the video to that moment. Press Ctrl+C in the terminal to stop the server.

If the video and log are slightly out of sync, nudge the **Sync offset** field
until a known click lines up.

## Browse all sessions

```bash
interlog list
```

Shows a table of all sessions: name, date, duration, event count, whether a
screen recording exists, whether analysis has been run, and privacy status.

## Common Workflows

### HCI research session (bring your own recorder)

```bash
# 1. Start your screen recorder (OBS, QuickTime, etc.)

# 2. Record interactions
interlog record --name participant_01_checkout

# 3. Stop InterLog (Ctrl+C), then stop your recorder

# 4. Analyze
interlog analyze interlog-data/participant_01_checkout

# 5. Generate heatmap
interlog heatmap interlog-data/participant_01_checkout

# 6. Open viewer and align video with the sync-offset field
interlog view interlog-data/participant_01_checkout
```

### Privacy mode

```bash
# Logs key events without recording which keys were pressed
interlog record --privacy --name sensitive_session
```

Typed-text analysis and keyboard identity metrics are automatically suppressed.

### Custom output directory

```bash
interlog record --output ./study_2024/sessions --name p01
interlog analyze ./study_2024/sessions/p01
interlog heatmap ./study_2024/sessions/p01
```

## What to Look For

**Rage clicks** — 3+ rapid clicks in the same spot. Usually means a broken
button, unresponsive UI, or genuine confusion. The heatmap marks them in red.

**Struggle score** — composite of rage/dead/double clicks and hesitations,
normalized per minute. Higher = more friction.

**High interaction density** — bursts of activity in `intensity.csv` (or the
terminal sparkline) tell you exactly where to scrub in a long recording.

**Long pauses** — gaps between actions indicate reading, decisions, or
confusion. Check `longest_pause_seconds` in the summary.

## Tips

1. **Use `--name`** — descriptive session names make `interlog list` much more useful
2. **`--serve` for screen recordings** — the file-picker fallback works but `--serve` is smoother
3. **Heatmap `--sigma`** — increase for sparser sessions, decrease for dense ones
4. **`--no-text`** — skip transcript reconstruction if you don't need it (faster)
5. **Privacy mode** — use it for any session where key identities aren't relevant to your research question

## Troubleshooting

**`interlog heatmap` fails with ImportError**
```bash
pip install ".[heatmap]"
```

**"Permission denied" on macOS**
- System Settings → Privacy & Security → Accessibility → add your terminal

**No events captured on Linux**
- Run `interlog doctor --live` to confirm input capture works
- Wayland: support depends on compositor; X11 works without extra steps

**Video and log out of sync**
- Use the **Sync offset** field in `interlog view`
- Positive offset: video is ahead of the log
- Negative offset: log is ahead of the video

## Next Steps

- See [README.md](README.md) for full documentation and command reference
- Browse [examples/](examples/) for sample output files
- Run `interlog <command> --help` for all options
