"""Statistical analysis of interaction logs.

Generates summary statistics and interaction-intensity data from a session's
events CSV.

Scope and caveats
-----------------
These metrics are deliberately descriptive: event counts, rates, timing, and a
small set of movement/keyboard measures with an established basis in the HCI
literature (keystroke inter-key intervals; pointer-path efficiency, cf.
MacKenzie, Kauppinen & Silfverberg, "Accuracy measures for evaluating computer
pointing devices", CHI 2001). They are not validated indices of any latent
construct such as "frustration" or "struggle", and are deliberately not combined
into a single composite score.

Pointer-path efficiency is built to be comparable across machines: it is a
dimensionless ratio (the device-pixel ratio cancels) measured on a trajectory
resampled to a fixed time base (``EFFICIENCY_RESAMPLE_HZ``), so it does not
depend on the native mouse-sampling rate. Raw pixel measures (distance, speed)
do scale with the device-pixel ratio and the sampling rate, so compare those
only within one capture environment. See ``capture_region`` / ``dpi_scale`` in
the session metadata.
"""

import csv
import json
import math
import statistics
import warnings
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from interlog import __version__

# Version of the summary.json structure (not the tool version). Bump on any
# breaking change to the export's shape so downstream readers can adapt.
SUMMARY_SCHEMA_VERSION = "1.0"

# Tunable thresholds for derived metrics.
IDLE_THRESHOLD_S = 2.0          # inter-event gaps longer than this count as idle
LONG_PAUSE_THRESHOLD_S = 2.0    # inter-event gaps longer than this are counted as long pauses
DOUBLE_CLICK_WINDOW_S = 0.3     # two clicks within this (and close in space) = double-click
DOUBLE_CLICK_DISTANCE_PX = 10
MIN_EFFICIENCY_SEGMENT_PX = 40  # ignore click-to-click moves shorter than this when scoring path efficiency
# Path length for efficiency is measured on a trajectory resampled to this fixed
# rate, so the result is comparable across machines whose native mouse-sampling
# rate is at least this (true of essentially all mice). See _resampled_length.
EFFICIENCY_RESAMPLE_HZ = 30.0
PRE_CLICK_RADIUS_PX = 8         # "near the target": dwell is measured within this radius of a click
PRE_CLICK_MAX_S = 2.0           # cap pre-click dwell so a long idle isn't counted as hesitation


def _resample_points(points, dt):
    """Resample a time-stamped polyline onto a fixed time step ``dt``.

    ``points`` is a list of ``(t, x, y)`` in non-decreasing time order. Positions
    are linearly interpolated onto an evenly spaced grid (t0, t0+dt, …, t1) and
    returned as ``(x, y)``. The fixed grid spacing makes fast and slow mice
    recording the same motion yield the same trajectory, which is what lets the
    path measures be comparable across machines. Returns [] when the path spans
    no time.
    """
    t0, t1 = points[0][0], points[-1][0]
    span = t1 - t0
    if span <= 0:
        return []

    # Evenly spaced target times from t0 up to (and including) t1.
    times = []
    k = 0
    while True:
        t = t0 + k * dt
        if t >= t1:
            break
        times.append(t)
        k += 1
    times.append(t1)

    out = []
    j = 0  # points[j], points[j+1] bracket the current target time
    for t in times:
        while j < len(points) - 2 and points[j + 1][0] <= t:
            j += 1
        ta, xa, ya = points[j]
        tb, xb, yb = points[j + 1]
        seg = tb - ta
        f = (t - ta) / seg if seg > 0 else 0.0
        f = 0.0 if f < 0 else 1.0 if f > 1 else f
        out.append((xa + (xb - xa) * f, ya + (yb - ya) * f))
    return out


def _resampled_length(points, dt):
    """Length of a time-stamped polyline resampled at a fixed time step ``dt``.

    Thin wrapper over :func:`_resample_points`: sums segment lengths along the
    fixed-rate trajectory, so the result does not depend on the native sampling
    rate (see _resample_points for why).
    """
    resampled = _resample_points(points, dt)
    return sum(
        math.hypot(b[0] - a[0], b[1] - a[1])
        for a, b in zip(resampled, resampled[1:])
    )


def _diffs(xs):
    """Consecutive first differences of a sequence."""
    return [b - a for a, b in zip(xs, xs[1:])]


def _sign_changes(xs):
    """Number of sign changes in a sequence, ignoring zeros.

    A run of zeros does not count as a change; the sign is compared against the
    most recent non-zero value, so a path that touches the axis and continues in
    the same direction is not counted as a crossing.
    """
    count = 0
    prev = 0
    for x in xs:
        s = (x > 0) - (x < 0)  # -1, 0, or 1
        if s == 0:
            continue
        if prev != 0 and s != prev:
            count += 1
        prev = s
    return count


def base_prefix(events_file):
    """Filename prefix for derived outputs.

    Returns "" for a session-folder layout (``events.csv`` -> ``summary.csv``)
    and "<name>_" for legacy/arbitrary files (``p01_events.csv`` -> ``p01_summary.csv``).
    """
    stem = Path(events_file).stem
    if stem.endswith("_events"):
        stem = stem[: -len("_events")]
    elif stem == "events":
        stem = ""
    return f"{stem}_" if stem else ""


def read_session_metadata(events_file):
    """Load a session's ``metadata.json`` (or legacy ``<name>_metadata.json``).

    Returns the parsed dict, or ``{}`` if no readable metadata sits beside the
    events file. Shared by the viewer and the JSON export so both resolve session
    metadata the same way.
    """
    events_file = Path(events_file)
    parent = events_file.parent
    candidates = [parent / "metadata.json"]
    name = base_prefix(events_file).rstrip("_")
    if name:
        candidates.append(parent / f"{name}_metadata.json")
    for meta_file in candidates:
        try:
            return json.loads(meta_file.read_text())
        except (OSError, ValueError):
            continue
    return {}


def load_event_rows(events_file):
    """Read a session's events CSV, coercing numeric fields in place.

    A non-numeric cell is left as its original string rather than aborting the
    whole load. Shared by the analyzer and the heatmap so both read the same way.
    """
    events = []
    with open(events_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for field in ("timestamp", "x", "y", "dx", "dy"):
                if row.get(field):
                    try:
                        row[field] = float(row[field]) if field == "timestamp" else int(float(row[field]))
                    except (ValueError, TypeError):
                        pass
            events.append(row)
    return events


def mouse_down_clicks(events):
    """Time-ordered mouse-down clicks as ``{timestamp, x, y}`` dicts."""
    return [
        {"timestamp": e["timestamp"], "x": e.get("x"), "y": e.get("y")}
        for e in events
        if e["event_type"] == "mouse_down"
    ]


def detect_rage_clicks(clicks, time_window=1.0, distance_threshold=50):
    """Detect rage-click bursts: 3+ rapid clicks within a small area.

    Rage clicks are an established UX-analytics signal for a broken or
    unresponsive target. Each burst is counted once: clicks attributed to a
    burst are consumed and not reused as the seed of another.

    Args:
        clicks: Click events with timestamp/x/y, time-ordered.
        time_window: Window in seconds over which clicks are grouped.
        distance_threshold: Max distance in pixels to count as the same area.

    Returns:
        One dict per burst with the seed click plus ``click_count`` and
        ``timestamps`` (every click in the burst).
    """
    bursts = []
    i = 0
    n = len(clicks)
    while i < n - 1:
        window = [clicks[i]]
        j = i + 1
        while j < n and clicks[j]["timestamp"] - clicks[i]["timestamp"] <= time_window:
            window.append(clicks[j])
            j += 1

        if len(window) < 3:
            i += 1
            continue

        first = window[0]
        same_area = all(
            first["x"] is not None and c["x"] is not None
            and math.hypot(c["x"] - first["x"], c["y"] - first["y"]) <= distance_threshold
            for c in window[1:]
        )
        if same_area:
            bursts.append({
                "timestamp": first["timestamp"],
                "x": first["x"],
                "y": first["y"],
                "click_count": len(window),
                "timestamps": [c["timestamp"] for c in window],
            })
            i = j  # consume the whole burst so it is not recounted
        else:
            i += 1

    return bursts


class InteractionAnalyzer:
    """Analyzes interaction logs and generates statistics."""

    def __init__(self, events_file):
        """
        Initialize analyzer with events file.

        Args:
            events_file: Path to the events CSV file.
        """
        self.events_file = Path(events_file)
        self.events = []
        self.stats = {}

    def load_events(self):
        """Load events from CSV file."""
        self.events = load_event_rows(self.events_file)

    def calculate_statistics(self):
        """Calculate summary statistics from events."""
        if not self.events:
            return self.stats

        # Basic counts
        event_counts = defaultdict(int)
        for event in self.events:
            event_counts[event["event_type"]] += 1

        # Session duration
        timestamps = [e["timestamp"] for e in self.events]
        min_time = min(timestamps)
        duration = max(timestamps) - min_time

        # Click locations for rage click detection
        clicks = mouse_down_clicks(self.events)
        rage_clicks = detect_rage_clicks(clicks)

        # Pauses (gaps between consecutive events)
        pauses = [
            self.events[i]["timestamp"] - self.events[i - 1]["timestamp"]
            for i in range(1, len(self.events))
        ]
        longest_pause = max(pauses) if pauses else 0
        avg_pause = sum(pauses) / len(pauses) if pauses else 0

        # Total interactions (excluding mouse moves)
        total_interactions = sum(
            1 for e in self.events if e["event_type"] != "mouse_move"
        )

        # Rates (per minute)
        duration_minutes = duration / 60 if duration > 0 else 0
        clicks_per_minute = (
            event_counts.get("mouse_down", 0) / duration_minutes if duration_minutes > 0 else 0
        )
        actions_per_minute = (
            total_interactions / duration_minutes if duration_minutes > 0 else 0
        )
        keypresses_per_minute = (
            event_counts.get("key_press", 0) / duration_minutes if duration_minutes > 0 else 0
        )

        # Scroll analysis
        total_scroll_distance = sum(
            abs(e.get("dy", 0) or 0)
            for e in self.events
            if e["event_type"] == "scroll"
        )

        # Pointer movement: total path length and continuous-motion speed.
        moves = [
            e for e in self.events
            if e["event_type"] == "mouse_move" and isinstance(e.get("x"), int)
        ]
        mouse_distance = 0.0
        move_time = 0.0
        for prev, cur in zip(moves, moves[1:]):
            mouse_distance += math.hypot(cur["x"] - prev["x"], cur["y"] - prev["y"])
            dt = cur["timestamp"] - prev["timestamp"]
            if 0 < dt <= 1.0:  # only count continuous motion, not idle gaps
                move_time += dt
        pointer_speed = mouse_distance / move_time if move_time > 0 else 0
        mouse_distance_per_minute = (
            mouse_distance / duration_minutes if duration_minutes > 0 else 0
        )

        # Timing: idle vs active time, median pause, long pauses, time-to-first-action.
        idle_time = sum(g for g in pauses if g > IDLE_THRESHOLD_S)
        active_time = max(0.0, duration - idle_time)
        median_pause = statistics.median(pauses) if pauses else 0
        long_pauses = sum(1 for g in pauses if g > LONG_PAUSE_THRESHOLD_S)
        first_interaction = next(
            (e["timestamp"] for e in self.events if e["event_type"] != "mouse_move"),
            None,
        )
        ttfi = first_interaction - min_time if first_interaction is not None else 0

        # Click quality, pointer-path efficiency, and keyboard dynamics.
        double_clicks = self._count_double_clicks(clicks)
        path_efficiency = self._movement_efficiency()
        kbd = self._keyboard_metrics(duration_minutes)

        # Movement accuracy (MacKenzie CHI2001), coordination, and spatial spread.
        accuracy = self._accuracy_measures() or {}
        dispersion = self._click_dispersion() or {}
        modality_switches = self._modality_switches()
        modality_switches_per_minute = (
            modality_switches / duration_minutes if duration_minutes > 0 else 0
        )

        self.stats = {
            "session_duration_seconds": duration,
            "session_duration_formatted": str(timedelta(seconds=int(duration))),
            "total_events": len(self.events),
            "total_interactions": total_interactions,
            "total_mouse_moves": event_counts.get("mouse_move", 0),
            "total_clicks": event_counts.get("mouse_down", 0),
            "total_scrolls": event_counts.get("scroll", 0),
            "total_keypresses": event_counts.get("key_press", 0),
            "total_drags": event_counts.get("drag", 0),
            "clicks_per_minute": round(clicks_per_minute, 2),
            "actions_per_minute": round(actions_per_minute, 2),
            "keypresses_per_minute": round(keypresses_per_minute, 2),
            "rage_clicks_detected": len(rage_clicks),
            "longest_pause_seconds": round(longest_pause, 2),
            "average_pause_seconds": round(avg_pause, 3),
            "total_scroll_distance": total_scroll_distance,
            "total_mouse_distance_px": round(mouse_distance, 1),
            "mouse_distance_per_minute": round(mouse_distance_per_minute, 1),
            "mean_pointer_speed_px_s": round(pointer_speed, 1),
            "mean_path_efficiency": path_efficiency,
            "idle_time_seconds": round(idle_time, 2),
            "active_time_seconds": round(active_time, 2),
            "median_pause_seconds": round(median_pause, 3),
            "long_pauses": long_pauses,
            "time_to_first_interaction_seconds": round(ttfi, 2),
            "double_clicks": double_clicks,
            "scroll_reversals": self._scroll_reversals(),
            "pre_click_dwell_seconds": self._pre_click_dwell(),
            "modality_switches": modality_switches,
            "modality_switches_per_minute": round(modality_switches_per_minute, 2),
            "mean_interkey_interval_seconds": kbd["mean_interkey_interval_seconds"],
            "interkey_interval_sd_seconds": kbd["interkey_interval_sd_seconds"],
            "interkey_interval_cv": kbd["interkey_interval_cv"],
            "typing_chars_per_minute": kbd["typing_chars_per_minute"],
            "backspaces": kbd["backspaces"],
            "correction_rate": kbd["correction_rate"],
            # Movement accuracy (MacKenzie CHI2001); None-keys absent when no
            # qualifying click-to-click movement existed.
            "movement_offset_px": accuracy.get("movement_offset_px"),
            "movement_error_px": accuracy.get("movement_error_px"),
            "movement_variability_px": accuracy.get("movement_variability_px"),
            "task_axis_crossings": accuracy.get("task_axis_crossings"),
            "movement_direction_changes": accuracy.get("movement_direction_changes"),
            "orthogonal_direction_changes": accuracy.get("orthogonal_direction_changes"),
            # Spatial spread of clicks.
            "click_spread_px": dispersion.get("click_spread_px"),
            "click_bbox_width_px": dispersion.get("click_bbox_width_px"),
            "click_bbox_height_px": dispersion.get("click_bbox_height_px"),
        }

        return self.stats

    def _count_double_clicks(self, clicks):
        """Count consecutive click pairs that are close in time and space."""
        count = 0
        i = 0
        while i < len(clicks) - 1:
            a, b = clicks[i], clicks[i + 1]
            close_in_time = (b["timestamp"] - a["timestamp"]) <= DOUBLE_CLICK_WINDOW_S
            same_spot = (
                a["x"] is not None and b["x"] is not None
                and math.hypot(b["x"] - a["x"], b["y"] - a["y"]) <= DOUBLE_CLICK_DISTANCE_PX
            )
            if close_in_time and same_spot:
                count += 1
                i += 2  # consume both clicks of the pair
            else:
                i += 1
        return count

    def _click_segments(self):
        """Yield qualifying click→click pointer movements.

        Each yielded item is ``(start, end, path)`` where ``start``/``end`` are
        the two clicks as ``(t, x, y)`` and ``path`` is the pointer trajectory
        between them (the two clicks plus every intervening ``mouse_move``), in
        time order. Segments shorter than ``MIN_EFFICIENCY_SEGMENT_PX`` (jitter
        dominates) or with no sampled intervening movement are skipped.

        This is the shared primitive for every pointer-path measure (efficiency
        and the MacKenzie accuracy measures), so they all score the same set of
        movements.
        """
        clicks = [
            (e["timestamp"], e["x"], e["y"])
            for e in self.events
            if e["event_type"] == "mouse_down" and isinstance(e.get("x"), int)
        ]
        moves = [
            (e["timestamp"], e["x"], e["y"])
            for e in self.events
            if e["event_type"] == "mouse_move" and isinstance(e.get("x"), int)
        ]
        if len(clicks) < 2 or not moves:
            return

        mi = 0  # advances monotonically through moves as click segments progress
        for start, end in zip(clicks, clicks[1:]):
            (t0, x0, y0), (t1, x1, y1) = start, end
            if math.hypot(x1 - x0, y1 - y0) < MIN_EFFICIENCY_SEGMENT_PX:
                continue
            while mi < len(moves) and moves[mi][0] <= t0:
                mi += 1
            path = [(t0, x0, y0)]
            k = mi
            while k < len(moves) and moves[k][0] < t1:
                path.append(moves[k])
                k += 1
            path.append((t1, x1, y1))
            if len(path) < 3:
                continue  # no intervening movement sampled; nothing to score
            yield start, end, path

    def _movement_efficiency(self):
        """Mean pointer-path efficiency between consecutive clicks, in (0, 1].

        For each click-to-click segment, efficiency is the straight-line
        distance between the two clicks divided by the actual length of the
        pointer path travelled between them (1.0 = a perfectly direct move).
        This is a standard pointer-movement quality measure (cf. MacKenzie,
        Kauppinen & Silfverberg, CHI 2001). It is a dimensionless ratio measured
        on a resampled trajectory, so it is comparable across machines (see the
        module docstring).

        Returns None when no segment is long enough to score.
        """
        dt = 1.0 / EFFICIENCY_RESAMPLE_HZ
        ratios = []
        for (_, x0, y0), (_, x1, y1), path in self._click_segments():
            straight = math.hypot(x1 - x0, y1 - y0)
            actual = _resampled_length(path, dt)
            if actual > 0:
                ratios.append(min(1.0, straight / actual))

        if not ratios:
            return None
        return round(sum(ratios) / len(ratios), 3)

    def _accuracy_measures(self):
        """MacKenzie/Kauppinen/Silfverberg (CHI 2001) accuracy measures.

        For each click→click movement the straight line from the start click to
        the end click is the *task axis*. The pointer path is resampled to a
        fixed time base (so the counts below do not inflate with the native mouse
        sampling rate), then each resampled point is decomposed into distance
        *along* the axis and signed perpendicular distance *from* it. Reported as
        the mean over all qualifying movements:

        * ``movement_offset_px`` (MO) — mean signed perpendicular deviation (a
          consistent bias to one side of the ideal line).
        * ``movement_error_px`` (ME) — mean absolute perpendicular deviation.
        * ``movement_variability_px`` (MV) — SD of perpendicular deviation.
        * ``task_axis_crossings`` (TAC) — times the path crosses the axis.
        * ``movement_direction_changes`` (MDC) — reversals *along* the axis
          (backtracking toward the start).
        * ``orthogonal_direction_changes`` (ODC) — reversals *across* the axis.

        MO/ME/MV are perpendicular distances in pixels, so they scale with the
        device-pixel ratio — compare them only within one capture environment
        (see ``capture_region.dpi_scale``). The three counts are dimensionless.
        Target re-entries (TRE) from the same paper are intentionally omitted:
        they require a defined target width, which free-form logs do not carry.

        Returns None when no segment qualifies.
        """
        dt = 1.0 / EFFICIENCY_RESAMPLE_HZ
        mo, me, mv = [], [], []
        tac, mdc, odc = [], [], []

        for (_, x0, y0), (_, x1, y1), path in self._click_segments():
            pts = _resample_points(path, dt)
            if len(pts) < 3:
                continue
            # Unit vector along the task axis (start click -> end click).
            ax, ay = x1 - x0, y1 - y0
            axis = math.hypot(ax, ay)
            if axis == 0:
                continue
            ux, uy = ax / axis, ay / axis

            along, perp = [], []
            for px, py in pts:
                vx, vy = px - x0, py - y0
                along.append(vx * ux + vy * uy)      # projection onto the axis
                perp.append(vx * (-uy) + vy * ux)    # signed distance from axis

            mo.append(sum(perp) / len(perp))
            me.append(sum(abs(p) for p in perp) / len(perp))
            mv.append(statistics.pstdev(perp) if len(perp) > 1 else 0.0)
            tac.append(_sign_changes(perp))                  # crossings of the axis
            mdc.append(_sign_changes(_diffs(along)))         # reversals along the axis
            odc.append(_sign_changes(_diffs(perp)))          # reversals across the axis

        if not mo:
            return None

        def _mean(xs):
            return sum(xs) / len(xs)

        return {
            "movement_offset_px": round(_mean(mo), 2),
            "movement_error_px": round(_mean(me), 2),
            "movement_variability_px": round(_mean(mv), 2),
            "task_axis_crossings": round(_mean(tac), 2),
            "movement_direction_changes": round(_mean(mdc), 2),
            "orthogonal_direction_changes": round(_mean(odc), 2),
        }

    def _keyboard_metrics(self, duration_minutes):
        """Inter-key timing and (when not in privacy mode) typing/correction rates."""
        presses = [e for e in self.events if e["event_type"] == "key_press"]
        intervals = [b["timestamp"] - a["timestamp"] for a, b in zip(presses, presses[1:])]
        mean_interkey = statistics.mean(intervals) if intervals else 0

        # Variability of inter-key timing (rhythm / planning pauses). The
        # coefficient of variation (SD / mean) is dimensionless, so it is
        # comparable across people and machines; it needs no key identity and so
        # survives privacy mode. Reported as None when there are too few presses.
        interkey_sd = statistics.stdev(intervals) if len(intervals) > 1 else None
        interkey_cv = (
            round(interkey_sd / mean_interkey, 3)
            if interkey_sd is not None and mean_interkey > 0
            else None
        )

        base = {
            "mean_interkey_interval_seconds": round(mean_interkey, 3),
            "interkey_interval_sd_seconds": round(interkey_sd, 3) if interkey_sd is not None else None,
            "interkey_interval_cv": interkey_cv,
        }

        # Key identities are unavailable in privacy mode, so char/correction
        # metrics are reported as None rather than guessed.
        redacted = any(e.get("key") == "[REDACTED]" for e in presses)
        if redacted or not presses:
            return {
                **base,
                "typing_chars_per_minute": None,
                "backspaces": None,
                "correction_rate": None,
            }

        backspaces = sum(
            1 for e in presses if e.get("key") in ("Key.backspace", "Key.delete")
        )
        char_keys = sum(1 for e in presses if len(str(e.get("key") or "")) == 1)
        cpm = char_keys / duration_minutes if duration_minutes > 0 else 0
        return {
            **base,
            "typing_chars_per_minute": round(cpm, 2),
            "backspaces": backspaces,
            "correction_rate": round(backspaces / len(presses), 3),
        }

    def _modality_switches(self):
        """Count transitions between mouse and keyboard activity (KLM "homing").

        Each intentional action is classed as mouse (click, scroll, drag) or
        keyboard (key press); a switch is a class change between consecutive
        actions. Mouse moves and key/button releases are ignored — they are not
        deliberate task actions. Grounded in the homing operator of the Keystroke
        -Level Model (Card, Moran & Newell, 1980).
        """
        mouse = {"mouse_down", "scroll", "drag"}
        seq = [
            "m" if e["event_type"] in mouse else "k"
            for e in self.events
            if e["event_type"] in mouse or e["event_type"] == "key_press"
        ]
        return sum(1 for a, b in zip(seq, seq[1:]) if a != b)

    def _scroll_reversals(self):
        """Number of times the scroll direction flips (up→down or down→up).

        A descriptive signal of searching or re-reading: a long document read
        once scrolls one way; hunting for something reverses repeatedly. Computed
        from the sign of scroll ``dy``; zero-delta scrolls are ignored.
        """
        dys = [
            e.get("dy", 0) or 0
            for e in self.events
            if e["event_type"] == "scroll"
        ]
        return _sign_changes(dys)

    def _pre_click_dwell(self):
        """Mean dwell near the target just before clicking, in seconds.

        For each click, scan its preceding ``mouse_move`` samples backward until
        the pointer is more than ``PRE_CLICK_RADIUS_PX`` from the click point;
        the dwell is the time from that arrival to the click, capped at
        ``PRE_CLICK_MAX_S`` so a long idle before clicking is not counted as
        hesitation. A descriptive uncertainty/settling signal — longer dwell
        suggests more time spent homing in on or hesitating over the target.

        Returns None when no click has a preceding sampled approach.
        """
        moves = [
            (e["timestamp"], e["x"], e["y"])
            for e in self.events
            if e["event_type"] == "mouse_move" and isinstance(e.get("x"), int)
        ]
        clicks = [
            (e["timestamp"], e["x"], e["y"])
            for e in self.events
            if e["event_type"] == "mouse_down" and isinstance(e.get("x"), int)
        ]
        if not moves or not clicks:
            return None

        dwells = []
        mi = 0
        for ct, cx, cy in clicks:
            # Advance to the moves that precede this click.
            while mi < len(moves) and moves[mi][0] <= ct:
                mi += 1
            arrival = None
            # Walk backward through the approach while inside the radius.
            for k in range(mi - 1, -1, -1):
                mt, mx, my = moves[k]
                if ct - mt > PRE_CLICK_MAX_S:
                    break
                if math.hypot(mx - cx, my - cy) <= PRE_CLICK_RADIUS_PX:
                    arrival = mt
                else:
                    break
            if arrival is not None:
                dwells.append(ct - arrival)

        if not dwells:
            return None
        return round(sum(dwells) / len(dwells), 3)

    def _click_dispersion(self):
        """Spatial spread of clicks: RMS distance from the centroid and bbox.

        Summarizes *where* on screen interaction happened — a scalar companion to
        the heatmap. ``click_spread_px`` is the root-mean-square distance of
        clicks from their centroid; the bounding box gives the extent. All are
        pixel measures, so compare them only within one capture environment (see
        ``capture_region.dpi_scale``). Returns None with fewer than two clicks.
        """
        pts = [
            (e["x"], e["y"])
            for e in self.events
            if e["event_type"] == "mouse_down" and isinstance(e.get("x"), int)
        ]
        if len(pts) < 2:
            return None
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        spread = math.sqrt(sum((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in pts) / len(pts))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return {
            "click_spread_px": round(spread, 1),
            "click_bbox_width_px": max(xs) - min(xs),
            "click_bbox_height_px": max(ys) - min(ys),
        }

    def calculate_intensity(self, bucket_size=5.0):
        """
        Calculate interaction intensity over time.

        Args:
            bucket_size: Time bucket size in seconds.

        Returns:
            List of time buckets with interaction counts.
        """
        if bucket_size <= 0:
            raise ValueError("bucket_size must be greater than 0")

        if not self.events:
            return []

        timestamps = [e["timestamp"] for e in self.events]
        min_time, max_time = min(timestamps), max(timestamps)
        n_buckets = int((max_time - min_time) / bucket_size) + 1

        buckets = [
            {
                "time_start": round(min_time + i * bucket_size, 2),
                "time_end": round(min_time + (i + 1) * bucket_size, 2),
                "total_interactions": 0,
                "clicks": 0,
                "scrolls": 0,
                "keypresses": 0,
            }
            for i in range(n_buckets)
        ]
        field = {"mouse_down": "clicks", "scroll": "scrolls", "key_press": "keypresses"}
        for e in self.events:
            if e["event_type"] == "mouse_move":
                continue
            idx = min(int((e["timestamp"] - min_time) / bucket_size), n_buckets - 1)
            buckets[idx]["total_interactions"] += 1
            key = field.get(e["event_type"])
            if key:
                buckets[idx][key] += 1

        return buckets

    def save_summary(self, output_file=None):
        """Save summary statistics to CSV file."""
        if output_file is None:
            output_file = self.events_file.parent / f"{base_prefix(self.events_file)}summary.csv"
        else:
            output_file = Path(output_file)

        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            for key, value in self.stats.items():
                writer.writerow([key, value])

        return output_file

    def build_summary_export(self, metadata=None):
        """Assemble the structured, self-describing summary for ``summary.json``.

        Unlike ``summary.csv`` (every value stringified, no context), this keeps
        native JSON types and carries the session's provenance and a schema
        version, so a downstream reader (pandas/R) can interpret the numbers and
        know whether two sessions are comparable. ``metadata`` defaults to the
        session's ``metadata.json``; pass a dict to override.
        """
        if not self.stats:
            self.calculate_statistics()
        if metadata is None:
            metadata = read_session_metadata(self.events_file)

        session = {
            "name": metadata.get("session_name") or self.events_file.parent.name,
            "privacy_mode": metadata.get("privacy_mode"),
            "synthetic": metadata.get("synthetic", False),
            "duration_seconds": self.stats.get("session_duration_seconds"),
            "provenance": metadata.get("provenance"),
            "capture_region": metadata.get("capture_region"),
        }
        return {
            "schema": "interlog/summary",
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "tool_version": __version__,
            "session": session,
            "metrics": dict(self.stats),
            "metrics_notes": {
                "comparability": (
                    "Pixel-based metrics (suffix _px) scale with "
                    "session.capture_region.dpi_scale; compare them only within one "
                    "capture environment. Dimensionless and time-based metrics are "
                    "cross-machine comparable. See docs/METRICS.md."
                ),
                "nulls": (
                    "null means a metric was undefined for this session (e.g. no "
                    "qualifying click-to-click movement, or privacy mode)."
                ),
            },
        }

    def save_summary_json(self, output_file=None, metadata=None):
        """Write the structured summary (see ``build_summary_export``) as JSON."""
        if output_file is None:
            output_file = self.events_file.parent / f"{base_prefix(self.events_file)}summary.json"
        else:
            output_file = Path(output_file)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.build_summary_export(metadata), f, indent=2)

        return output_file

    def save_intensity(self, output_file=None, bucket_size=5.0):
        """Save interaction intensity data to CSV file."""
        if output_file is None:
            output_file = self.events_file.parent / f"{base_prefix(self.events_file)}intensity.csv"
        else:
            output_file = Path(output_file)

        buckets = self.calculate_intensity(bucket_size)

        with open(output_file, "w", newline="") as f:
            if buckets:
                writer = csv.DictWriter(f, fieldnames=buckets[0].keys())
                writer.writeheader()
                writer.writerows(buckets)

        return output_file

    def _sparkline(self, bucket_size=5.0, width=52):
        """Return a one-line Unicode block sparkline of interaction intensity."""
        buckets = self.calculate_intensity(bucket_size)
        if not buckets:
            return ""
        values = [b["total_interactions"] for b in buckets]
        if len(values) > width:
            # downsample: average each slice of buckets into one cell
            step = len(values) / width
            means = []
            for i in range(width):
                slice_ = values[int(i * step):int((i + 1) * step)] or [0]
                means.append(sum(slice_) / len(slice_))
            values = means
        blocks = " ▁▂▃▄▅▆▇█"
        max_v = max(values) or 1
        return "".join(blocks[min(8, int(v / max_v * 8))] for v in values)

    def print_summary(self, console=None):
        """Print summary statistics to console using rich.

        ``console`` lets a caller pass a configured Console (e.g. a recording one
        for screenshot capture); defaults to a fresh non-highlighting console.
        """
        from rich.console import Console
        from rich.table import Table
        from rich.columns import Columns

        if console is None:
            console = Console(highlight=False)
        s = self.stats
        if not s:
            console.print("[dim]No statistics calculated[/dim]")
            return

        console.print()
        console.rule("[bold cyan]InterLog[/bold cyan]", style="cyan dim")
        console.print(
            f"  [bold white]{s['session_duration_formatted']}[/bold white]"
            f"  [dim]·[/dim]  [cyan]{s['total_events']:,}[/cyan] events"
            f"  [dim]·[/dim]  [cyan]{s['total_interactions']:,}[/cyan] interactions"
        )
        console.print()

        # Left column: Interactions
        t_events = Table(box=None, show_header=True, pad_edge=False,
                         padding=(0, 3, 0, 2), show_edge=False)
        t_events.add_column("Interactions", style="bold white", min_width=13)
        t_events.add_column("", justify="right", style="cyan", min_width=7)
        t_events.add_row("Mouse Moves", f"{s['total_mouse_moves']:,}")
        t_events.add_row("Clicks", f"{s['total_clicks']:,}")
        t_events.add_row("Scrolls", f"{s['total_scrolls']:,}")
        t_events.add_row("Keypresses", f"{s['total_keypresses']:,}")
        t_events.add_row("Drags", f"{s['total_drags']:,}")

        # Right column: Rates per minute
        t_rates = Table(box=None, show_header=True, pad_edge=False,
                        padding=(0, 3, 0, 2), show_edge=False)
        t_rates.add_column("Per Minute", style="bold white", min_width=13)
        t_rates.add_column("", justify="right", style="cyan", min_width=7)
        t_rates.add_row("Clicks", f"{s['clicks_per_minute']:.1f}")
        t_rates.add_row("Actions", f"{s['actions_per_minute']:.1f}")
        t_rates.add_row("Keypresses", f"{s['keypresses_per_minute']:.1f}")

        console.print(Columns([t_events, t_rates], equal=False, expand=False, padding=(0, 2)))
        console.print()

        # Left: Pointer
        t_ptr = Table(box=None, show_header=True, pad_edge=False,
                      padding=(0, 3, 0, 2), show_edge=False)
        t_ptr.add_column("Pointer", style="bold white", min_width=16)
        t_ptr.add_column("", justify="right", style="cyan", min_width=12)
        t_ptr.add_row("Distance", f"{s['total_mouse_distance_px']:,.0f} px")
        t_ptr.add_row("Speed", f"{s['mean_pointer_speed_px_s']:,.0f} px/s")
        eff = s.get("mean_path_efficiency")
        t_ptr.add_row("Path efficiency",
                      f"{eff:.2f}" if eff is not None else "[dim]n/a[/dim]")
        me = s.get("movement_error_px")
        t_ptr.add_row("Movement error",
                      f"{me:.1f} px" if me is not None else "[dim]n/a[/dim]")
        t_ptr.add_row("Active / Idle",
                      f"{s['active_time_seconds']:.1f}s / {s['idle_time_seconds']:.1f}s")
        t_ptr.add_row("Time to First", f"{s['time_to_first_interaction_seconds']:.2f}s")

        # Right: Keyboard
        t_kbd = Table(box=None, show_header=True, pad_edge=False,
                      padding=(0, 3, 0, 2), show_edge=False)
        t_kbd.add_column("Keyboard", style="bold white", min_width=16)
        t_kbd.add_column("", justify="right", style="cyan", min_width=12)
        cpm = s["typing_chars_per_minute"]
        if cpm is None:
            # None means either privacy mode (keys redacted) or simply no typing;
            # distinguish them so a no-typing session isn't mislabelled.
            label = "[dim]none[/dim]" if s["total_keypresses"] == 0 else "[dim]privacy mode[/dim]"
            t_kbd.add_row("Typing", label)
        else:
            t_kbd.add_row("Typing speed", f"{cpm:.0f} cpm")
            t_kbd.add_row("Corrections",
                          f"{s['backspaces']} ({s['correction_rate'] * 100:.1f}%)")
        t_kbd.add_row("Inter-key interval", f"{s['mean_interkey_interval_seconds']:.3f}s")
        cv = s.get("interkey_interval_cv")
        t_kbd.add_row("Inter-key rhythm (CV)",
                      f"{cv:.2f}" if cv is not None else "[dim]n/a[/dim]")

        console.print(Columns([t_ptr, t_kbd], equal=False, expand=False, padding=(0, 2)))
        console.print()

        # Interaction signals (descriptive counts — not a diagnosis)
        console.rule("[bold white]Interaction Signals[/bold white]", style="dim")

        def _val(n, warn_gt=0, bad_gt=None, fmt=str):
            v = fmt(n)
            if bad_gt is not None and n > bad_gt:
                return f"[red]{v}[/red]"
            if n > warn_gt:
                return f"[yellow]{v}[/yellow]"
            return f"[green]{v}[/green]"

        rage = s["rage_clicks_detected"]
        double = s["double_clicks"]
        longp = s["long_pauses"]
        console.print(
            f"  Rage-click bursts  {_val(rage, bad_gt=1)}   "
            f"Double clicks  {_val(double, warn_gt=3)}   "
            f"Long pauses  {_val(longp, warn_gt=2, bad_gt=6)}  [dim](>{int(LONG_PAUSE_THRESHOLD_S)}s)[/dim]"
        )
        console.print(
            f"  Longest pause  [white]{s['longest_pause_seconds']:.2f}s[/white]   "
            f"Median pause  [white]{s['median_pause_seconds']:.3f}s[/white]   "
            f"Scroll distance  [white]{s['total_scroll_distance']:,} px[/white]"
        )

        dwell = s.get("pre_click_dwell_seconds")
        dwell_str = f"{dwell:.2f}s" if dwell is not None else "n/a"
        console.print(
            f"  Modality switches  [white]{s['modality_switches']}[/white] "
            f"[dim]({s['modality_switches_per_minute']:.1f}/min)[/dim]   "
            f"Scroll reversals  [white]{s['scroll_reversals']}[/white]   "
            f"Pre-click dwell  [white]{dwell_str}[/white]"
        )
        console.print()

        # Activity sparkline
        spark = self._sparkline()
        if spark and spark.strip():
            dur = s["session_duration_formatted"]
            dashes = max(2, len(spark) - len(dur) - 1)
            console.print("  [bold white]Activity[/bold white]  [dim](5s buckets)[/dim]")
            console.print(f"  [cyan]{spark}[/cyan]")
            console.print(f"  [dim]0:00 {'─' * dashes} {dur}[/dim]")
            console.print()


def batch_analyze(data_dir):
    """Walk all sessions in data_dir and return a list of stats dicts.

    Each dict has the session name and a flat set of key metrics drawn from
    InteractionAnalyzer.calculate_statistics(). Sessions with no events.csv or
    no events are skipped quietly; a session that errors during analysis is
    skipped with a warning naming it, so one bad session doesn't abort the batch
    while still being surfaced rather than silently dropped.
    """
    data_dir = Path(data_dir)
    rows = []
    for session_dir in sorted(data_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        events_path = session_dir / "events.csv"
        if not events_path.exists():
            continue
        try:
            analyzer = InteractionAnalyzer(events_path)
            analyzer.load_events()
            if not analyzer.events:
                continue
            analyzer.calculate_statistics()
            s = analyzer.stats
            rows.append({
                "session": session_dir.name,
                "duration_seconds": s["session_duration_seconds"],
                "duration_formatted": s["session_duration_formatted"],
                "total_events": s["total_events"],
                "total_clicks": s["total_clicks"],
                "clicks_per_minute": s["clicks_per_minute"],
                "actions_per_minute": s["actions_per_minute"],
                "rage_clicks": s["rage_clicks_detected"],
                "double_clicks": s["double_clicks"],
                "long_pauses": s["long_pauses"],
                "mean_path_efficiency": s["mean_path_efficiency"],
                "modality_switches_per_minute": s["modality_switches_per_minute"],
                "interkey_interval_cv": s["interkey_interval_cv"],
            })
        except Exception as e:
            warnings.warn(
                f"skipping session '{session_dir.name}': analysis failed ({e})",
                stacklevel=2,
            )
            continue
    return rows
