# InterLog Quick Start Guide

## Installation (30 seconds)

```bash
# 1. Install Python dependency
pip install -r requirements.txt

# 2. You're ready!
```

## Your First Session (2 minutes)

### Step 1: Start Recording

```bash
python interlog.py
```

You'll see:
```
Starting InterLog session: 20240115_143000
Privacy mode: DISABLED
Output directory: /current/directory

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
Events: 20240115_143000_events.csv
Metadata: 20240115_143000_metadata.json

Total events captured: 2341
Duration: 45.67 seconds

Run analyzer to generate statistics:
  python analyzer.py 20240115_143000_events.csv
```

### Step 4: Analyze

```bash
python analyzer.py 20240115_143000_events.csv
```

You'll get:
- Console summary of all statistics
- `20240115_143000_summary.csv` - Stats spreadsheet
- `20240115_143000_intensity.csv` - Time-bucketed activity

## Common Use Cases

### UX Research Session

```bash
# 1. Start screen recording (OBS, QuickTime, etc.)

# 2. Start InterLog with a descriptive name
python interlog.py --name participant_01_checkout_flow

# 3. Conduct research session

# 4. Stop InterLog (Ctrl+C)

# 5. Stop screen recording

# 6. Analyze
python analyzer.py participant_01_checkout_flow_events.csv
```

### Privacy Mode (Sensitive Data)

```bash
# Don't record which keys were pressed
python interlog.py --privacy --name sensitive_session
```

### Organize Multiple Sessions

```bash
# Create organized directory structure
mkdir -p research_study/sessions

# Record session
python interlog.py --output research_study/sessions --name p01

# Analyze later
python analyzer.py research_study/sessions/p01_events.csv
```

## What to Look For

### Rage Clicks
- **3+ rapid clicks in same area**
- Usually means: broken button, unresponsive UI, or confusion
- Check the timestamps in your video to see what they were trying to click

### High Interaction Density
- **Lots of actions in short time**
- Could mean: scanning for something, uncertainty, or error recovery
- Use `*_intensity.csv` to find these moments

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
3. **Check the summary** - Run analyzer.py to spot patterns
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
