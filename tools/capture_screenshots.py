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
    con = Console(record=True, width=66, highlight=False)
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

        # Heatmap PNG. The demo profiles are deliberately sparse, which makes a
        # thin heatmap; synthesize a denser movement field so the screenshot
        # shows what a real session's density map actually looks like.
        from interlog.heatmap import build_heatmap
        hero = write_hero_session(data / "hero")
        build_heatmap(hero, output=IMG_DIR / "heatmap.png", sigma=20)
        print(f"wrote {IMG_DIR / 'heatmap.png'}")

        # Cross-session comparison chart.
        _render_comparison_chart(rows, IMG_DIR / "compare.png")
        print(f"wrote {IMG_DIR / 'compare.png'}")


W, H = 1440, 810


def write_hero_session(session_dir, name="checkout-flow"):
    """One rich synthetic session that powers every screenshot: dense pointer
    movement (so the heatmap shows real heat) plus realistic clicks, typing, a
    scroll, and a rage burst. Returns the session path. Reproducible by seed."""
    import csv
    import json
    import random

    from interlog.recorder import EVENT_FIELDS

    session_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    dt = 0.008  # ~125 Hz pointer sampling
    # (x, y, dwell-weight, kind) — weight scales density so one zone reads hottest.
    hotspots = [
        (330, 240, 1.0, "field"),
        (1060, 250, 0.9, "field"),
        (760, 560, 2.1, "cta"),     # primary button — the hot focal point
        (300, 650, 0.85, "link"),
        (1130, 640, 1.1, "field"),
    ]
    rows, t = [], 0.0

    def clamp(v, hi):
        return int(min(hi - 1, max(0, v)))

    def add(event_type, **kw):
        rows.append({**{k: "" for k in EVENT_FIELDS},
                     "timestamp": round(t, 3), "event_type": event_type, **kw})

    def move(x, y):
        nonlocal t
        t += dt
        add("mouse_move", x=clamp(x, W), y=clamp(y, H))

    def click(x, y):
        nonlocal t
        t += 0.16
        add("mouse_down", x=clamp(x, W), y=clamp(y, H), button="Button.left")
        t += 0.05
        add("mouse_up", x=clamp(x, W), y=clamp(y, H), button="Button.left")

    def typ(text):
        nonlocal t
        for ch in text:
            t += rng.uniform(0.07, 0.2)
            add("key_press", key=ch)
            t += 0.03
            add("key_release", key=ch)

    cur = (hotspots[0][0], hotspots[0][1])
    for i, (hx, hy, weight, kind) in enumerate(hotspots):
        if i:  # a direct transit from the previous hotspot (keeps path efficient)
            for k in range(45):
                f = k / 45
                move(cur[0] + (hx - cur[0]) * f + rng.gauss(0, 6),
                     cur[1] + (hy - cur[1]) * f + rng.gauss(0, 6))
        click(hx, hy)  # click on arrival, so the transit segment scores directly
        # dwell densely around the target — these local moves feed the heatmap but
        # sit below the path-efficiency segment threshold, so they don't skew it
        for _ in range(int(1050 * weight)):
            move(rng.gauss(hx, 20), rng.gauss(hy, 17))
        for _ in range(int(300 * weight)):
            move(rng.gauss(hx, 52), rng.gauss(hy, 45))
        if kind == "field":
            typ(rng.choice(["jordan", "4111 1111", "checkout@mail"]))
        elif kind == "cta":
            t += 0.2
            add("scroll", x=hx, y=hy, dx=0, dy=-3)
        click(hx + rng.randint(-5, 5), hy + rng.randint(-5, 5))  # settle before leaving
        t += rng.uniform(0.3, 0.8)  # think time
        cur = (hx, hy)

    for k in range(45):  # move to the first field, then rage-click it
        f = k / 45
        move(cur[0] + (330 - cur[0]) * f + rng.gauss(0, 6),
             cur[1] + (240 - cur[1]) * f + rng.gauss(0, 6))
    for _ in range(4):  # a rage burst → red marker on heatmap and timeline
        click(330 + rng.randint(-6, 6), 240 + rng.randint(-6, 6))

    with open(session_dir / "events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    (session_dir / "metadata.json").write_text(json.dumps({
        "session_name": name,
        "start_time": "2024-01-01T10:15:00",
        "synthetic": True,
        "duration_seconds": round(t, 3),
        "total_events": len(rows),
        "capture_region": {"x": 0, "y": 0, "width": W, "height": H, "dpi_scale": 1.0},
    }))
    return session_dir


def _render_comparison_chart(rows, out_path):
    """A dark, brand-styled two-panel comparison of sessions (clicks/min + path
    efficiency) — the kind of visual the README's batch table only hints at."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = [r["session"] for r in rows]
    cpm = [r["clicks_per_minute"] for r in rows]
    eff = [r["mean_path_efficiency"] or 0 for r in rows]
    y = range(len(rows))

    bg, fg, dim, cyan, amber = "#0d0d0d", "#e2e8f0", "#64748b", "#22d3ee", "#fbbf24"
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 0.7 * len(rows) + 1.6), dpi=120)
    fig.patch.set_facecolor(bg)

    for ax, vals, title, color, fmt in (
        (ax1, cpm, "Clicks / min", cyan, "{:.0f}"),
        (ax2, eff, "Path efficiency", amber, "{:.2f}"),
    ):
        ax.set_facecolor(bg)
        ax.barh(list(y), vals, color=color, height=0.6, zorder=3)
        ax.set_title(title, color=fg, fontsize=13, pad=12, loc="left", fontweight="bold")
        ax.set_yticks(list(y))
        ax.set_yticklabels(names, color=fg, fontsize=10)
        ax.invert_yaxis()
        ax.tick_params(colors=dim, length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(axis="x", color="#1e293b", zorder=0)
        for yi, v in zip(y, vals):
            ax.text(v, yi, "  " + fmt.format(v), va="center", color=fg, fontsize=10)
        if ax is ax2:
            ax.set_xlim(0, 1)
            ax.set_yticklabels([])

    fig.suptitle("interlog analyze --batch", color=dim, fontsize=11,
                 x=0.012, ha="left", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, facecolor=bg, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
