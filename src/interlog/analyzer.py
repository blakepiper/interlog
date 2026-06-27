"""Statistical analysis of interaction logs.

Generates summary statistics and interaction-intensity data from a session's
events CSV.
"""

import csv
import math
import statistics
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

# Tunable thresholds for derived metrics.
IDLE_THRESHOLD_S = 2.0          # gaps longer than this count as idle / hesitation
HESITATION_THRESHOLD_S = 2.0    # a pause this long near activity = hesitation
DEAD_CLICK_WINDOW_S = 1.5       # a click with no follow-up interaction within this = "dead"
DOUBLE_CLICK_WINDOW_S = 0.3     # two clicks within this (and close in space) = double-click
DOUBLE_CLICK_DISTANCE_PX = 10


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
        with open(self.events_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields (blank cells stay as empty strings)
                if row.get("timestamp"):
                    row["timestamp"] = float(row["timestamp"])
                for field in ("x", "y", "dx", "dy"):
                    if row.get(field):
                        row[field] = int(float(row[field]))
                self.events.append(row)

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
        duration = max(timestamps) - min(timestamps) if timestamps else 0

        # Click locations for rage click detection
        clicks = [
            {"timestamp": e["timestamp"], "x": e.get("x"), "y": e.get("y")}
            for e in self.events
            if e["event_type"] == "mouse_down"
        ]
        rage_clicks = self._detect_rage_clicks(clicks)

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

        # Timing: idle vs active time, median pause, hesitations, time-to-first-action.
        idle_time = sum(g for g in pauses if g > IDLE_THRESHOLD_S)
        active_time = max(0.0, duration - idle_time)
        median_pause = statistics.median(pauses) if pauses else 0
        hesitations = sum(1 for g in pauses if g > HESITATION_THRESHOLD_S)
        first_interaction = next(
            (e["timestamp"] for e in self.events if e["event_type"] != "mouse_move"),
            None,
        )
        ttfi = (
            first_interaction - min(timestamps)
            if first_interaction is not None and timestamps else 0
        )

        # Click quality and keyboard dynamics.
        double_clicks = self._count_double_clicks(clicks)
        dead_clicks = self._count_dead_clicks()
        kbd = self._keyboard_metrics(duration_minutes)

        # Composite struggle score (higher = more friction), normalized per minute.
        struggle_raw = (
            len(rage_clicks) * 3 + dead_clicks + double_clicks * 0.5 + hesitations * 0.5
        )
        struggle_score = (
            struggle_raw / duration_minutes if duration_minutes > 0 else struggle_raw
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
            "idle_time_seconds": round(idle_time, 2),
            "active_time_seconds": round(active_time, 2),
            "median_pause_seconds": round(median_pause, 3),
            "hesitations": hesitations,
            "time_to_first_interaction_seconds": round(ttfi, 2),
            "double_clicks": double_clicks,
            "dead_clicks": dead_clicks,
            "mean_interkey_interval_seconds": kbd["mean_interkey_interval_seconds"],
            "typing_chars_per_minute": kbd["typing_chars_per_minute"],
            "backspaces": kbd["backspaces"],
            "correction_rate": kbd["correction_rate"],
            "struggle_score": round(struggle_score, 2),
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

    def _count_dead_clicks(self):
        """Clicks with no following interaction within DEAD_CLICK_WINDOW_S.

        A rough proxy for clicking something that did nothing (events are in
        time order, so we scan forward only until the window closes).
        """
        events = self.events
        n = len(events)
        dead = 0
        for i, e in enumerate(events):
            if e["event_type"] != "mouse_down":
                continue
            t = e["timestamp"]
            has_follow = False
            for k in range(i + 1, n):
                if events[k]["timestamp"] - t > DEAD_CLICK_WINDOW_S:
                    break
                if events[k]["event_type"] != "mouse_move":
                    has_follow = True
                    break
            if not has_follow:
                dead += 1
        return dead

    def _keyboard_metrics(self, duration_minutes):
        """Inter-key timing and (when not in privacy mode) typing/correction rates."""
        presses = [e for e in self.events if e["event_type"] == "key_press"]
        intervals = [b["timestamp"] - a["timestamp"] for a, b in zip(presses, presses[1:])]
        mean_interkey = statistics.mean(intervals) if intervals else 0

        # Key identities are unavailable in privacy mode, so char/correction
        # metrics are reported as None rather than guessed.
        redacted = any(e.get("key") == "[REDACTED]" for e in presses)
        if redacted or not presses:
            return {
                "mean_interkey_interval_seconds": round(mean_interkey, 3),
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
            "mean_interkey_interval_seconds": round(mean_interkey, 3),
            "typing_chars_per_minute": round(cpm, 2),
            "backspaces": backspaces,
            "correction_rate": round(backspaces / len(presses), 3),
        }

    def _detect_rage_clicks(self, clicks, time_window=1.0, distance_threshold=50):
        """
        Detect rage clicks (multiple rapid clicks in same area).

        Args:
            clicks: List of click events with timestamp, x, y.
            time_window: Time window in seconds to consider (default 1.0).
            distance_threshold: Maximum distance in pixels to consider same area.

        Returns:
            List of rage click instances.
        """
        rage_clicks = []

        for i in range(len(clicks) - 2):
            # Collect clicks falling within the time window of click i.
            window_clicks = []
            for j in range(i, len(clicks)):
                if clicks[j]["timestamp"] - clicks[i]["timestamp"] <= time_window:
                    window_clicks.append(clicks[j])
                else:
                    break

            if len(window_clicks) < 3:
                continue

            # Check whether all clicks land in the same area.
            first_click = window_clicks[0]
            same_area = True
            for click in window_clicks[1:]:
                if first_click["x"] is None or click["x"] is None:
                    same_area = False
                    break
                distance = (
                    (click["x"] - first_click["x"]) ** 2
                    + (click["y"] - first_click["y"]) ** 2
                ) ** 0.5
                if distance > distance_threshold:
                    same_area = False
                    break

            if same_area:
                rage_clicks.append({
                    "timestamp": first_click["timestamp"],
                    "x": first_click["x"],
                    "y": first_click["y"],
                    "click_count": len(window_clicks),
                })

        return rage_clicks

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

        buckets = []
        current_time = min_time
        while current_time <= max_time:
            bucket_end = current_time + bucket_size

            # Count events in this bucket (excluding mouse moves)
            event_counts = defaultdict(int)
            bucket_total = 0
            for e in self.events:
                if (
                    current_time <= e["timestamp"] < bucket_end
                    and e["event_type"] != "mouse_move"
                ):
                    event_counts[e["event_type"]] += 1
                    bucket_total += 1

            buckets.append({
                "time_start": round(current_time, 2),
                "time_end": round(bucket_end, 2),
                "total_interactions": bucket_total,
                "clicks": event_counts.get("mouse_down", 0),
                "scrolls": event_counts.get("scroll", 0),
                "keypresses": event_counts.get("key_press", 0),
            })

            current_time = bucket_end

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
        blocks = " ▁▂▃▄▅▆▇█"
        max_v = max(values) or 1
        chars = [blocks[min(8, int(v / max_v * 8))] for v in values]
        if len(chars) > width:
            # downsample by averaging
            step = len(chars) / width
            chars = [
                blocks[min(8, int(
                    sum(values[int(i * step):int((i + 1) * step)] or [0])
                    / max(max_v, 1) * 8
                ))]
                for i in range(width)
            ]
        return "".join(chars)

    def print_summary(self):
        """Print summary statistics to console using rich."""
        from rich.console import Console
        from rich.table import Table
        from rich.columns import Columns

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
            t_kbd.add_row("Typing", "[dim]privacy mode[/dim]")
        else:
            t_kbd.add_row("Typing speed", f"{cpm:.0f} cpm")
            t_kbd.add_row("Corrections",
                          f"{s['backspaces']} ({s['correction_rate'] * 100:.1f}%)")
        t_kbd.add_row("Inter-key interval", f"{s['mean_interkey_interval_seconds']:.3f}s")

        console.print(Columns([t_ptr, t_kbd], equal=False, expand=False, padding=(0, 2)))
        console.print()

        # Behavioral patterns
        console.rule("[bold white]Behavioral Patterns[/bold white]", style="dim")

        def _val(n, warn_gt=0, bad_gt=None, fmt=str):
            v = fmt(n)
            if bad_gt is not None and n > bad_gt:
                return f"[red]{v}[/red]"
            if n > warn_gt:
                return f"[yellow]{v}[/yellow]"
            return f"[green]{v}[/green]"

        rage = s["rage_clicks_detected"]
        dead = s["dead_clicks"]
        double = s["double_clicks"]
        hesit = s["hesitations"]
        console.print(
            f"  Rage clicks  {_val(rage, bad_gt=1)}   "
            f"Dead clicks  {_val(dead, warn_gt=2, bad_gt=5)}   "
            f"Double clicks  {_val(double, warn_gt=3)}   "
            f"Hesitations  {_val(hesit, warn_gt=2, bad_gt=6)}"
        )
        console.print(
            f"  Longest pause  [white]{s['longest_pause_seconds']:.2f}s[/white]   "
            f"Median pause  [white]{s['median_pause_seconds']:.3f}s[/white]   "
            f"Scroll distance  [white]{s['total_scroll_distance']:,} px[/white]"
        )
        console.print()

        # Struggle score
        score = s["struggle_score"]
        if score < 2:
            sc, sl = "green", "LOW"
        elif score < 5:
            sc, sl = "yellow", "MODERATE"
        else:
            sc, sl = "red", "HIGH"
        console.print(
            f"  Struggle Score  [{sc}]{score:.2f} / min[/{sc}]  "
            f"[bold {sc}][{sl}][/bold {sc}]  "
            f"[dim](higher = more friction)[/dim]"
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
    InteractionAnalyzer.calculate_statistics(). Sessions that cannot be read
    are silently skipped.
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
                "dead_clicks": s["dead_clicks"],
                "hesitations": s["hesitations"],
                "struggle_score": s["struggle_score"],
            })
        except Exception:
            continue
    return rows
