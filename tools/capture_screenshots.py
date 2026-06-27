#!/usr/bin/env python3
"""Regenerate the README screenshots as crisp, version-controlled SVGs.

Run from the repo root:  python tools/capture_screenshots.py

Uses the same synthetic-session generator as ``interlog demo`` to build a few
varied sessions in a temp directory, then renders the real ``analyze`` and
``analyze --batch`` views through a *recording* rich console and exports them to
``docs/img/*.svg``. Nothing is mocked — the same code paths the CLI uses produce
the images, so the screenshots can't drift from reality.
"""

import sys
import tempfile
from pathlib import Path

from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rich.text import Text  # noqa: E402

from interlog.analyzer import InteractionAnalyzer, batch_analyze  # noqa: E402
from interlog.branding import banner  # noqa: E402
from interlog.cli import render_batch_table  # noqa: E402
from interlog.demo import write_session  # noqa: E402

IMG_DIR = ROOT / "docs" / "img"

# Screenshot session name -> demo profile. The checkout session is the hero.
SESSIONS = {
    "P01_onboarding": "onboarding",
    "P02_checkout": "checkout",
    "P03_power_user": "power_user",
    "P04_first_time": "first_time",
}
HERO = "P02_checkout"


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # Banner: the exact colored logo the CLI prints, exported as an SVG so the
    # README header and the terminal art can never drift apart.
    con = Console(record=True, width=52, highlight=False)
    con.print(Text.from_ansi(banner(color=True)))
    (IMG_DIR / "banner.svg").write_text(
        con.export_svg(title="interlog"), encoding="utf-8")
    print(f"wrote {IMG_DIR / 'banner.svg'}")

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        for i, (name, profile) in enumerate(SESSIONS.items()):
            write_session(data, name, profile=profile, seed=7 + i)

        # Hero: single-session analyze summary.
        hero = InteractionAnalyzer(data / HERO / "events.csv")
        hero.load_events()
        hero.calculate_statistics()
        con = Console(record=True, width=84, highlight=False)
        hero.print_summary(console=con)
        (IMG_DIR / "analyze.svg").write_text(
            con.export_svg(title="interlog analyze"), encoding="utf-8")
        print(f"wrote {IMG_DIR / 'analyze.svg'}")

        # Cross-session aggregate table.
        rows = batch_analyze(data)
        con = Console(record=True, width=94, highlight=False)
        render_batch_table(con, rows, "study-2026")
        (IMG_DIR / "batch.svg").write_text(
            con.export_svg(title="interlog analyze --batch"), encoding="utf-8")
        print(f"wrote {IMG_DIR / 'batch.svg'}")


if __name__ == "__main__":
    main()
