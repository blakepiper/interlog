"""Generate realistic synthetic sessions for trying InterLog without recording.

Produces the same on-disk shape as ``interlog record`` — an ``events.csv`` plus a
``metadata.json`` inside a session folder — but the events are *synthesized*, not
captured. Every demo session's metadata is flagged ``"synthetic": true`` so
generated data is never mistaken for a real participant.

The motion model bows each click-to-click path off the straight line by ``curl``
and adds small jitter, so path efficiency, the accuracy measures, typing rhythm,
and the interaction signals all take on believable, varied values. Sessions are
seeded, so a given ``(profile, seed)`` always yields the same data.
"""

import csv
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from interlog.recorder import EVENT_FIELDS, session_provenance

# Named behaviour profiles. Each tunes how many targets are clicked, how curved
# the pointer paths are, and how much typing/scrolling/frustration to mix in.
PROFILES = {
    "onboarding": dict(targets=14, curl=0.06, typing=8, scrolls=3),
    "checkout":   dict(targets=12, curl=0.16, rage=True, typing=6, scrolls=3),
    "power_user": dict(targets=18, curl=0.03, typing=10),
    "first_time": dict(targets=10, curl=0.22, rage=True, typing=5, scrolls=5),
}
DEFAULT_PROFILE = "checkout"

# Profile rotation used when generating several sessions for `analyze --batch`.
_ROTATION = list(PROFILES)

# Fixed reference date so a given (profile, seed) yields identical metadata too.
_EPOCH = datetime(2024, 1, 1)


def _row(t, event_type, **kw):
    row = {k: "" for k in EVENT_FIELDS}
    row["timestamp"] = round(t, 4)
    row["event_type"] = event_type
    for k, v in kw.items():
        row[k] = v
    return row


def _synthesize(rng, *, targets, curl, rage=False, typing=0, scrolls=0):
    """Build a plausible event stream; return ``(rows, duration_seconds)``."""
    rows = []
    t = 0.4  # brief settle before first action
    x, y = rng.randint(200, 600), rng.randint(200, 500)

    for i in range(targets):
        tx, ty = rng.randint(80, 1840), rng.randint(80, 1020)
        dist = math.hypot(tx - x, ty - y)
        steps = max(6, int(dist / 25))
        nx, ny = -(ty - y) / (dist or 1), (tx - x) / (dist or 1)  # perpendicular
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
                rows.append(_row(t, "key_press", key=key))
                t += 0.03
                rows.append(_row(t, "key_release", key=key))
            if rng.random() < 0.5:
                t += 0.3
                rows.append(_row(t, "key_press", key="Key.backspace"))

        t += rng.uniform(0.2, 1.1)  # think time between targets

    return rows, t


def write_session(parent_dir, name, *, profile=DEFAULT_PROFILE, seed=7):
    """Write one synthetic session folder under ``parent_dir``; return its path.

    The folder mirrors ``interlog record`` output (``events.csv`` +
    ``metadata.json``). Metadata is flagged ``synthetic`` and records the profile
    and seed, so the session is reproducible and clearly not a real capture.
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose from {sorted(PROFILES)}")

    rng = random.Random(seed)
    rows, duration = _synthesize(rng, **PROFILES[profile])

    session_dir = Path(parent_dir) / name
    session_dir.mkdir(parents=True, exist_ok=True)

    with open(session_dir / "events.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "session_name": name,
        "start_time": (_EPOCH + timedelta(seconds=seed)).isoformat(),
        "privacy_mode": False,
        "synthetic": True,
        "note": "Synthetic demo data generated by `interlog demo` — not a real capture.",
        "profile": profile,
        "seed": seed,
        "provenance": session_provenance(),
        "duration_seconds": round(duration, 3),
        "total_events": len(rows),
    }
    with open(session_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return session_dir


def generate(output_dir, *, sessions=1, seed=7):
    """Create one or more synthetic sessions under ``output_dir``.

    A single session uses the default profile and is named ``demo``; several
    sessions rotate through the profiles (named ``demo_01_<profile>`` …) so the
    set makes a meaningful ``interlog analyze --batch`` table. Returns the list
    of created session paths.
    """
    if sessions < 1:
        raise ValueError("sessions must be at least 1")

    if sessions == 1:
        return [write_session(output_dir, "demo", profile=DEFAULT_PROFILE, seed=seed)]

    paths = []
    for i in range(sessions):
        profile = _ROTATION[i % len(_ROTATION)]
        name = f"demo_{i + 1:02d}_{profile}"
        paths.append(write_session(output_dir, name, profile=profile, seed=seed + i))
    return paths
