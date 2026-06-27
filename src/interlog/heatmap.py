"""Mouse movement and click heatmap for InterLog sessions.

Renders a density heatmap of pointer movement overlaid with click markers,
using PIL for the Gaussian blur (avoids a scipy dependency) and matplotlib
for compositing and output.
"""

import shutil
import subprocess
from pathlib import Path

from interlog.analyzer import detect_rage_clicks, load_event_rows, read_session_metadata


def _grab_frame(video_path, out_path, duration, frame_at=0.25):
    """Extract a single frame at `frame_at` fraction into the recording."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    t = max(0.5, (duration or 0) * frame_at) if duration else 2.0
    r = subprocess.run(
        [ff, "-y", "-ss", f"{t:.1f}", "-i", str(video_path),
         "-frames:v", "1", "-q:v", "2", str(out_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return out_path if r.returncode == 0 and out_path.exists() else None


def _infer_bounds(events):
    """Infer canvas size from the range of mouse coordinates in the data."""
    xs = [e["x"] for e in events
          if e["event_type"] == "mouse_move" and isinstance(e.get("x"), int)]
    ys = [e["y"] for e in events
          if e["event_type"] == "mouse_move" and isinstance(e.get("y"), int)]
    return (max(xs) + 100 if xs else 1920), (max(ys) + 100 if ys else 1080)


def _rage_timestamps(click_events):
    """Return the set of event timestamps that belong to a rage-click burst."""
    return {t for b in detect_rage_clicks(click_events) for t in b["timestamps"]}


def _heatmap_cmap():
    """Transparent-to-cyan-to-yellow-to-white density colormap."""
    from matplotlib.colors import LinearSegmentedColormap
    stops = [
        (0.00, (0.00, 0.00, 0.00, 0.00)),
        (0.05, (0.00, 0.20, 0.60, 0.40)),
        (0.20, (0.00, 0.75, 0.90, 0.65)),
        (0.45, (0.10, 0.90, 0.10, 0.80)),
        (0.70, (1.00, 0.90, 0.00, 0.90)),
        (0.88, (1.00, 0.30, 0.00, 0.95)),
        (1.00, (1.00, 1.00, 1.00, 1.00)),
    ]
    return LinearSegmentedColormap.from_list("interlog_heat", stops)


def build_heatmap(session_path, output=None, sigma=25, frame_at=0.25):
    """Build a mouse movement + click heatmap PNG for a session.

    Args:
        session_path: Session folder or path to events.csv.
        output: Output PNG path (default: <session>/heatmap.png).
        sigma: Gaussian blur radius in pixels (default: 25).
        frame_at: Fraction into the recording to grab the background frame (default: 0.25).

    Returns:
        Path to the written PNG.
    """
    import numpy as np
    import matplotlib.pyplot as plt
    from PIL import Image, ImageFilter

    session_path = Path(session_path)
    if session_path.is_dir():
        session_dir = session_path
        events_path = session_dir / "events.csv"
    else:
        session_dir = session_path.parent
        events_path = session_path

    if not events_path.exists():
        raise FileNotFoundError(f"Events file not found: {events_path}")
    if output is None:
        output = session_dir / "heatmap.png"
    output = Path(output)

    events = load_event_rows(events_path)
    if not events:
        raise ValueError("No events found in session.")

    meta = read_session_metadata(events_path)
    region = meta.get("capture_region")
    duration = meta.get("duration_seconds") or 0
    session_name = meta.get("session_name") or session_dir.name
    video_path = session_dir / "recording.mp4"

    # Canvas origin and size. A degenerate region falls back to inferred bounds.
    W = H = 0
    if region:
        W, H = region.get("width", 0), region.get("height", 0)
        ox, oy = region.get("x", 0), region.get("y", 0)
    if not (W > 0 and H > 0):
        W, H = _infer_bounds(events)
        ox, oy = 0, 0
        region = None

    # Grab a background frame and let it override W/H when there's no region
    bg_img_path = None
    if video_path.exists():
        tmp = session_dir / "_hm_frame.jpg"
        grabbed = _grab_frame(video_path, tmp, duration, frame_at=frame_at)
        if grabbed:
            try:
                probe = Image.open(grabbed)
                if not region:
                    W, H = probe.size
                probe.close()
                bg_img_path = grabbed
            except Exception:
                grabbed.unlink(missing_ok=True)

    # Classify events
    move_events = [
        e for e in events
        if e["event_type"] == "mouse_move"
        and isinstance(e.get("x"), int) and isinstance(e.get("y"), int)
    ]
    click_events = [
        e for e in events
        if e["event_type"] == "mouse_down"
        and isinstance(e.get("x"), int) and isinstance(e.get("y"), int)
    ]
    rage_ts = _rage_timestamps(click_events)
    clicks_normal = [(e["x"] - ox, e["y"] - oy) for e in click_events
                     if e["timestamp"] not in rage_ts]
    clicks_rage = [(e["x"] - ox, e["y"] - oy) for e in click_events
                   if e["timestamp"] in rage_ts]

    # Build density grid
    heat = np.zeros((H, W), dtype=np.float32)
    if move_events:
        xs = np.clip([e["x"] - ox for e in move_events], 0, W - 1).astype(int)
        ys = np.clip([e["y"] - oy for e in move_events], 0, H - 1).astype(int)
        np.add.at(heat, (ys, xs), 1.0)
        peak = heat.max()
        if peak > 0:
            pil_h = Image.fromarray((heat * (255.0 / peak)).astype(np.uint8), mode="L")
            pil_h = pil_h.filter(ImageFilter.GaussianBlur(radius=sigma))
            heat = np.array(pil_h, dtype=np.float32) / 255.0

    # Render
    fig_w = 14
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * H / W), dpi=100)
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    if bg_img_path:
        try:
            bg = Image.open(bg_img_path).convert("RGB")
            if (bg.width, bg.height) != (W, H):
                bg = bg.resize((W, H), Image.Resampling.LANCZOS)
            ax.imshow(np.array(bg), extent=[0, W, H, 0], aspect="auto", alpha=0.4)
        except Exception:
            pass
        finally:
            try:
                bg_img_path.unlink()
            except Exception:
                pass

    cmap = _heatmap_cmap()
    if heat.max() > 0:
        ax.imshow(
            heat, extent=[0, W, H, 0], aspect="auto",
            cmap=cmap, alpha=0.85,
            vmin=0.01, vmax=1.0, interpolation="bilinear",
        )

    if clicks_normal:
        cx, cy = zip(*clicks_normal)
        ax.scatter(cx, cy, s=16, c="white", alpha=0.55, linewidths=0, zorder=4)
    if clicks_rage:
        rx, ry = zip(*clicks_rage)
        ax.scatter(rx, ry, s=55, c="#ff3333", alpha=0.85,
                   linewidths=1.5, marker="x", zorder=5)

    # Density colorbar
    if heat.max() > 0:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, orientation="vertical",
                            fraction=0.018, pad=0.008, shrink=0.35, aspect=18)
        cbar.set_ticks([0, 1])
        cbar.set_ticklabels(["low", "high"])
        cbar.ax.tick_params(labelsize=8, colors="#999999", length=0, pad=4)
        cbar.outline.set_visible(False)

    dur_s = int(duration)
    title = (
        f"InterLog  ·  {session_name}"
        f"  |  {dur_s // 60}:{dur_s % 60:02d}"
        f"  ·  {len(move_events):,} moves"
        f"  ·  {len(click_events)} clicks"
    )
    if rage_ts:
        title += f"  ·  {len(rage_ts)} rage"
    ax.set_title(title, color="#bbbbbb", fontsize=10, pad=8,
                 fontfamily="monospace", loc="left")

    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    plt.tight_layout(pad=0.3)
    fig.savefig(output, dpi=100, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return output
