#!/usr/bin/env python3
"""Render docs/img/viewer.gif — the synced viewer jumping the video to hot spots.

The viewer syncs interaction data to a *real* <video>, so to show it working we
synthesize a screen-recording-like video whose cursor follows the session's
recorded pointer path, load it through the actual `interlog view --serve` server,
and drive the seeks with a headless browser — then stitch the frames into a GIF.

Setup (one time):

    pip install playwright && playwright install chromium
    # ffmpeg must be on PATH (used to encode the video and the GIF)

Run from the repo root:

    python tools/capture_viewer_gif.py
"""

import bisect
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from capture_screenshots import write_hero_session  # noqa: E402
from interlog.analyzer import load_event_rows  # noqa: E402
from interlog.serve import serve_viewer  # noqa: E402
from interlog.viewer import build_viewer  # noqa: E402

IMG_DIR = ROOT / "docs" / "img"
VW, VH = 1280, 720                       # video size
FIELDS = ["Email", "Card number", "Place order", "Promo code", "ZIP code"]


def _font(size):
    from matplotlib import font_manager
    from PIL import ImageFont
    return ImageFont.truetype(font_manager.findfont("DejaVu Sans"), size)


def _cursor_track(events):
    """(times, xs, ys) of pointer moves, scaled into the video's pixel space."""
    sx, sy = VW / 1440, VH / 810
    ts, xs, ys = [], [], []
    for e in events:
        if e["event_type"] == "mouse_move" and isinstance(e.get("x"), int):
            ts.append(e["timestamp"])
            xs.append(int(e["x"] * sx))
            ys.append(int(e["y"] * sy))
    return ts, xs, ys


def _render_video(session, events, duration, out_video):
    """Render a mock checkout screen whose cursor replays the recorded path."""
    from PIL import Image, ImageDraw

    sx, sy = VW / 1440, VH / 810
    spots = [(330, 240), (1060, 250), (760, 560), (300, 650), (1130, 640)]
    boxes = []  # (x0, y0, x1, y1, label) in video space
    for (hx, hy), label in zip(spots, FIELDS):
        cx, cy = hx * sx, hy * sy
        w, h = (230, 56) if label != "Place order" else (260, 64)
        boxes.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, label))

    ts, xs, ys = _cursor_track(events)
    title_f, label_f, time_f = _font(30), _font(22), _font(26)
    fps = 12
    frames = int(duration * fps) + 1
    frame_dir = Path(tempfile.mkdtemp())

    for i in range(frames):
        tf = i / fps
        img = Image.new("RGB", (VW, VH), "#0b0f16")
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, VW, 64), fill="#11161f")
        d.text((28, 18), "Acme  ·  Checkout", font=title_f, fill="#e2e8f0")
        d.text((VW - 150, 20), f"{int(tf // 60)}:{tf % 60:04.1f}", font=time_f, fill="#64748b")

        # cursor position = last recorded move at/under this time
        j = max(0, bisect.bisect_right(ts, tf) - 1)
        cx, cy = (xs[j], ys[j]) if ts else (VW // 2, VH // 2)

        for (x0, y0, x1, y1, label) in boxes:
            active = x0 - 14 <= cx <= x1 + 14 and y0 - 14 <= cy <= y1 + 14
            is_cta = label == "Place order"
            fill = "#1d4ed8" if is_cta else "#161c27"
            border = "#22d3ee" if active else ("#2563eb" if is_cta else "#27303f")
            d.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=fill, outline=border, width=3 if active else 2)
            d.text((x0 + 16, (y0 + y1) / 2 - 12), label, font=label_f,
                   fill="#ffffff" if is_cta else "#94a3b8")

        # progress bar + cursor
        d.rectangle((0, VH - 5, int(VW * tf / duration), VH), fill="#22d3ee")
        d.polygon([(cx, cy), (cx, cy + 22), (cx + 6, cy + 16),
                   (cx + 11, cy + 26), (cx + 15, cy + 24), (cx + 10, cy + 14),
                   (cx + 18, cy + 14)], fill="#ffffff", outline="#0b0f16")
        img.save(frame_dir / f"f{i:05d}.png")

    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frame_dir / "f%05d.png"),
         "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-pix_fmt", "yuv420p",
         str(out_video)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    shutil.rmtree(frame_dir, ignore_errors=True)


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed. Run:\n"
                 "  pip install playwright && playwright install chromium")

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    session = write_hero_session(work / "checkout-flow")
    events = load_event_rows(session / "events.csv")
    duration = max(e["timestamp"] for e in events)

    _render_video(session, events, duration, session / "recording.webm")
    viewer = build_viewer(session / "events.csv", open_browser=False,
                          video_src="recording.webm")

    httpd, url = serve_viewer(viewer.parent, viewer.name)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    # seek targets: a few hot spots across the session, ending on the rage burst
    targets = [0.5, duration * 0.18, duration * 0.42, duration * 0.62, duration - 0.6]
    shots = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 880},
                                    device_scale_factor=2)
            page.goto(url)
            page.wait_for_function("document.getElementById('video').readyState >= 2",
                                   timeout=15000)
            page.evaluate("document.getElementById('video').pause()")
            for k, tt in enumerate(targets):
                page.evaluate(
                    """t => { const v = document.getElementById('video');
                             v.pause(); v.currentTime = t; }""", tt)
                page.wait_for_function(
                    "t => Math.abs(document.getElementById('video').currentTime - t) < 0.3",
                    arg=tt, timeout=5000)
                page.wait_for_timeout(450)
                shot = work / f"shot{k:02d}.png"
                page.screenshot(path=str(shot))
                shots.append(shot)
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    # assemble the frames into a looping GIF (~1.4s per frame)
    listfile = work / "frames.txt"
    listfile.write_text("".join(
        f"file '{s}'\nduration 1.4\n" for s in shots) + f"file '{shots[-1]}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-vf", "scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
         "-loop", "0", str(IMG_DIR / "viewer.gif")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"wrote {IMG_DIR / 'viewer.gif'}")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
