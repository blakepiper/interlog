"""Generate a self-contained HTML report for an InterLog session.

Embeds session stats, an SVG activity timeline, and (if available) the
mouse heatmap as a base64 image — everything needed for a screenshot or
a shareable artefact, with no external dependencies.
"""

import base64
from pathlib import Path
from string import Template

from interlog.analyzer import LONG_PAUSE_THRESHOLD_S, InteractionAnalyzer
from interlog.viewer import _read_metadata


# ---------------------------------------------------------------------------
# HTML template  (uses $placeholder so CSS {} braces need no escaping)
# ---------------------------------------------------------------------------

_REPORT_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>InterLog Report — $session_name</title>
<style>
  :root { color-scheme: dark; }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0f1117;
    color: #e2e8f0;
    font: 14px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    padding: 40px 32px 64px;
  }
  .wrap { max-width: 880px; margin: 0 auto; }

  /* ---- header ---- */
  .header { margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid #1e2330; }
  .header-meta { color: #475569; font-size: 11px; text-transform: uppercase;
    letter-spacing: .08em; margin-bottom: 8px; }
  .header h1 { font-size: 22px; font-weight: 700; color: #f1f5f9; }
  .header .sub { color: #94a3b8; font-size: 13px; margin-top: 4px; }

  /* ---- sections ---- */
  .section { margin-bottom: 28px; }
  .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
    color: #475569; margin-bottom: 12px; }
  .section-title .note { text-transform: none; letter-spacing: 0; font-weight: 400;
    color: #334155; margin-left: 8px; }

  /* ---- metric cards ---- */
  .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .card { background: #161b27; border: 1px solid #1e2330; border-radius: 8px; padding: 14px 16px; }
  .card .label { font-size: 11px; color: #64748b; margin-bottom: 6px;
    display: flex; align-items: center; gap: 6px; }
  .card .value { font-size: 22px; font-weight: 600; color: #e2e8f0;
    font-variant-numeric: tabular-nums; line-height: 1.2; }
  .card .unit { font-size: 11px; color: #64748b; margin-left: 2px; font-weight: 400; }
  .badge { display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-size: 10px; font-weight: 600; letter-spacing: .05em; }

  /* ---- activity chart ---- */
  .chart-wrap { background: #161b27; border: 1px solid #1e2330; border-radius: 8px;
    padding: 16px 16px 12px; }
  .chart-axis { display: flex; justify-content: space-between; color: #334155;
    font-size: 11px; margin-top: 8px; font-variant-numeric: tabular-nums; }

  /* ---- heatmap ---- */
  .heatmap-img { width: 100%; border-radius: 8px; display: block; }
  .no-heatmap { color: #475569; font-size: 13px; padding: 28px 20px;
    text-align: center; background: #161b27; border: 1px dashed #1e2330;
    border-radius: 8px; line-height: 2; }
  .no-heatmap code { color: #7dd3fc; background: #0f1929;
    padding: 2px 6px; border-radius: 4px; font-size: 12px; }

  /* ---- footer ---- */
  .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #1a2030;
    color: #334155; font-size: 11px; }
</style>
</head>
<body>
<div class="wrap">

<header class="header">
  <div class="header-meta">InterLog &middot; HCI Interaction Report</div>
  <h1>$session_name</h1>
  <div class="sub">$date &ensp;&middot;&ensp; $duration</div>
</header>

<section class="section">
  <div class="section-title">Session Overview</div>
  <div class="metrics">
    <div class="card">
      <div class="label">Duration</div>
      <div class="value">$duration</div>
    </div>
    <div class="card">
      <div class="label">Total events</div>
      <div class="value">$total_events</div>
    </div>
    <div class="card">
      <div class="label">Interactions</div>
      <div class="value">$total_interactions</div>
    </div>
    <div class="card">
      <div class="label">Key presses</div>
      <div class="value">$keypresses</div>
    </div>
  </div>
</section>

<section class="section">
  <div class="section-title">Interaction Rates</div>
  <div class="metrics">
    <div class="card">
      <div class="label">Clicks / min</div>
      <div class="value">$clicks_per_minute</div>
    </div>
    <div class="card">
      <div class="label">Actions / min</div>
      <div class="value">$actions_per_minute</div>
    </div>
    <div class="card">
      <div class="label">Scroll distance</div>
      <div class="value" style="font-size:17px">$scroll_distance</div>
    </div>
    <div class="card">
      <div class="label">Total clicks</div>
      <div class="value">$total_clicks</div>
    </div>
  </div>
</section>

<section class="section">
  <div class="section-title">
    Interaction Signals
    <span class="note">descriptive counts, not a diagnosis</span>
  </div>
  <div class="metrics">
    <div class="card">
      <div class="label">Rage-click bursts</div>
      <div class="value" style="color:$rage_color">$rage_clicks</div>
    </div>
    <div class="card">
      <div class="label">Double clicks</div>
      <div class="value">$double_clicks</div>
    </div>
    <div class="card">
      <div class="label">Long pauses <span class="unit">&gt;${long_pause_threshold}s</span></div>
      <div class="value">$long_pauses</div>
    </div>
    <div class="card">
      <div class="label">Path efficiency</div>
      <div class="value">$path_efficiency</div>
    </div>
  </div>
</section>

<section class="section">
  <div class="section-title">
    Activity Timeline
    <span class="note">${bucket_size}s buckets &middot; red = rage clicks</span>
  </div>
  <div class="chart-wrap">
    $sparkline_svg
    <div class="chart-axis"><span>0:00</span><span>$duration</span></div>
  </div>
</section>

<section class="section">
  <div class="section-title">Mouse Heatmap</div>
  $heatmap_block
</section>

<footer class="footer">
  Generated with <strong>InterLog</strong> &mdash; local interaction logging for HCI research
</footer>

</div>
</body>
</html>
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_image(path):
    """Return a data: URI for the image at path, or None on failure."""
    try:
        data = Path(path).read_bytes()
        mime = "image/png" if str(path).endswith(".png") else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except OSError:
        return None


def _build_sparkline_svg(buckets, rage_ts, duration, width=840, height=90):
    """Return an inline SVG bar chart of interaction intensity."""
    if not buckets:
        return (
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="{width//2}" y="{height//2}" text-anchor="middle" '
            f'fill="#334155" font-size="12">No activity data</text></svg>'
        )

    max_v = max((b["total_interactions"] for b in buckets), default=1) or 1
    n = len(buckets)
    bar_w = width / n
    pad_top = 4

    parts = []
    for i, b in enumerate(buckets):
        h = max(2, int((b["total_interactions"] / max_v) * (height - pad_top)))
        x = i * bar_w
        y = height - h
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.1f}" '
            f'width="{max(1, bar_w - 0.8):.2f}" height="{h}" fill="#3a5a9f"/>'
        )

    for t in rage_ts:
        x = (t / (duration or 1)) * width
        parts.append(
            f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{height}" '
            f'stroke="#ef4444" stroke-width="1.5"/>'
        )

    return (
        f'<svg width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:{height}px;display:block">'
        + "".join(parts)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report(session_path, output=None, bucket_size=5.0):
    """Build a self-contained HTML report for a session.

    Args:
        session_path: Session folder or path to events.csv.
        output: Output HTML path (default: <session>/report.html).
        bucket_size: Bucket size in seconds for the activity timeline.

    Returns:
        Path to the written HTML file.
    """
    session_path = Path(session_path)
    if session_path.is_dir():
        session_dir = session_path
        events_path = session_dir / "events.csv"
    else:
        session_dir = session_path.parent
        events_path = session_path

    if not events_path.exists():
        raise FileNotFoundError(f"Events file not found: {events_path}")

    analyzer = InteractionAnalyzer(events_path)
    analyzer.load_events()
    if not analyzer.events:
        raise ValueError("No events found in session.")
    analyzer.calculate_statistics()
    s = analyzer.stats

    meta = _read_metadata(events_path)
    session_name = meta.get("session_name") or session_dir.name
    start_date = (meta.get("start_time") or "")[:10]

    buckets = analyzer.calculate_intensity(bucket_size)
    duration = s["session_duration_seconds"]

    clicks = [
        {"timestamp": e["timestamp"], "x": e.get("x"), "y": e.get("y")}
        for e in analyzer.events
        if e["event_type"] == "mouse_down"
    ]
    rage_ts = [r["timestamp"] for r in analyzer._detect_rage_clicks(clicks)]

    sparkline_svg = _build_sparkline_svg(
        [{"total_interactions": b["total_interactions"]} for b in buckets],
        rage_ts,
        duration,
    )

    heatmap_path = session_dir / "heatmap.png"
    heatmap_src = _encode_image(heatmap_path) if heatmap_path.exists() else None
    if heatmap_src:
        heatmap_block = f'<img src="{heatmap_src}" alt="Mouse movement heatmap" class="heatmap-img">'
    else:
        hint_cmd = f"interlog heatmap {session_dir}"
        heatmap_block = (
            f'<div class="no-heatmap">'
            f'Run <code>{hint_cmd}</code> to generate the heatmap,<br>'
            f'then re-run <code>interlog report {session_dir}</code> to embed it here.'
            f'</div>'
        )

    rage_color = "#ef4444" if s["rage_clicks_detected"] > 0 else "#e2e8f0"
    eff = s.get("mean_path_efficiency")
    path_efficiency = f"{eff:.2f}" if eff is not None else "n/a"

    dur_fmt = s["session_duration_formatted"]

    html = _REPORT_TEMPLATE.substitute(
        session_name=session_name,
        date=start_date or "—",
        duration=dur_fmt,
        total_events=f"{s['total_events']:,}",
        total_interactions=f"{s['total_interactions']:,}",
        total_clicks=f"{s['total_clicks']:,}",
        keypresses=f"{s['total_keypresses']:,}",
        clicks_per_minute=f"{s['clicks_per_minute']:.1f}",
        actions_per_minute=f"{s['actions_per_minute']:.1f}",
        scroll_distance=f"{s['total_scroll_distance']:,} px",
        rage_clicks=str(s["rage_clicks_detected"]),
        rage_color=rage_color,
        double_clicks=str(s["double_clicks"]),
        long_pauses=str(s["long_pauses"]),
        long_pause_threshold=int(LONG_PAUSE_THRESHOLD_S),
        path_efficiency=path_efficiency,
        bucket_size=int(bucket_size) if bucket_size == int(bucket_size) else bucket_size,
        sparkline_svg=sparkline_svg,
        heatmap_block=heatmap_block,
    )

    if output is None:
        output = session_dir / "report.html"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
