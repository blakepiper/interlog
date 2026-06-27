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
from mock_screen import render_screen  # noqa: E402

IMG_DIR = ROOT / "docs" / "img"


def _cursor_track(events):
    """(times, xs, ys) of pointer moves in screen space (= session space)."""
    ts, xs, ys = [], [], []
    for e in events:
        if e["event_type"] == "mouse_move" and isinstance(e.get("x"), int):
            ts.append(e["timestamp"])
            xs.append(e["x"])
            ys.append(e["y"])
    return ts, xs, ys


def _render_video(events, duration, out_video):
    """Render the checkout screen with the cursor replaying the recorded path,
    using the same ``mock_screen`` the heatmap overlays on."""
    ts, xs, ys = _cursor_track(events)
    fps = 12
    frames = int(duration * fps) + 1
    frame_dir = Path(tempfile.mkdtemp())

    for i in range(frames):
        tf = i / fps
        j = max(0, bisect.bisect_right(ts, tf) - 1)
        cursor = (xs[j], ys[j]) if ts else None
        render_screen(cursor=cursor).save(frame_dir / f"f{i:05d}.png")

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

    _render_video(events, duration, session / "recording.webm")
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
