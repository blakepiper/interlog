# InterLog

[![CI](https://github.com/blakepiper/interlog/actions/workflows/ci.yml/badge.svg)](https://github.com/blakepiper/interlog/actions/workflows/ci.yml)

```
     ____      __            __
    /  _/___  / /____  _____/ /___  ____ _
    / // __ \/ __/ _ \/ ___/ / __ \/ __ `/
  _/ // / / / /_/  __/ /  / / /_/ / /_/ /
 /___/_/ /_/\__/\___/_/  /_/\____/\__, /
                                 /____/
   >>>>  capture . measure . replay  <<<<
```

**A lightweight, local interaction-logging tool for HCI research.**

InterLog captures timestamped keyboard and mouse activity, records the screen,
and turns a session into *structured, analyzable data* — not just a video you
have to watch end to end. It runs entirely on your machine: no cloud, no
accounts, no telemetry.

> [!WARNING]
> **InterLog captures input globally, across every application — not just the
> window under study.** While recording, it logs every key you press and every
> mouse action *system-wide*, including anything you type into other apps
> (passwords, messages, unrelated windows). By default `interlog analyze` also
> reconstructs the typed text to `transcript.txt`. Record only what you intend
> to, brief and get consent from participants, and use `--privacy` (and/or
> `--no-text`) for sensitive sessions. See [Privacy & consent](#privacy--consent).

## Why InterLog?

Screen recorders (and OBS input-overlay plugins) show you *what happened*.
InterLog tells you *where it matters and by how much*.

- **Data, not just pixels.** Every interaction becomes a row in a CSV you can
  query, aggregate, and compare — across tasks, conditions, and participants.
- **A navigational index into your video.** Don't scrub a 40-minute session;
  jump straight to the rage-click bursts and high-intensity "hot spots" via a
  synced timeline (`interlog view`).
- **Quantified behavior.** Clicks/min, action rate, pauses, scroll distance,
  pointer-path efficiency, and rage-click detection (`interlog analyze`) —
  descriptive measures, not invented composite scores.
- **Instant visual summary.** Generate a mouse-density heatmap overlaid on a
  captured screen frame — one PNG that tells the whole story (`interlog heatmap`).
- **Works anywhere on the desktop.** Native apps, prototypes, games, kiosks —
  not just websites (where Hotjar/Clarity stop).
- **Local, no telemetry.** Nothing leaves your machine — no cloud, no accounts.
  (Local storage is not the same as participant privacy: capture is global, so
  see [Privacy & consent](#privacy--consent).)

Best fit: **analyzing longer or repeated HCI/usability sessions** where you need
evidence and triage, not a one-off clip you'd just watch.

## What You Get

- **Comprehensive interaction capture** — Mouse (moves, clicks, scrolls, drags) and keyboard events
- **Rich terminal analytics** — Statistics, behavioral scores, and a Unicode activity sparkline
- **Mouse heatmap** — Density PNG with rage-click markers, overlaid on a screen grab
- **Synced viewer** — Local HTML timeline with intensity bars and hot spots; click to seek
- **HTML report** — Self-contained report with metric cards, SVG activity chart, and embedded heatmap
- **Batch aggregation** — `interlog analyze --batch` compares all sessions in a directory at once
- **Session browser** — `interlog list` shows all sessions with duration, event counts, and status
- **Privacy mode** — Optional mode that logs key *events* without recording which keys (see caveats below)
- **Cross-platform** — Works on Windows, macOS, and Linux

## Quick Start

### Installation

```bash
git clone https://github.com/blakepiper/interlog.git
cd interlog
pip install .
```

This installs a single `interlog` command on your PATH. No configuration files,
no accounts.

Add heatmap support (matplotlib, numpy, Pillow):

```bash
pip install ".[heatmap]"
```

Verify your environment any time:

```bash
interlog doctor          # checks Python, pynput, ffmpeg, and heatmap deps
interlog doctor --live   # confirm input capture works (press ESC to stop)
```

### Record a session

```bash
interlog record --name p01
# Press Ctrl+C when done
```

Each session is saved in its own subfolder:

```
interlog-data/
└── p01/
    ├── events.csv      # every interaction with timestamps
    └── metadata.json   # session info
```

Add `--screen` to also capture the primary display (requires
[ffmpeg](https://ffmpeg.org/download.html)):

```bash
interlog record --screen --name p01
```

### Analyze

```bash
interlog analyze interlog-data/p01
```

Prints a Rich statistics panel to the terminal and writes to the session folder:

- `summary.csv` — all metrics (clicks/min, rage clicks, path efficiency, …)
- `intensity.csv` — time-bucketed interaction counts
- `transcript.txt` + `text.json` — typed-text reconstruction and lexical stats
  (skipped automatically in privacy mode; pass `--no-text` to disable)

### Generate a heatmap

```bash
interlog heatmap interlog-data/p01
```

Writes `interlog-data/p01/heatmap.png` — a mouse-density overlay on a captured
screen frame, with rage clicks marked in red. Opens automatically; pass
`--no-open` to skip.

### View the synced timeline

```bash
# With a screen recording — auto-loads the video, seeking works immediately
interlog view interlog-data/p01 --serve

# Without a recording — open the HTML and load the video manually
interlog view interlog-data/p01
```

`--serve` starts a local HTTP server with Range-request support so the browser
can seek without downloading the whole file. Press Ctrl+C to stop the server.

### Browse all sessions

```bash
interlog list
```

Prints a table of all sessions: name, date, duration, event count, whether a
screen recording and analysis are present, and privacy status.

## Example Workflow

```bash
# 1. Record screen + interactions together
interlog record --screen --name p01

# 2. Analyze — statistics panel + output files
interlog analyze interlog-data/p01

# 3. Generate a heatmap PNG
interlog heatmap interlog-data/p01

# 4. Review with the synced viewer (video auto-loads, seeking works)
interlog view interlog-data/p01 --serve

# 5. Generate a shareable HTML report (embeds the heatmap)
interlog report interlog-data/p01

# After multiple sessions: cross-session summary table + aggregate.csv
interlog analyze --batch
```

Or bring your own screen recorder (OBS, QuickTime, etc.):

```bash
# Start your recorder, then:
interlog record --name p01
# Stop InterLog (Ctrl+C), then stop your recorder.
# Align the timestamps in the viewer's sync-offset field.
interlog view interlog-data/p01
```

## Commands

### `record` — Capture interactions

```
interlog record [OPTIONS]

  -n, --name NAME       Session name (default: timestamp)
  -o, --output DIR      Data directory root (default: ./interlog-data)
  -p, --privacy         Log key events without recording which keys
      --screen          Also record the primary screen via ffmpeg
      --fps N           Screen capture frame rate (default: 15)
      --monitor {primary,all}   Which display to capture (default: primary)
```

### `list` — Browse sessions

```
interlog list [OPTIONS]

  -d, --dir DIR         Directory to list (default: ./interlog-data)
```

### `analyze` — Compute statistics

```
interlog analyze SESSION [OPTIONS]
interlog analyze --batch [DIR]

  SESSION               Session folder or path to events.csv
      --batch [DIR]     Aggregate all sessions in DIR (default: ./interlog-data)
  -o, --output DIR      Output directory (default: session folder)
  -b, --bucket-size S   Time bucket size for intensity (default: 5.0)
      --json            Also emit summary as JSON
      --no-text         Skip typed-text reconstruction
```

`--batch` prints a cross-session table (duration, clicks/min, rage clicks, long
pauses, path efficiency) with a mean ± SD row, and writes `aggregate.csv` to the
data directory.

### `heatmap` — Generate a density PNG

```
interlog heatmap SESSION [OPTIONS]

  SESSION               Session folder or path to events.csv
  -o, --output FILE     Output PNG path (default: <session>/heatmap.png)
      --sigma N         Gaussian blur radius in pixels (default: 25)
      --frame-at PCT    Fraction into recording to grab background frame (default: 0.25)
      --no-open         Save without opening
```

Requires the `[heatmap]` optional dependencies (`pip install ".[heatmap]"`).

### `view` — Open the synced timeline viewer

```
interlog view SESSION [OPTIONS]

  SESSION               Session folder or path to events.csv
  -o, --output PATH     Output HTML file or directory
  -b, --bucket-size S   Timeline bucket size in seconds (default: 2.0)
      --serve           Serve over HTTP so the recording loads automatically
      --no-open         Generate HTML without opening a browser
```

### `report` — Generate a shareable HTML report

```
interlog report SESSION [OPTIONS]

  SESSION               Session folder or path to events.csv
  -o, --output FILE     Output HTML path (default: <session>/report.html)
  -b, --bucket-size S   Activity chart bucket size in seconds (default: 5.0)
      --no-open         Write the report without opening it in a browser
```

Generates a self-contained dark-themed HTML file with metric cards, an SVG
activity bar chart (with rage-click markers), and the heatmap embedded as
base64 (if `heatmap.png` exists in the session folder). No external assets —
everything is inline, so the file works offline and screenshots cleanly.

### `doctor` — Check your environment

```
interlog doctor [--live]

  --live   Run a live input-capture test (press ESC to finish)
```

## Output Files

### `events.csv`

Every interaction event, one row per event:

| timestamp | event_type | x | y | button | key | dx | dy |
|-----------|------------|---|---|--------|-----|----|----|
| 0.125 | mouse_move | 450 | 320 | | | | |
| 0.891 | mouse_down | 450 | 320 | Button.left | | | |
| 1.023 | mouse_up | 450 | 320 | Button.left | | | |
| 1.445 | key_press | | | | a | | |
| 2.108 | scroll | 500 | 400 | | | 0 | -3 |

### `summary.csv`

Key statistics about the session:

| metric | value |
|--------|-------|
| session_duration_seconds | 127.45 |
| total_clicks | 45 |
| clicks_per_minute | 21.2 |
| rage_clicks_detected | 2 |
| double_clicks | 5 |
| long_pauses | 4 |
| total_mouse_distance_px | 18430 |
| mean_pointer_speed_px_s | 612 |
| mean_path_efficiency | 0.74 |
| time_to_first_interaction_seconds | 1.83 |
| typing_chars_per_minute | 142 |
| correction_rate | 0.08 |
| … | … |

Covers: **event counts & rates**, **pointer** (distance, speed, path efficiency,
idle/active, time-to-first), **timing** (longest/median pause, long pauses),
**click signals** (rage-click bursts, double clicks), and **keyboard dynamics**
(typing speed, inter-key interval, correction rate — omitted in privacy mode).

These are descriptive measures; InterLog deliberately does **not** fold them into
a single "struggle"/"frustration" index. **Path efficiency is comparable across
machines** — it is a dimensionless ratio (display scaling cancels) measured on a
trajectory resampled to a fixed time base, so it does not depend on the mouse's
native sampling rate (assuming that rate is at least ~30 Hz, which all real mice
exceed). Raw pixel metrics (distance, speed) still scale with display scaling and
the sampling rate, so compare those only across sessions captured on the same
machine — see `dpi_scale` in `metadata.json`.

### `intensity.csv`

Time-bucketed interaction counts — great for finding "hot spots" in long videos:

| time_start | time_end | total_interactions | clicks | scrolls | keypresses |
|------------|----------|--------------------|--------|---------|------------|
| 0.0 | 5.0 | 12 | 3 | 2 | 7 |
| 5.0 | 10.0 | 8 | 1 | 4 | 3 |
| 10.0 | 15.0 | 23 | 8 | 5 | 10 |

### `heatmap.png`

A mouse-movement density map overlaid on a screen grab from the recording,
with normal clicks marked in white and rage clicks in red.
Generated by `interlog heatmap`; requires the `[heatmap]` optional extras.

### `report.html`

A self-contained HTML report with metric cards, an SVG activity timeline, and
the heatmap embedded as base64. Generated by `interlog report`; opens in any
browser and screenshots cleanly for sharing.

### `aggregate.csv`

Cross-session summary produced by `interlog analyze --batch`. One row per
session; columns match the key stats from `summary.csv`.

### `metadata.json`

```json
{
  "session_name": "p01",
  "start_time": "2024-01-15T14:30:00",
  "end_time": "2024-01-15T14:32:07",
  "privacy_mode": false,
  "duration_seconds": 127.45,
  "total_events": 2341
}
```

## What the Statistics Tell You

These are descriptive signals to help you *triage* a recording — where to look
first — not validated measures of any mental state. Interpret them alongside the
video, not in place of it.

**Rage-click bursts** — 3+ rapid clicks within a small area, counted once per
burst. An established UX-analytics signal often associated with a broken or
unresponsive target, or user confusion.

**Path efficiency** — straight-line distance between consecutive clicks divided
by the actual pointer path travelled (1.0 = perfectly direct). A standard
pointer-movement quality measure (MacKenzie, Kauppinen & Silfverberg, CHI 2001).
Measured on a trajectory resampled to a fixed time base, so it's a dimensionless
ratio that's comparable across machines and display scaling.

**Clicks per minute** — baseline for comparison across tasks and participants.
Sudden drops often accompany dense reading or decision-making.

**Longest / long pauses** — gaps between actions. `long_pauses` simply counts
inter-event gaps over 2s; it carries no cognitive interpretation on its own.

**Interaction intensity** — the time-bucketed sparkline (in the terminal and in
`intensity.csv`) tells you where to look first in a long recording.

## Privacy & consent

InterLog records keyboard and mouse input **globally**, using OS-level hooks. It
does not know or care which window has focus, so a session captures *everything*
typed and clicked while it runs — including content in applications unrelated to
your study (browsers, password managers, chat).

- By default, `interlog analyze` reconstructs the keystrokes into a readable
  `transcript.txt` and keyword list. Pass `--no-text` to skip that step.
- `record --privacy` logs that keys were pressed without recording *which*, and
  suppresses text reconstruction. It does **not** redact mouse coordinates,
  keystroke timing, or — importantly — the `--screen` recording, which captures
  whatever is on screen. Privacy mode and `--screen` together are contradictory
  for truly sensitive content.
- "Local-only" protects against *exfiltration*, not against capturing more than
  you intended. For studies with participants, obtain informed consent, follow
  your institution's ethics/IRB requirements, tell people the capture is
  system-wide, and have them close unrelated apps before recording.

## Technical Details

### Requirements

- Python 3.9+
- [`pynput`](https://github.com/moses-palmer/pynput) — installed automatically
- [`rich`](https://github.com/Textualize/rich) — installed automatically
- `ffmpeg` — optional, needed only for `interlog record --screen`
- `matplotlib`, `numpy`, `Pillow` — optional, needed only for `interlog heatmap`
  (`pip install ".[heatmap]"`)

### Platform Notes

**macOS** — Accessibility permission required:
System Settings → Privacy & Security → Accessibility → add your terminal.

**Linux X11** — No extra steps needed.

**Linux Wayland** — `interlog record --screen` uses xdg-desktop-portal + PipeWire
(installed automatically as a dependency). A native screen-picker dialog appears
once when you start recording; choose the monitor and recording begins. Requires
`xdg-desktop-portal` (ships with KDE Plasma and GNOME) and ffmpeg compiled with
PipeWire support (standard on Arch/Ubuntu 22.04+/Fedora 38+). Run
`interlog doctor` to verify.

**Windows** — Works out of the box on Windows 10+.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup
and guidelines.

- Bug? [Open an issue](https://github.com/blakepiper/interlog/issues)
- Feature idea? [Open an issue](https://github.com/blakepiper/interlog/issues)
- Code? Fork and submit a PR.

## License & Citation

InterLog is free and open-source under the [MIT License](LICENSE) — use,
modify, distribute, and sell it as you see fit.

The one ask: if you use InterLog in published research, **please cite it** —
see [CITATION.cff](CITATION.cff).

## Use Cases

- **Usability testing** — Identify pain points and confusion with quantified evidence
- **A/B testing** — Compare interaction patterns between design conditions
- **User research** — Supplement qualitative observations with behavioral metrics
- **Academic HCI** — Publish reproducible interaction data alongside your findings
- **Design portfolios** — Back up design decisions with real interaction data

## FAQ

**Q: Does this record my screen?**
A: Optionally. By default InterLog only captures mouse/keyboard events. Add
`--screen` to also record the display via ffmpeg, already time-aligned with the
interaction log. Then use `interlog view --serve` to open the synced viewer with
the recording loaded automatically. You can also use your own recorder (OBS,
QuickTime, etc.) and align timestamps using the viewer's sync-offset field.

**Q: Is my data sent anywhere?**
A: No. Everything stays on your local machine. No network access, no cloud, no telemetry.

**Q: Can I use this for remote research?**
A: Yes. Send participants the package and have them run `interlog record`
locally, then share the session folder with you afterward.

**Q: What about mobile/touch interactions?**
A: Not currently supported. InterLog focuses on desktop (mouse + keyboard).

**Q: How accurate are the timestamps?**
A: Sub-millisecond resolution from a monotonic clock. Accurate enough to sync
with 60fps video.

## Acknowledgments

Built with [pynput](https://github.com/moses-palmer/pynput) for cross-platform
input monitoring and [Rich](https://github.com/Textualize/rich) for terminal output.

---

**Made for HCI researchers who care about users.**

*MIT licensed — if it helps your research, please cite it and consider starring the repo.*
