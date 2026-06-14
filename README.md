# InterLog

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

## Why InterLog?

Screen recorders (and OBS input-overlay plugins) show you *what happened*.
InterLog tells you *where it matters and by how much*.

- **Data, not just pixels.** Every interaction becomes a row in a CSV you can
  query, aggregate, and compare — across tasks, conditions, and participants.
- **A navigational index into your video.** Don't scrub a 40-minute session;
  jump straight to the rage-click bursts and high-intensity "hot spots" via a
  synced timeline (`interlog view`).
- **Quantified behavior.** Clicks/min, action rate, pauses, scroll distance,
  and rage-click detection out of the box (`interlog analyze`).
- **Works anywhere on the desktop.** Native apps, prototypes, games, kiosks —
  not just websites (where Hotjar/Clarity stop).
- **Private by design.** Everything stays local. Optional privacy mode logs
  *that* keys were pressed without recording *which* keys.

Best fit: **analyzing longer or repeated HCI/usability sessions** where you need
evidence and triage, not a one-off clip you'd just watch.

## What You Get

- **Comprehensive interaction capture**: Mouse (moves, clicks, scrolls, drags) and keyboard events
- **Privacy-first**: Optional privacy mode that logs key events without recording which keys
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Structured output**: CSV files ready for analysis in Excel, R, Python, or your tool of choice
- **Rich analytics**: Automatic statistics including rage clicks, pause detection, interaction intensity
- **Video sync**: Built-in screen recording (`--screen`), or align timestamps with your own OBS/QuickTime/etc. recordings

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/blakepiper/interlog.git
cd interlog

# Install the package (provides the `interlog` command)
pip install .
```

This installs a single `interlog` command on your PATH. **That's it!** No
configuration files, no accounts.

> Developing on InterLog? Use an editable install: `pip install -e .`

Verify your environment any time with:

```bash
interlog doctor          # check Python + pynput (+ ffmpeg, for --screen)
interlog doctor --live   # confirm input capture works (press ESC to stop)
```

### Basic Usage

```bash
# Start recording interactions
interlog record

# Press Ctrl+C when done
```

### Record the screen too (all in one)

If you have [ffmpeg](https://ffmpeg.org/download.html) installed, InterLog can
start a screen recording and the interaction log together, already aligned in
time:

```bash
interlog record --screen --name user_study_p1
# Press Ctrl+C when done -> writes the .mp4, the events CSV, and metadata
```

Then open the **synced viewer** to scrub straight to the interesting moments:

```bash
interlog view interlog-data/user_study_p1
```

This opens a local HTML page with an interaction-intensity timeline and
rage-click markers. Load your recording (it stays on your machine — nothing is
uploaded), and clicking a "hot spot" jumps the video to that moment. A sync
offset nudge is provided in case the video and log need fine alignment.

Each session is saved in its own subfolder under `interlog-data/`:

```
interlog-data/
└── 20240115_143000/          # session folder (timestamp, or your --name)
    ├── events.csv            # all interaction events with timestamps
    └── metadata.json         # session metadata
```

So nothing is dumped loose in your working directory — everything is contained
and self-describing. Use `-o DIR` to put the `interlog-data` root somewhere else.

### Generate Statistics

```bash
# Point at the session folder (or its events.csv)
interlog analyze interlog-data/20240115_143000
```

This adds to the same session folder:
- `summary.csv` - Session statistics (clicks/min, rage clicks, etc.)
- `intensity.csv` - Time-bucketed activity data

`interlog view interlog-data/20240115_143000` likewise writes `viewer.html` there.

#### Typed-text analysis

`interlog analyze` reconstructs the typed text from the keystroke log and runs
local, dependency-free lexical analysis (word/char counts, top keywords),
writing `transcript.txt` and `text.json`. It runs **by default**, entirely on
your machine (no cloud). Pass `--no-text` to skip it, and it's automatically
skipped for privacy-mode sessions (where key identities weren't recorded).

Note: keystrokes are captured globally across apps and caret moves aren't
tracked, so the transcript is approximate — treat it as a reviewable artifact.

## Example Workflow

Simplest path — let InterLog record the screen for you:

1. **Start InterLog with screen capture**: `interlog record --screen --name user_study_p1`
2. **Conduct your user research session**
3. **Stop InterLog** (Ctrl+C) — writes the MP4, events CSV, and metadata
4. **Open the synced viewer**: `interlog view interlog-data/user_study_p1`

Or bring your own screen recorder:

1. **Start your screen recording** (OBS, QuickTime, etc.)
2. **Start InterLog**: `interlog record --name user_study_p1`
3. **Conduct your user research session**
4. **Stop InterLog** (Ctrl+C)
5. **Stop your screen recording**
6. **Analyze the data**: `interlog analyze interlog-data/user_study_p1`
7. **Review the video** with timestamps from the CSV to find interesting moments

## Advanced Options

### Privacy Mode

For sensitive research where you don't need to know which keys were pressed:

```bash
interlog record --privacy
```

This logs keyboard activity without recording the actual keys pressed.

### Custom Session Names

```bash
interlog record --name participant_05_task_checkout
```

### Custom Output Directory

```bash
interlog record --output ./sessions/study_2024/
```

### Full Command Options

InterLog is a single command with subcommands: `record`, `analyze`, `view`, and
`doctor`. Run `interlog <command> --help` for details.

**Recording:**
```bash
interlog record [OPTIONS]

Options:
  -o, --output DIR     Output directory (default: current directory)
  -n, --name NAME      Session name (default: timestamp)
  -p, --privacy        Enable privacy mode
  --screen             Also record the primary screen (requires ffmpeg)
  --fps N              Screen capture frame rate with --screen (default: 15)
  -h, --help           Show help message
```

**Viewing (sync log with recording):**
```bash
interlog view EVENTS_FILE [OPTIONS]

Options:
  -o, --output PATH        Output .html file or directory
  -b, --bucket-size SECS   Timeline bucket size (default: 2.0)
  --no-open                Generate the HTML without opening a browser
  -h, --help               Show help message
```

**Analyzing:**
```bash
interlog analyze EVENTS_FILE [OPTIONS]

Options:
  -o, --output DIR         Output directory for analysis files
  -b, --bucket-size SECS   Time bucket size for intensity (default: 5.0)
  --json                   Also output summary as JSON
  --no-text                Skip typed-text reconstruction (on by default)
  -h, --help               Show help message
```

**Diagnostics:**
```bash
interlog doctor [--live]

  --live   Run a live input-capture test (press ESC to finish)
```

## Output Files

### Events CSV (`events.csv`)

Contains every interaction event:

| timestamp | event_type | x | y | button | key | dx | dy |
|-----------|------------|---|---|--------|-----|----|----|
| 0.125 | mouse_move | 450 | 320 | | | | |
| 0.891 | mouse_down | 450 | 320 | Button.left | | | |
| 1.023 | mouse_up | 450 | 320 | Button.left | | | |
| 1.445 | key_press | | | | a | | |
| 2.108 | scroll | 500 | 400 | | | 0 | -3 |

### Summary CSV (`summary.csv`)

Key statistics about the session:

| metric | value |
|--------|-------|
| session_duration_seconds | 127.45 |
| total_clicks | 45 |
| clicks_per_minute | 21.2 |
| rage_clicks_detected | 2 |
| dead_clicks | 3 |
| double_clicks | 5 |
| hesitations | 4 |
| total_mouse_distance_px | 18430 |
| mean_pointer_speed_px_s | 612 |
| time_to_first_interaction_seconds | 1.83 |
| typing_chars_per_minute | 142 |
| correction_rate | 0.08 |
| struggle_score | 6.4 |
| ... | ... |

The summary spans several families: **event counts & rates**, **pointer**
(distance, speed, idle/active, time-to-first-action), **timing** (longest/median
pause, hesitations), **click quality** (rage/dead/double clicks), **keyboard
dynamics** (typing speed, inter-key interval, correction rate — omitted under
privacy mode), and a composite **struggle score** for quick triage.

### Intensity CSV (`intensity.csv`)

Time-bucketed interaction counts (great for finding "hot spots" in videos):

| time_start | time_end | total_interactions | clicks | scrolls | keypresses |
|------------|----------|-------------------|--------|---------|------------|
| 0.0 | 5.0 | 12 | 3 | 2 | 7 |
| 5.0 | 10.0 | 8 | 1 | 4 | 3 |
| 10.0 | 15.0 | 23 | 8 | 5 | 10 |

### Metadata JSON (`metadata.json`)

Session information:

```json
{
  "session_name": "user_study_p1",
  "start_time": "2024-01-15T14:30:00",
  "end_time": "2024-01-15T14:32:07",
  "privacy_mode": false,
  "duration_seconds": 127.45,
  "total_events": 2341
}
```

## What the Statistics Tell You

### Rage Clicks
3+ rapid clicks in the same area—often indicates confusion, broken UI elements, or unresponsive feedback.

### Clicks Per Minute
Higher rates might indicate scanning behavior or uncertainty. Lower rates might mean focused reading or decision-making.

### Longest Pause
Long pauses can indicate moments of confusion, complex decisions, or simply reading dense content.

### Interaction Intensity
Time-bucketed data helps you quickly scrub to the most active moments in your video recording.

## Technical Details

### Requirements
- Python 3.7+
- `pynput` library (installed automatically with the package)
- `ffmpeg` (optional) — only needed for `interlog record --screen`

### Platform Notes

**macOS**: You may need to grant accessibility permissions:
- System Preferences → Security & Privacy → Privacy → Accessibility
- Add Terminal (or your Python IDE)

**Linux**: Some distributions may require additional packages for `pynput`:
```bash
sudo apt-get install python3-xlib  # Debian/Ubuntu
```

**Windows**: Should work out of the box on Windows 7+

## Contributing

This is a free tool for researchers—contributions welcome!

- Found a bug? [Open an issue](https://github.com/blakepiper/interlog/issues)
- Have a feature idea? [Start a discussion](https://github.com/blakepiper/interlog/discussions)
- Want to contribute code? Fork and submit a PR!

## License & Citation

InterLog is free and open-source under the [MIT License](LICENSE) — use, modify,
distribute, and sell it as you see fit.

The one ask: if you use InterLog in published research, **please cite it** — see
[CITATION.cff](CITATION.cff).

## Use Cases

- **Usability testing**: Identify pain points and confusion
- **A/B testing**: Compare interaction patterns between designs
- **User research**: Quantify behavior alongside qualitative observations
- **Academic research**: Publish reproducible interaction metrics
- **Design portfolios**: Back up design decisions with real data

## Roadmap

Current version is MVP. Future enhancements could include:

- [x] HTML/JS viewer for syncing logs with video playback (`interlog view`)
- [x] Built-in screen recording via ffmpeg (`interlog record --screen`)
- [ ] Frame-perfect auto-sync (current auto-offset is best-effort + manual nudge)
- [ ] Executable binaries (no Python installation needed)
- [ ] PyPI package for easy installation
- [ ] Heatmap generation from mouse movements
- [ ] Support for multi-monitor setups
- [ ] Export to more formats (JSON, Parquet, SQLite)
- [ ] Real-time dashboard during recording

## FAQ

**Q: Does this record my screen?**
A: Optionally, yes. By default InterLog only captures mouse/keyboard events, but
`interlog record --screen` will also capture the primary screen to an MP4 (via
[ffmpeg](https://ffmpeg.org/download.html)), already time-aligned with the
interaction log so you can scrub it in `interlog view`. You can still use your
own screen recorder (OBS, QuickTime, etc.) instead and sync against the
timestamps — `--screen` is just the all-in-one option.

**Q: Is my data sent anywhere?**
A: No. Everything stays on your local machine. No network access, no cloud, no telemetry.

**Q: Can I use this for remote research?**
A: Yes! Just send participants the script and have them screen-share while running it, or have them run it locally and send you the CSV files afterward.

**Q: What about mobile/touch interactions?**
A: Not yet supported. This version focuses on desktop interactions only.

**Q: How accurate are the timestamps?**
A: Very accurate—typically within milliseconds. Perfect for syncing with 30fps or 60fps video.

## Acknowledgments

Built with:
- [pynput](https://github.com/moses-palmer/pynput) - Cross-platform input monitoring
- Love for the HCI research community

---

**Made for HCI researchers who care about users**

*InterLog is free and open-source (MIT). If it helps your research, please cite it and consider starring it on GitHub!*
