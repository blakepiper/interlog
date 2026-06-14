# InterLog Quick Start Guide

## Installation (30 seconds)

```bash
# 1. Install the package (provides the `interlog` command)
pip install .

# 2. (optional) Confirm everything is set up
interlog doctor

# 3. You're ready!
```

## Your First Session (2 minutes)

### Step 1: Start Recording

```bash
interlog record
```

You'll see:
```
Session:  20240115_143000
Privacy:  DISABLED
Output:   /current/directory

Recording... Press Ctrl+C to stop.
```

### Step 2: Interact

Use your computer normally:
- Move the mouse
- Click things
- Type
- Scroll

### Step 3: Stop Recording

Press `Ctrl+C`

You'll see:
```
Session saved!
Events:   interlog-data/20240115_143000/events.csv
Metadata: interlog-data/20240115_143000/metadata.json

Total events captured: 2341
Duration: 45.67 seconds

Run the analyzer to generate statistics:
  interlog analyze interlog-data/20240115_143000
```

### Step 4: Analyze

```bash
interlog analyze interlog-data/20240115_143000
```

You'll get (written into the same session folder):
- Console summary of all statistics
- `summary.csv` - Stats spreadsheet
- `intensity.csv` - Time-bucketed activity

## All-in-one: screen + interactions + viewer

If you have [ffmpeg](https://ffmpeg.org/download.html) installed:

```bash
# Records the primary screen AND interactions together (Ctrl+C to stop)
interlog record --screen --name p01

# Open the synced viewer, then load the recording it produced
interlog view interlog-data/p01
```

In the viewer, click a "hot spot" (or anywhere on the intensity timeline) to
jump the video to that moment. If the video and log drift, nudge the sync
offset field until a known click lines up.

## Common Use Cases

### HCI Research Session

```bash
# 1. Start screen recording (OBS, QuickTime, etc.)

# 2. Start InterLog with a descriptive name
interlog record --name participant_01_checkout_flow

# 3. Conduct research session

# 4. Stop InterLog (Ctrl+C)

# 5. Stop screen recording

# 6. Analyze
interlog analyze interlog-data/participant_01_checkout_flow
```

### Privacy Mode (Sensitive Data)

```bash
# Don't record which keys were pressed
interlog record --privacy --name sensitive_session
```

### Organize Multiple Sessions

```bash
# Create organized directory structure
mkdir -p research_study/sessions

# Record session
interlog record --output research_study/sessions --name p01

# Analyze later
interlog analyze research_study/sessions/p01
```

## What to Look For

### Rage Clicks
- **3+ rapid clicks in same area**
- Usually means: broken button, unresponsive UI, or confusion
- Check the timestamps in your video to see what they were trying to click

### High Interaction Density
- **Lots of actions in short time**
- Could mean: scanning for something, uncertainty, or error recovery
- Use `intensity.csv` to find these moments

### Long Pauses
- **Gaps between actions**
- Could mean: reading, thinking, confusion, or distraction
- Note the `longest_pause_seconds` in the summary

### Clicks Per Minute
- **Baseline for comparison**
- Compare between tasks or participants
- Sudden changes might indicate difficulty shifts

## Tips

1. **Always start screen recording first** - Then start InterLog
2. **Name your sessions** - Use `--name` for easier identification
3. **Check the summary** - Run `interlog analyze` to spot patterns
4. **Use intensity data** - Find "hot spots" in long videos quickly
5. **Combine with notes** - Add timestamps to your observations

## Troubleshooting

**"ModuleNotFoundError: No module named 'pynput'"**
```bash
pip install pynput
```

**"Permission denied" (macOS)**
- System Preferences > Security & Privacy > Privacy > Accessibility
- Add Terminal or your IDE

**No events captured**
- Check that the script is running (you should see "Recording...")
- Try moving mouse/clicking - you should see the event count increase

**Want to stop mid-session**
- Just press `Ctrl+C` - everything is saved automatically

## Next Steps

- Read [README.md](README.md) for complete documentation
- Check [examples/](examples/) for sample output files
- Experiment with different `--bucket-size` values in analyzer

---

Questions? Open an issue on GitHub or check the FAQ in README.md
