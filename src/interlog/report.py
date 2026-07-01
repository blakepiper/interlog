"""Generate a self-contained HTML report for an InterLog session.

Embeds session stats, an SVG activity timeline, and (if available) the
mouse heatmap as a base64 image — everything needed for a screenshot or
a shareable artefact, with no external dependencies.
"""

import base64
import html
from pathlib import Path
from string import Template

from interlog.analyzer import (
    LONG_PAUSE_THRESHOLD_S,
    InteractionAnalyzer,
    detect_rage_clicks,
    mouse_down_clicks,
    read_session_metadata,
)
from interlog.security import lock_down


# ---------------------------------------------------------------------------
# HTML template  (uses $placeholder so CSS {} braces need no escaping)
# ---------------------------------------------------------------------------

_REPORT_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>InterLog Readout — $session_name</title>
<style>
  :root {
    color-scheme: dark;
    --ink:#0A0C10; --ink2:#0E131B;
    --line:#1C2632; --line-soft:#151d27;
    --signal:#46E0B8; --alert:#FF5A47; --cursor:#FFB23E;
    --text:#E6EBF2; --text2:#98A6B8; --muted:#5C6A7D;
    --mono: ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,Consolas,monospace;
    --sans: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--ink); color: var(--text);
    font: 14px/1.55 var(--sans); -webkit-font-smoothing: antialiased;
    padding: 40px 28px 60px; }
  .wrap { max-width: 900px; margin: 0 auto; }

  /* ---- header ---- */
  .ident { display: flex; align-items: center; gap: 10px; margin-bottom: 22px; }
  .mark { width: 10px; height: 10px; background: var(--signal); border-radius: 2px;
    transform: rotate(45deg); box-shadow: 0 0 10px var(--signal); }
  .wordmark { font: 700 16px/1 var(--sans); letter-spacing: -.01em; }
  .tag { font: 600 10px/1 var(--sans); letter-spacing: .09em; text-transform: uppercase;
    color: var(--muted); padding: 4px 8px; border: 1px solid var(--line); border-radius: 5px; }
  .rhead { display: flex; align-items: flex-end; justify-content: space-between;
    gap: 22px; flex-wrap: wrap; padding-bottom: 22px; margin-bottom: 28px;
    border-bottom: 1px solid var(--line); }
  .rhead h1 { font: 600 24px/1.15 var(--sans); color: #F3F6FA; letter-spacing: -.01em; }
  .rhead .sub { font: 13px/1 var(--sans); color: var(--muted); margin-top: 9px; }
  .gauges { display: flex; gap: 10px; }
  .gauge { display: flex; flex-direction: column; align-items: flex-end;
    padding: 9px 15px; border: 1px solid var(--line); border-radius: 9px;
    background: var(--ink2); min-width: 92px; }
  .gauge.alert { border-color: rgba(255,90,71,.4); }
  .g-val { font: 650 20px/1 var(--sans); font-variant-numeric: tabular-nums; color: var(--text); }
  .g-lab { font: 600 10px/1 var(--sans); letter-spacing: .09em; text-transform: uppercase;
    color: var(--muted); margin-top: 7px; }

  /* ---- scope (hero) ---- */
  .scope { padding: 16px 18px 12px; border: 1px solid var(--line); border-radius: 12px;
    background: var(--ink2); margin-bottom: 30px; }
  .scope-cap { display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .scope-title { font: 600 11px/1 var(--sans); letter-spacing: .1em; text-transform: uppercase; color: var(--text2); }
  .scope-note { font: 12px/1 var(--sans); color: var(--muted); }
  .chart-axis { display: flex; justify-content: space-between; color: var(--muted);
    font: 12px/1 var(--sans); font-variant-numeric: tabular-nums; margin-top: 8px; }

  /* ---- panels ---- */
  .panel { margin-bottom: 26px; }
  .panel-label { font: 600 11px/1 var(--sans); letter-spacing: .1em; text-transform: uppercase;
    color: var(--text2); margin-bottom: 13px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .panel-label .note { font: 400 12px/1.3 var(--sans); letter-spacing: 0;
    color: var(--muted); text-transform: none; }
  .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .cell { background: var(--ink2); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
  .cell .label { font: 600 10px/1.2 var(--sans); letter-spacing: .07em; color: var(--muted);
    text-transform: uppercase; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
  .cell .value { font: 650 22px/1.1 var(--sans); font-variant-numeric: tabular-nums; color: var(--text); }
  .cell .unit { font: 12px/1 var(--sans); color: var(--muted); margin-left: 3px; font-weight: 400; }

  /* ---- heatmap ---- */
  .heatmap-img { width: 100%; border-radius: 8px; display: block; border: 1px solid var(--line); }
  .no-heatmap { color: var(--text2); font: 13px/1.9 var(--sans); padding: 26px 20px;
    text-align: center; background: var(--ink2); border: 1px dashed var(--line); border-radius: 8px; }
  .no-heatmap code { font-family: var(--mono); color: var(--signal); background: #0c1620;
    padding: 2px 6px; border-radius: 4px; font-size: 12px; }

  /* ---- footer ---- */
  .rfoot { margin-top: 34px; padding-top: 20px; border-top: 1px solid var(--line);
    color: var(--muted); font: 11px/1.5 var(--sans); }
  .rfoot b { color: var(--text2); font-weight: 600; }

  @media (max-width: 680px) {
    .metrics { grid-template-columns: repeat(2, 1fr); }
    .rhead { align-items: flex-start; }
  }
</style>
</head>
<body>
<div class="wrap">

<div class="ident">
  <span class="mark"></span>
  <span class="wordmark">InterLog</span>
  <span class="tag">Session readout</span>
</div>

<header class="rhead">
  <div>
    <h1>$session_name</h1>
    <div class="sub">$date &nbsp;·&nbsp; $duration</div>
  </div>
  <div class="gauges">
    <div class="gauge">
      <span class="g-val">$total_interactions</span><span class="g-lab">INTERACTIONS</span>
    </div>
    <div class="gauge">
      <span class="g-val">$actions_per_minute</span><span class="g-lab">ACTIONS / MIN</span>
    </div>
    <div class="gauge $rage_state">
      <span class="g-val" style="color:$rage_color">$rage_clicks</span><span class="g-lab">RAGE BURSTS</span>
    </div>
  </div>
</header>

<figure class="scope">
  <figcaption class="scope-cap">
    <span class="scope-title">Interaction trace</span>
    <span class="scope-note">${bucket_size}s buckets · red marks rage clicks</span>
  </figcaption>
  $sparkline_svg
  <div class="chart-axis"><span>0:00</span><span>$duration</span></div>
</figure>

<section class="panel">
  <div class="panel-label">Session Overview</div>
  <div class="metrics">
    <div class="cell"><div class="label">Duration</div><div class="value">$duration</div></div>
    <div class="cell"><div class="label">Total events</div><div class="value">$total_events</div></div>
    <div class="cell"><div class="label">Interactions</div><div class="value">$total_interactions</div></div>
    <div class="cell"><div class="label">Key presses</div><div class="value">$keypresses</div></div>
  </div>
</section>

<section class="panel">
  <div class="panel-label">Interaction Rates</div>
  <div class="metrics">
    <div class="cell"><div class="label">Clicks / min</div><div class="value">$clicks_per_minute</div></div>
    <div class="cell"><div class="label">Actions / min</div><div class="value">$actions_per_minute</div></div>
    <div class="cell"><div class="label">Scroll distance</div><div class="value">$scroll_distance</div></div>
    <div class="cell"><div class="label">Total clicks</div><div class="value">$total_clicks</div></div>
  </div>
</section>

<section class="panel">
  <div class="panel-label">
    Interaction Signals
    <span class="note">descriptive counts, not a diagnosis</span>
  </div>
  <div class="metrics">
    <div class="cell"><div class="label">Rage-click bursts</div>
      <div class="value" style="color:$rage_color">$rage_clicks</div></div>
    <div class="cell"><div class="label">Double clicks</div><div class="value">$double_clicks</div></div>
    <div class="cell"><div class="label">Long pauses <span class="unit">&gt;${long_pause_threshold}s</span></div>
      <div class="value">$long_pauses</div></div>
    <div class="cell"><div class="label">Path efficiency</div><div class="value">$path_efficiency</div></div>
  </div>
</section>

<section class="panel">
  <div class="panel-label">
    Movement &amp; Coordination
    <span class="note">accuracy (MacKenzie CHI 2001) · pixel measures are per-environment</span>
  </div>
  <div class="metrics">
    <div class="cell"><div class="label">Movement error</div>
      <div class="value">$movement_error<span class="unit">px</span></div></div>
    <div class="cell"><div class="label">Modality switches</div>
      <div class="value">$modality_switches<span class="unit">/min</span></div></div>
    <div class="cell"><div class="label">Pre-click dwell</div>
      <div class="value">$pre_click_dwell<span class="unit">s</span></div></div>
    <div class="cell"><div class="label">Click spread</div>
      <div class="value">$click_spread<span class="unit">px</span></div></div>
  </div>
</section>

<section class="panel">
  <div class="panel-label">Mouse Heatmap</div>
  $heatmap_block
</section>

<footer class="rfoot">
  Generated with <b>InterLog</b> — local interaction logging for HCI research.
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


def _nice_step(duration):
    """Pick a round time-axis step so the trace shows ~6 divisions."""
    target = (duration or 1) / 6
    for s in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900):
        if target <= s:
            return s
    return 1800


def _fmt_short(seconds):
    return f"{int(seconds // 60)}:{int(round(seconds % 60)):02d}"


def _build_sparkline_svg(buckets, rage_ts, duration, width=852, height=132):
    """Inline SVG of interaction intensity as a filled trace on a measurement
    graticule, matching the viewer's oscilloscope scope (green = activity,
    red ticks = rage clicks)."""
    pad_top, pad_bottom = 18, 6
    base_y = height - pad_bottom
    plot_h = base_y - pad_top
    head = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:{height}px;display:block">'
    )

    if not buckets:
        return (
            head
            + f'<text x="{width // 2}" y="{height // 2}" text-anchor="middle" '
            f'fill="#5C6A7D" font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif" font-size="12">'
            f'No activity data</text></svg>'
        )

    max_v = max((b["total_interactions"] for b in buckets), default=1) or 1
    origin = buckets[0]["time_start"]
    dur = duration or 1

    def x_for(t):
        return ((t - origin) / dur) * width

    parts = []
    # graticule — horizontal divisions
    for i in range(1, 4):
        y = pad_top + plot_h * i / 4
        parts.append(f'<line x1="0" y1="{y:.1f}" x2="{width}" y2="{y:.1f}" '
                     f'stroke="#151d27" stroke-width="1"/>')
    # graticule — time divisions + ruler labels
    step = _nice_step(dur)
    t = step
    while t < dur:
        x = x_for(origin + t)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{base_y}" '
                     f'stroke="#151d27" stroke-width="1"/>')
        parts.append(f'<text x="{x + 3:.1f}" y="12" fill="#5C6A7D" '
                     f'font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif" font-size="10">{_fmt_short(t)}</text>')
        t += step
    # baseline
    parts.append(f'<line x1="0" y1="{base_y}" x2="{width}" y2="{base_y}" '
                 f'stroke="#1C2632" stroke-width="1"/>')

    # waveform points at bucket centers
    pts = [
        (x_for((b["time_start"] + b["time_end"]) / 2),
         base_y - (b["total_interactions"] / max_v) * plot_h)
        for b in buckets
    ]
    area = (f'M {pts[0][0]:.1f} {base_y:.1f} '
            + " ".join(f'L {x:.1f} {y:.1f}' for x, y in pts)
            + f' L {pts[-1][0]:.1f} {base_y:.1f} Z')
    line = "M " + " L ".join(f'{x:.1f} {y:.1f}' for x, y in pts)
    parts.append(
        '<defs><linearGradient id="sig" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#46E0B8" stop-opacity="0.28"/>'
        '<stop offset="1" stop-color="#46E0B8" stop-opacity="0.02"/></linearGradient></defs>'
    )
    parts.append(f'<path d="{area}" fill="url(#sig)"/>')
    parts.append(f'<path d="{line}" fill="none" stroke="#46E0B8" stroke-width="1.5"/>')

    # rage alert ticks
    for tt in rage_ts:
        x = x_for(tt)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{base_y}" '
                     f'stroke="#FF5A47" stroke-width="1" opacity="0.5"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{pad_top}" r="2.5" fill="#FF5A47"/>')

    return head + "".join(parts) + "</svg>"


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

    meta = read_session_metadata(events_path)
    # Escaped: these land in HTML and may contain user/dir-supplied characters.
    session_name = html.escape(meta.get("session_name") or session_dir.name)
    start_date = html.escape((meta.get("start_time") or "")[:10])

    buckets = analyzer.calculate_intensity(bucket_size)
    duration = s["session_duration_seconds"]

    rage_ts = [b["timestamp"] for b in detect_rage_clicks(mouse_down_clicks(analyzer.events))]
    sparkline_svg = _build_sparkline_svg(buckets, rage_ts, duration)

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

    has_rage = s["rage_clicks_detected"] > 0
    rage_color = "#FF5A47" if has_rage else "#E6EBF2"
    rage_state = "alert" if has_rage else ""
    eff = s.get("mean_path_efficiency")
    path_efficiency = f"{eff:.2f}" if eff is not None else "n/a"

    me = s.get("movement_error_px")
    movement_error = f"{me:.1f}" if me is not None else "n/a"
    dwell = s.get("pre_click_dwell_seconds")
    pre_click_dwell = f"{dwell:.2f}" if dwell is not None else "n/a"
    spread = s.get("click_spread_px")
    click_spread = f"{spread:,.0f}" if spread is not None else "n/a"

    dur_fmt = s["session_duration_formatted"]

    rendered = _REPORT_TEMPLATE.substitute(
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
        rage_state=rage_state,
        double_clicks=str(s["double_clicks"]),
        long_pauses=str(s["long_pauses"]),
        long_pause_threshold=int(LONG_PAUSE_THRESHOLD_S),
        path_efficiency=path_efficiency,
        movement_error=movement_error,
        modality_switches=f"{s['modality_switches_per_minute']:.1f}",
        pre_click_dwell=pre_click_dwell,
        click_spread=click_spread,
        bucket_size=f"{bucket_size:g}",
        sparkline_svg=sparkline_svg,
        heatmap_block=heatmap_block,
    )

    if output is None:
        output = session_dir / "report.html"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    lock_down(output)
    return output
