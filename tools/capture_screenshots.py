#!/usr/bin/env python3
"""Regenerate the README screenshots as crisp, version-controlled SVGs.

Run from the repo root:  python tools/capture_screenshots.py

Uses the same synthetic-session generator as ``interlog demo`` to build a few
varied sessions in a temp directory, then renders the real ``analyze`` and
``analyze --batch`` views through a *recording* rich console and exports them to
``docs/img/*.svg``. Nothing is mocked — the same code paths the CLI uses produce
the images, so the screenshots can't drift from reality.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from rich.text import Text  # noqa: E402

from interlog.analyzer import InteractionAnalyzer, batch_analyze  # noqa: E402
from interlog.branding import banner  # noqa: E402
from interlog.cli import render_batch_table  # noqa: E402
from interlog.demo import write_session  # noqa: E402
from mock_screen import H, W, hotspots, render_screen  # noqa: E402

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
        _add_screen_recording(hero)   # so the heatmap overlays on the UI, not black
        build_heatmap(hero, output=IMG_DIR / "heatmap.png", sigma=20)
        print(f"wrote {IMG_DIR / 'heatmap.png'}")

        # Cross-session comparison chart.
        _render_comparison_chart(rows, IMG_DIR / "compare.png")
        print(f"wrote {IMG_DIR / 'compare.png'}")


def write_hero_session(session_dir, name="checkout-flow"):
    """One rich synthetic session that powers every screenshot. The user fills a
    checkout form (dense dwell on each field, feeding the heatmap), reviews the
    total, then rage-clicks an unresponsive Pay button. Movement clusters land on
    the ``mock_screen`` elements; transits stay direct so path efficiency is
    realistic. Reproducible by seed; returns the session path."""
    import csv
    import json
    import random

    from interlog.recorder import EVENT_FIELDS

    session_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    dt = 0.008  # ~125 Hz pointer sampling
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

    spots = hotspots()
    cur = (spots[0][0], spots[0][1])
    for i, (hx, hy, weight, kind, _id) in enumerate(spots):
        if i:  # a direct transit from the previous hotspot (keeps path efficient)
            for k in range(45):
                f = k / 45
                move(cur[0] + (hx - cur[0]) * f + rng.gauss(0, 6),
                     cur[1] + (hy - cur[1]) * f + rng.gauss(0, 6))
        click(hx, hy)  # click on arrival, so the transit segment scores directly
        # dwell densely around the target — these local moves feed the heatmap but
        # sit below the path-efficiency segment threshold, so they don't skew it
        for _ in range(int(1100 * weight)):
            move(rng.gauss(hx, 22), rng.gauss(hy, 18))
        for _ in range(int(320 * weight)):
            move(rng.gauss(hx, 56), rng.gauss(hy, 48))
        if kind == "field":
            typ(rng.choice(["jordan@lumen.io", "4242 4242", "04 / 27", "311"]))
        elif kind == "review":
            t += 0.2
            add("scroll", x=hx, y=hy, dx=0, dy=-3)
        if kind == "cta":
            for _ in range(3):  # Pay doesn't respond → rapid rage burst (4 total)
                click(hx + rng.randint(-7, 7), hy + rng.randint(-7, 7))
        else:
            click(hx + rng.randint(-5, 5), hy + rng.randint(-5, 5))  # settle
        t += rng.uniform(0.3, 0.8)  # think time
        cur = (hx, hy)

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


def _add_screen_recording(session_dir):
    """Drop a short MP4 of the checkout screen into the session so the heatmap
    overlays its density on the UI (not a black canvas). No-op without ffmpeg."""
    import json
    if not shutil.which("ffmpeg"):
        return
    meta = json.loads((session_dir / "metadata.json").read_text())
    dur = int(meta.get("duration_seconds", 60)) + 2
    bg = session_dir / "_screen.png"
    render_screen().save(bg)
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(bg), "-t", str(dur), "-r", "2",
         "-pix_fmt", "yuv420p", str(session_dir / "recording.mp4")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    bg.unlink(missing_ok=True)


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

    # InterLog instrument palette (matches the viewer/report scope).
    bg, fg, dim, signal, amber = "#0A0C10", "#E6EBF2", "#5C6A7D", "#46E0B8", "#FFB23E"
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 0.7 * len(rows) + 1.6), dpi=120)
    fig.patch.set_facecolor(bg)

    for ax, vals, title, color, fmt in (
        (ax1, cpm, "Clicks / min", signal, "{:.0f}"),
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
        ax.grid(axis="x", color="#1C2632", zorder=0)
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
