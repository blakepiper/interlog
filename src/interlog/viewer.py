"""Generate a self-contained HTML viewer that syncs a session's interactions
with a screen recording.

The viewer embeds precomputed intensity buckets, interaction markers, and
detected rage clicks. The user loads their recording locally in the browser
(nothing is uploaded), and clicking a hot spot or the timeline seeks the video
to that moment.
"""

import json
import webbrowser
from pathlib import Path

from interlog.analyzer import (
    InteractionAnalyzer,
    base_prefix,
    detect_rage_clicks,
    mouse_down_clicks,
    read_session_metadata,
)
from interlog.security import lock_down

_TEMPLATE = Path(__file__).parent / "viewer_template.html"
_PLACEHOLDER = "__INTERLOG_DATA__"

# Interaction events worth marking on the timeline (mouse moves are excluded -
# they are high-volume and low-signal).
_MARKER_TYPES = {"mouse_down", "scroll", "key_press", "drag"}


def build_viewer(events_file, output=None, bucket_size=2.0, open_browser=True, video_src=None):
    """Generate the viewer HTML for a session. Returns the output path."""
    events_file = Path(events_file)

    analyzer = InteractionAnalyzer(events_file)
    analyzer.load_events()

    if not analyzer.events:
        raise ValueError(f"No events found in {events_file}")

    timestamps = [e["timestamp"] for e in analyzer.events]
    duration = max(timestamps) - min(timestamps)

    buckets = [
        {"t0": b["time_start"], "t1": b["time_end"], "total": b["total_interactions"]}
        for b in analyzer.calculate_intensity(bucket_size)
    ]

    markers = [
        {"t": round(e["timestamp"], 3), "type": e["event_type"],
         "x": e.get("x"), "y": e.get("y")}
        for e in analyzer.events
        if e["event_type"] in _MARKER_TYPES
    ]

    rage = [
        {"t": round(r["timestamp"], 3), "x": r["x"], "y": r["y"], "count": r["click_count"]}
        for r in detect_rage_clicks(mouse_down_clicks(analyzer.events))
    ]

    session_label = base_prefix(events_file).rstrip("_") or events_file.parent.name
    meta = read_session_metadata(events_file)

    try:
        offset = float(meta.get("video_start_offset", 0.0))
    except (TypeError, ValueError):
        offset = 0.0

    data = {
        "session": session_label,
        "duration": round(duration, 3),
        "offset": offset,
        "captureRegion": meta.get("capture_region"),
        "videoSrc": video_src,
        "buckets": buckets,
        "markers": markers,
        "rageClicks": rage,
    }

    data_json = json.dumps(data).replace("</", "<\\/")  # keep it safe inside <script>
    html = _TEMPLATE.read_text(encoding="utf-8").replace(_PLACEHOLDER, data_json)

    if output is None:
        output = events_file.parent / f"{base_prefix(events_file)}viewer.html"
    else:
        output = Path(output)
        # A path ending in .html is a file; anything else is treated as a directory.
        if output.suffix.lower() != ".html":
            output = output / f"{base_prefix(events_file)}viewer.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    lock_down(output)

    if open_browser:
        webbrowser.open(output.resolve().as_uri())

    return output
