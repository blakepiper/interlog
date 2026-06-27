#!/usr/bin/env python3
"""Capture a PNG screenshot of the HTML report (docs/img/report.png).

The report is a real web page, so rendering it needs a browser — this can't run
in plain CI, so it's a separate, optional tool from ``capture_screenshots.py``.
The synced viewer is captured as an animation by ``capture_viewer_gif.py``.

Setup (one time):

    pip install playwright
    playwright install chromium

Run from the repo root:

    python tools/capture_html_screenshots.py

Renders from the same hero session as the other screenshots, via the real
``build_report`` code path, so it can't drift from reality.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from capture_screenshots import _add_screen_recording, write_hero_session  # noqa: E402
from interlog.heatmap import build_heatmap  # noqa: E402
from interlog.report import build_report  # noqa: E402

IMG_DIR = ROOT / "docs" / "img"


def _shoot(page, url, out_path, width=1200):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url)
    page.wait_for_timeout(400)  # let fonts/SVG settle
    page.screenshot(path=str(out_path), full_page=True)
    print(f"wrote {out_path}")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "playwright is not installed. Run:\n"
            "  pip install playwright && playwright install chromium"
        )

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        session = write_hero_session(Path(tmp) / "checkout-flow")
        _add_screen_recording(session)       # heatmap overlays the UI
        build_heatmap(session)               # so the report embeds it (no placeholder)
        report = build_report(session)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(device_scale_factor=2)
            _shoot(page, report.resolve().as_uri(), IMG_DIR / "report.png")
            browser.close()


if __name__ == "__main__":
    main()
