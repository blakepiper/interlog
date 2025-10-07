# InterLog

**Free, open-source interaction logging tool for UX researchers.**

InterLog captures keyboard and mouse interactions with precise timestamps, designed to sync perfectly with your screen recordings. No expensive commercial software needed—just Python and your favorite screen recorder.

## What You Get

- **Comprehensive interaction capture**: Mouse (moves, clicks, scrolls, drags) and keyboard events
- **Privacy-first**: Optional privacy mode that logs key events without recording which keys
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Structured output**: CSV files ready for analysis in Excel, R, Python, or your tool of choice
- **Rich analytics**: Automatic statistics including rage clicks, pause detection, interaction intensity
- **Video sync**: Timestamps align with your OBS/QuickTime/etc. recordings

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/interlog.git
cd interlog

# Install dependencies
pip install -r requirements.txt
```

**That's it!** No complex setup, no configuration files, no accounts.

### Basic Usage

```bash
# Start recording interactions
python interlog.py

# Press Ctrl+C when done
```

This creates two files:
- `YYYYMMDD_HHMMSS_events.csv` - All interaction events with timestamps
- `YYYYMMDD_HHMMSS_metadata.json` - Session metadata

### Generate Statistics

```bash
# Analyze the recorded session
python analyzer.py YYYYMMDD_HHMMSS_events.csv
```

This generates:
- `YYYYMMDD_HHMMSS_summary.csv` - Session statistics (clicks/min, rage clicks, etc.)
- `YYYYMMDD_HHMMSS_intensity.csv` - Time-bucketed activity data

## Example Workflow

1. **Start your screen recording** (OBS, QuickTime, etc.)
2. **Start InterLog**: `python interlog.py --name user_study_p1`
3. **Conduct your user research session**
4. **Stop InterLog** (Ctrl+C)
5. **Stop your screen recording**
6. **Analyze the data**: `python analyzer.py user_study_p1_events.csv`
7. **Review the video** with timestamps from the CSV to find interesting moments

## Advanced Options

### Privacy Mode

For sensitive research where you don't need to know which keys were pressed:

```bash
python interlog.py --privacy
```

This logs keyboard activity without recording the actual keys pressed.

### Custom Session Names

```bash
python interlog.py --name participant_05_task_checkout
```

### Custom Output Directory

```bash
python interlog.py --output ./sessions/study_2024/
```

### Full Command Options

**InterLog (recording):**
```bash
python interlog.py [OPTIONS]

Options:
  -o, --output DIR     Output directory (default: current directory)
  -n, --name NAME      Session name (default: timestamp)
  -p, --privacy        Enable privacy mode
  -h, --help          Show help message
```

**Analyzer:**
```bash
python analyzer.py EVENTS_FILE [OPTIONS]

Options:
  -o, --output DIR         Output directory for analysis files
  -b, --bucket-size SECS   Time bucket size for intensity (default: 5.0)
  --json                   Also output summary as JSON
  -h, --help              Show help message
```

## Output Files

### Events CSV (`*_events.csv`)

Contains every interaction event:

| timestamp | event_type | x | y | button | key | dx | dy |
|-----------|------------|---|---|--------|-----|----|----|
| 0.125 | mouse_move | 450 | 320 | | | | |
| 0.891 | mouse_down | 450 | 320 | Button.left | | | |
| 1.023 | mouse_up | 450 | 320 | Button.left | | | |
| 1.445 | key_press | | | | a | | |
| 2.108 | scroll | 500 | 400 | | | 0 | -3 |

### Summary CSV (`*_summary.csv`)

Key statistics about the session:

| metric | value |
|--------|-------|
| session_duration_seconds | 127.45 |
| total_clicks | 45 |
| clicks_per_minute | 21.2 |
| rage_clicks_detected | 2 |
| longest_pause_seconds | 8.34 |
| ... | ... |

### Intensity CSV (`*_intensity.csv`)

Time-bucketed interaction counts (great for finding "hot spots" in videos):

| time_start | time_end | total_interactions | clicks | scrolls | keypresses |
|------------|----------|-------------------|--------|---------|------------|
| 0.0 | 5.0 | 12 | 3 | 2 | 7 |
| 5.0 | 10.0 | 8 | 1 | 4 | 3 |
| 10.0 | 15.0 | 23 | 8 | 5 | 10 |

### Metadata JSON (`*_metadata.json`)

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
- `pynput` library (automatically installed via requirements.txt)

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

- Found a bug? [Open an issue](https://github.com/yourusername/interlog/issues)
- Have a feature idea? [Start a discussion](https://github.com/yourusername/interlog/discussions)
- Want to contribute code? Fork and submit a PR!

## License

MIT License - use it for whatever you need!

## Use Cases

- **Usability testing**: Identify pain points and confusion
- **A/B testing**: Compare interaction patterns between designs
- **User research**: Quantify behavior alongside qualitative observations
- **Academic research**: Publish reproducible interaction metrics
- **UX portfolios**: Back up design decisions with real data

## Roadmap

Current version is MVP. Future enhancements could include:

- [ ] HTML/JS viewer for syncing logs with video playback
- [ ] Executable binaries (no Python installation needed)
- [ ] PyPI package for easy installation
- [ ] Heatmap generation from mouse movements
- [ ] Support for multi-monitor setups
- [ ] Export to more formats (JSON, Parquet, SQLite)
- [ ] Real-time dashboard during recording

## FAQ

**Q: Does this record my screen?**
A: No! Use your favorite screen recorder. InterLog only captures mouse/keyboard events.

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
- Love for the UX research community

---

**Made for researchers who care about users**

*InterLog is free and open-source. If it helps your research, consider starring it on GitHub!*
