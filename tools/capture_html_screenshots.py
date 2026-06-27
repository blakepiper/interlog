#!/usr/bin/env python3
"""Capture PNG screenshots of the HTML report and the synced viewer.

These two outputs are real web pages (the report is self-contained HTML; the
viewer syncs to a <video>), so rendering them needs a browser. That can't run in
plain CI, so this is a separate, optional tool from ``capture_screenshots.py``.

Setup (one time):

    pip install playwright
    playwright install chromium

Run from the repo root:

    python tools/capture_html_screenshots.py

Writes ``docs/img/report.png`` (and ``docs/img/viewer.png`` if a recording is
present). Uses the same synthetic session generator as ``interlog demo`` so the
screenshots come from the real code paths and can't drift from reality.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from interlog.demo import write_session  # noqa: E402
from interlog.report import build_report  # noqa: E402
from interlog.viewer import build_viewer  # noqa: E402

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
        session = write_session(Path(tmp), "P02_checkout", profile="checkout", seed=8)
        report = build_report(session)
        viewer = build_viewer(session / "events.csv", open_browser=False)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(device_scale_factor=2)
            _shoot(page, report.resolve().as_uri(), IMG_DIR / "report.png")
            _shoot(page, viewer.resolve().as_uri(), IMG_DIR / "viewer.png")
            browser.close()


if __name__ == "__main__":
    main()
