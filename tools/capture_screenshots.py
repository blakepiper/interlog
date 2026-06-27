#!/usr/bin/env python3
"""Regenerate the README screenshots as crisp, version-controlled SVGs.

Run from the repo root:  python tools/capture_screenshots.py

Synthesizes a few varied sessions in a temp directory, then renders the real
``analyze`` and ``analyze --batch`` views through a *recording* rich console and
exports them to ``docs/img/*.svg``. Nothing here is mocked — the same code paths
the CLI uses produce the images, so the screenshots can't drift from reality.
"""

import math
import random
import tempfile
from pathlib import Path

from rich.console import Console

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from interlog.analyzer import InteractionAnalyzer, batch_analyze  # noqa: E402
from interlog.cli import render_batch_table  # noqa: E402
from interlog.recorder import EVENT_FIELDS  # noqa: E402

IMG_DIR = ROOT / "docs" / "img"


def _row(t, event_type, **kw):
    row = {k: "" for k in EVENT_FIELDS}
    row["timestamp"] = round(t, 4)
    row["event_type"] = event_type
    for k, v in kw.items():
        row[k] = v
    return row


def synth_session(rng, *, targets, curl, rage=False, typing=0, scrolls=0):
    """Build a plausible event stream and return (rows, duration).

    ``curl`` bows each mouse path off the straight line (0 = laser-straight),
    so path efficiency and the accuracy measures vary believably across sessions.
    """
    rows = []
    t = 0.4  # brief settle before first action
    x, y = rng.randint(200, 600), rng.randint(200, 500)

    for i in range(targets):
        tx, ty = rng.randint(80, 1840), rng.randint(80, 1020)
        dist = math.hypot(tx - x, ty - y)
        steps = max(6, int(dist / 25))
        # perpendicular unit vector for the bow
        nx, ny = -(ty - y) / (dist or 1), (tx - x) / (dist or 1)
        bow = curl * dist * rng.uniform(-1, 1)
        for s in range(1, steps + 1):
            f = s / steps
            arc = math.sin(math.pi * f) * bow
            px = x + (tx - x) * f + nx * arc + rng.uniform(-1.5, 1.5)
            py = y + (ty - y) * f + ny * arc + rng.uniform(-1.5, 1.5)
            t += rng.uniform(0.012, 0.02)
            rows.append(_row(t, "mouse_move", x=int(px), y=int(py)))
        x, y = tx, ty

        t += rng.uniform(0.05, 0.18)  # pre-click settle
        rows.append(_row(t, "mouse_down", x=x, y=y, button="Button.left"))
        t += 0.05
        rows.append(_row(t, "mouse_up", x=x, y=y, button="Button.left"))

        if rage and i == targets // 2:
            for _ in range(4):  # a frustrated burst on the same spot
                t += rng.uniform(0.12, 0.22)
                rows.append(_row(t, "mouse_down", x=x + rng.randint(-6, 6),
                                 y=y + rng.randint(-6, 6), button="Button.left"))
                t += 0.04
                rows.append(_row(t, "mouse_up", x=x, y=y, button="Button.left"))

        if scrolls and i % 2 == 0:
            for _ in range(scrolls):
                t += rng.uniform(0.15, 0.4)
                rows.append(_row(t, "scroll", x=x, y=y, dy=rng.choice([-2, -1, 1])))

        if typing and i % 3 == 1:
            for _ in range(typing):
                t += rng.uniform(0.08, 0.4)  # bursty inter-key timing
                key = rng.choice("the quick brown fox abcdefg ")
                rows.append(_row(t, "key_press", key=key or "e"))
                t += 0.03
                rows.append(_row(t, "key_release", key=key or "e"))
            if rng.random() < 0.5:
                t += 0.3
                rows.append(_row(t, "key_press", key="Key.backspace"))

        t += rng.uniform(0.2, 1.1)  # think time between targets

    return rows, t


def write_session(directory, rows):
    import csv
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        specs = {
            "P01_onboarding": dict(targets=14, curl=0.06, typing=8, scrolls=3),
            "P02_checkout":   dict(targets=12, curl=0.16, rage=True, typing=6, scrolls=3),
            "P03_power_user": dict(targets=18, curl=0.03, typing=10),
            "P04_first_time": dict(targets=10, curl=0.22, rage=True, typing=5, scrolls=5),
        }
        for name, kw in specs.items():
            rows, _ = synth_session(rng, **kw)
            write_session(data / name, rows)

        # Hero: single-session analyze summary.
        hero = InteractionAnalyzer(data / "P02_checkout" / "events.csv")
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
