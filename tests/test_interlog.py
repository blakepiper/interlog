"""Tests for InterLog. Run with: pytest

These avoid pynput/ffmpeg entirely (the recorder imports pynput lazily, and we
drive its event handlers directly), so they run headless in CI on any OS.
"""

import csv
import http.client
import json
import math
import re
import threading
import time

import pytest

from interlog import branding
from interlog.analyzer import InteractionAnalyzer, base_prefix, batch_analyze
from interlog.demo import generate, write_session
from interlog.report import build_report
from interlog.cli import _resolve_events_path
from interlog.heatmap import _infer_bounds, _rage_timestamps
from interlog.recorder import EVENT_FIELDS, InteractionLogger
from interlog.serve import _parse_range, serve_viewer
from interlog.sync import event_offset, frame_quantization_error, video_time_for_event
from interlog.text_analysis import is_redacted, lexical_stats, reconstruct_text
from interlog.viewer import build_viewer


def _write_events(path, rows):
    """Write an events CSV with the canonical header and given event dicts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in EVENT_FIELDS})


# --- base_prefix -----------------------------------------------------------

@pytest.mark.parametrize(("name", "expected"), [
    ("events.csv", ""),
    ("p01_events.csv", "p01_"),
    ("sample_events.csv", "sample_"),
    ("foo.csv", "foo_"),
])
def test_base_prefix(name, expected):
    assert base_prefix(name) == expected


# --- _resolve_events_path --------------------------------------------------

def test_resolve_events_path_folder(tmp_path):
    (tmp_path / "events.csv").write_text("x")
    assert _resolve_events_path(str(tmp_path)) == tmp_path / "events.csv"


def test_resolve_events_path_file(tmp_path):
    f = tmp_path / "p01_events.csv"
    f.write_text("x")
    assert _resolve_events_path(str(f)) == f


# --- analyzer --------------------------------------------------------------

def test_statistics_and_rage_clicks(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.10, "event_type": "mouse_down", "x": 100, "y": 100, "button": "Button.left"},
        {"timestamp": 0.20, "event_type": "mouse_down", "x": 105, "y": 105, "button": "Button.left"},
        {"timestamp": 0.30, "event_type": "mouse_down", "x": 102, "y": 102, "button": "Button.left"},
        {"timestamp": 1.00, "event_type": "key_press", "key": "a"},
        {"timestamp": 2.00, "event_type": "mouse_move", "x": 500, "y": 500},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    stats = a.calculate_statistics()

    assert stats["total_clicks"] == 3
    assert stats["total_keypresses"] == 1
    assert stats["total_mouse_moves"] == 1
    # mouse moves are excluded from interaction counts
    assert stats["total_interactions"] == 4
    # three rapid clicks in the same area => one rage burst
    assert stats["rage_clicks_detected"] == 1


def test_rage_clicks_count_each_burst_once(tmp_path):
    # A single sustained burst must be counted once, not once per start index.
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.1 * i, "event_type": "mouse_down", "x": 100, "y": 100,
         "button": "Button.left"}
        for i in range(6)
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["rage_clicks_detected"] == 1


def test_path_efficiency_direct_move_is_one(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0},
        {"timestamp": 0.1, "event_type": "mouse_move", "x": 50, "y": 0},
        {"timestamp": 0.2, "event_type": "mouse_move", "x": 100, "y": 0},
        {"timestamp": 0.3, "event_type": "mouse_down", "x": 100, "y": 0},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["mean_path_efficiency"] == pytest.approx(1.0, abs=0.01)


def test_path_efficiency_penalizes_detour(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0},
        {"timestamp": 0.1, "event_type": "mouse_move", "x": 0, "y": 100},
        {"timestamp": 0.2, "event_type": "mouse_move", "x": 100, "y": 100},
        {"timestamp": 0.3, "event_type": "mouse_move", "x": 100, "y": 0},
        {"timestamp": 0.4, "event_type": "mouse_down", "x": 100, "y": 0},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    # straight 100 px over a 300 px path => ~0.33
    assert s["mean_path_efficiency"] == pytest.approx(1 / 3, abs=0.05)


def test_path_efficiency_none_without_moves(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0},
        {"timestamp": 0.5, "event_type": "mouse_down", "x": 500, "y": 0},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["mean_path_efficiency"] is None


def _semicircle_events(rate_hz, duration=1.0, radius=100.0):
    """click A -> semicircular pointer path -> click B, sampled at rate_hz.

    A=(0,0), B=(2r,0); the path bows up over a semicircle of radius r. The
    straight-line distance is 2r and the arc length is pi*r, so the *true*
    efficiency is 2/pi ~= 0.637 regardless of how fast the mouse is sampled.
    """
    n = int(round(duration * rate_hz))
    events = []
    for i in range(n + 1):
        t = duration * i / n
        theta = math.pi * (1 - i / n)          # pi -> 0
        x = radius + radius * math.cos(theta)  # 0 -> 2r
        y = radius * math.sin(theta)           # bows up
        etype = "mouse_down" if i in (0, n) else "mouse_move"
        events.append({"timestamp": round(t, 5), "event_type": etype,
                       "x": int(round(x)), "y": int(round(y))})
    return events


def test_path_efficiency_is_sampling_rate_invariant(tmp_path):
    # The same physical motion captured at different mouse-sampling rates must
    # yield (near-)identical efficiency — that's what makes it cross-machine.
    eff = {}
    for rate in (60, 120, 240):
        path = tmp_path / f"events_{rate}.csv"
        _write_events(path, _semicircle_events(rate))
        a = InteractionAnalyzer(path)
        a.load_events()
        eff[rate] = a.calculate_statistics()["mean_path_efficiency"]

    # Each rate lands near the analytic semicircle efficiency 2/pi ...
    for rate, value in eff.items():
        assert value == pytest.approx(2 / math.pi, abs=0.02)
    # ... and crucially they agree with each other regardless of native rate.
    assert max(eff.values()) - min(eff.values()) < 0.01


def test_pointer_and_timing_metrics(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_move", "x": 0, "y": 0},
        {"timestamp": 0.1, "event_type": "mouse_move", "x": 0, "y": 10},   # +10 px
        {"timestamp": 0.2, "event_type": "mouse_move", "x": 10, "y": 10},  # +10 px
        {"timestamp": 0.5, "event_type": "key_press", "key": "a"},
        {"timestamp": 5.0, "event_type": "key_press", "key": "b"},          # 4.5s gap
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()

    assert s["total_mouse_distance_px"] == pytest.approx(20.0, abs=0.1)
    assert s["mean_pointer_speed_px_s"] == pytest.approx(100.0, abs=1.0)  # 20px / 0.2s
    assert s["time_to_first_interaction_seconds"] == pytest.approx(0.5, abs=0.01)
    assert s["long_pauses"] == 1
    assert s["idle_time_seconds"] == pytest.approx(4.5, abs=0.1)


def test_click_quality_and_keyboard_metrics(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 1.0, "event_type": "mouse_down", "x": 50, "y": 50},
        {"timestamp": 1.1, "event_type": "mouse_down", "x": 50, "y": 50},  # double-click pair
        {"timestamp": 2.0, "event_type": "key_press", "key": "h"},
        {"timestamp": 2.1, "event_type": "key_press", "key": "Key.backspace"},
        {"timestamp": 2.2, "event_type": "key_press", "key": "i"},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()

    assert s["double_clicks"] == 1
    assert s["backspaces"] == 1
    assert s["correction_rate"] == pytest.approx(1 / 3, abs=0.01)
    assert s["typing_chars_per_minute"] is not None
    assert s["mean_interkey_interval_seconds"] == pytest.approx(0.1, abs=0.01)
    # removed metrics should no longer be reported
    assert "dead_clicks" not in s
    assert "struggle_score" not in s


def test_privacy_mode_nulls_keyboard_identity_metrics(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 1.0, "event_type": "key_press", "key": "[REDACTED]"},
        {"timestamp": 1.3, "event_type": "key_press", "key": "[REDACTED]"},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()

    assert s["typing_chars_per_minute"] is None
    assert s["backspaces"] is None
    assert s["correction_rate"] is None
    assert s["mean_interkey_interval_seconds"] == pytest.approx(0.3, abs=0.01)
    # timing-only variability survives privacy mode (no key identity needed)
    assert s["interkey_interval_cv"] is None  # too few intervals here


# --- structured summary.json export ----------------------------------------

def test_build_summary_export_structure(tmp_path):
    session = tmp_path / "p01"
    _write_events(session / "events.csv", [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 10, "y": 10},
        {"timestamp": 1.0, "event_type": "mouse_down", "x": 99, "y": 99},
    ])
    (session / "metadata.json").write_text(json.dumps({
        "session_name": "p01",
        "privacy_mode": False,
        "provenance": {"interlog_version": "9.9.9", "system": "TestOS",
                       "python_version": "3.12.0", "platform": "test"},
        "capture_region": {"x": 0, "y": 0, "width": 1920, "height": 1080, "dpi_scale": 2.0},
    }))

    a = InteractionAnalyzer(session / "events.csv")
    a.load_events()
    a.calculate_statistics()
    export = a.build_summary_export()

    assert export["schema"] == "interlog/summary"
    assert export["schema_version"]            # present, non-empty
    assert export["tool_version"]              # the analyzing tool's version
    assert export["session"]["name"] == "p01"
    assert export["session"]["provenance"]["interlog_version"] == "9.9.9"
    assert export["session"]["capture_region"]["dpi_scale"] == 2.0
    # metrics keep native JSON types (not stringified like the CSV)
    assert export["metrics"]["total_clicks"] == 2
    assert isinstance(export["metrics"]["total_clicks"], int)
    assert "comparability" in export["metrics_notes"]


def test_save_summary_json_roundtrips(tmp_path):
    session = tmp_path / "s"
    _write_events(session / "events.csv", [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 1, "y": 1},
        {"timestamp": 0.5, "event_type": "key_press", "key": "a"},
    ])
    a = InteractionAnalyzer(session / "events.csv")
    a.load_events()
    a.calculate_statistics()
    out = a.save_summary_json()
    assert out.name == "summary.json"
    loaded = json.loads(out.read_text())
    assert loaded["metrics"]["total_keypresses"] == 1


def test_summary_export_marks_synthetic_from_metadata(tmp_path):
    paths = generate(tmp_path, seed=3)
    a = InteractionAnalyzer(paths[0] / "events.csv")
    a.load_events()
    a.calculate_statistics()
    assert a.build_summary_export()["session"]["synthetic"] is True


def test_analyze_json_flag_writes_structured_export(tmp_path):
    from interlog.cli import main
    sess = generate(tmp_path, seed=5)[0]
    rc = main(["analyze", str(sess), "--json", "--no-text"])
    assert rc == 0
    export = json.loads((sess / "summary.json").read_text())
    assert export["schema"] == "interlog/summary"
    assert export["session"]["provenance"]["interlog_version"]


# --- demo data generation --------------------------------------------------

def test_demo_generate_single_session(tmp_path):
    paths = generate(tmp_path, sessions=1, seed=7)
    assert len(paths) == 1
    sess = paths[0]
    assert sess.name == "demo"
    assert (sess / "events.csv").exists()

    a = InteractionAnalyzer(sess / "events.csv")
    a.load_events()
    s = a.calculate_statistics()
    assert s["total_events"] > 0
    assert s["total_clicks"] > 0

    meta = json.loads((sess / "metadata.json").read_text())
    assert meta["synthetic"] is True            # never mistaken for a real capture
    assert meta["profile"] == "checkout"
    assert meta["provenance"]["interlog_version"]


def test_demo_generate_multiple_feeds_batch(tmp_path):
    paths = generate(tmp_path, sessions=4, seed=1)
    assert len(paths) == 4
    rows = batch_analyze(tmp_path)
    assert len(rows) == 4


def test_demo_is_reproducible_for_seed(tmp_path):
    a = write_session(tmp_path / "a", "s", profile="checkout", seed=42)
    b = write_session(tmp_path / "b", "s", profile="checkout", seed=42)
    assert (a / "events.csv").read_text() == (b / "events.csv").read_text()


def test_demo_rejects_unknown_profile(tmp_path):
    with pytest.raises(ValueError):
        write_session(tmp_path, "s", profile="nope")


def test_demo_command_creates_sessions(tmp_path):
    from interlog.cli import main
    out = tmp_path / "interlog-demo"
    rc = main(["demo", "-o", str(out), "--sessions", "2"])
    assert rc == 0
    assert len(batch_analyze(out)) == 2


# --- terminal rendering (capturable) ---------------------------------------

def _render(renderable_call):
    from rich.console import Console
    con = Console(record=True, width=90, highlight=False, force_terminal=True)
    renderable_call(con)
    return con.export_text()


def test_print_summary_labels_no_typing_distinctly(tmp_path):
    # A mouse-only session must read "none", not be mislabelled "privacy mode".
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 5, "y": 5},
        {"timestamp": 0.5, "event_type": "mouse_down", "x": 9, "y": 9},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    a.calculate_statistics()
    out = _render(a.print_summary)
    assert "none" in out
    assert "privacy mode" not in out


def test_render_batch_table_lists_sessions_and_footer(tmp_path):
    from interlog.cli import render_batch_table
    from interlog.analyzer import batch_analyze
    for name in ("s1", "s2"):
        _write_events(tmp_path / name / "events.csv", [
            {"timestamp": 0.0, "event_type": "mouse_down", "x": 1, "y": 1},
            {"timestamp": 1.0, "event_type": "mouse_down", "x": 9, "y": 9},
        ])
    rows = batch_analyze(tmp_path)
    out = _render(lambda con: render_batch_table(con, rows, tmp_path))
    assert "s1" in out and "s2" in out
    assert "mean ± SD" in out


# --- new movement / input metrics ------------------------------------------

def _click_move_stream(moves):
    """Two clicks 300 px apart on the x-axis with the given intervening moves.

    ``moves`` is a list of (t, x, y). Returns rows ready for _write_events.
    """
    rows = [{"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0}]
    rows += [{"timestamp": t, "event_type": "mouse_move", "x": x, "y": y} for t, x, y in moves]
    rows += [{"timestamp": 1.0, "event_type": "mouse_down", "x": 300, "y": 0}]
    return rows


def test_accuracy_measures_straight_move_is_clean(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, _click_move_stream([
        (0.25, 75, 0), (0.5, 150, 0), (0.75, 225, 0),  # dead straight on the axis
    ]))
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()

    assert s["movement_error_px"] == pytest.approx(0.0, abs=0.01)
    assert s["movement_variability_px"] == pytest.approx(0.0, abs=0.01)
    assert s["movement_offset_px"] == pytest.approx(0.0, abs=0.01)
    assert s["task_axis_crossings"] == 0
    assert s["movement_direction_changes"] == 0
    assert s["orthogonal_direction_changes"] == 0


def test_accuracy_measures_one_sided_bump(tmp_path):
    # Path bows to one side of the axis and returns: biased + one orthogonal turn.
    events = tmp_path / "events.csv"
    _write_events(events, _click_move_stream([
        (0.25, 75, 40), (0.5, 150, 60), (0.75, 225, 40),
    ]))
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()

    assert s["movement_offset_px"] > 0       # consistently one side of the axis
    assert s["movement_error_px"] > 0
    assert s["task_axis_crossings"] == 0     # never reaches the other side
    assert s["orthogonal_direction_changes"] >= 1  # out then back


def test_accuracy_measures_axis_crossing_zigzag(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, _click_move_stream([
        (0.25, 75, 40), (0.5, 150, -40), (0.75, 225, 40),  # crosses the axis twice
    ]))
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["task_axis_crossings"] >= 2


def test_accuracy_measures_backtrack_along_axis(tmp_path):
    # Overshoot forward, retreat, finish: reversals *along* the axis.
    events = tmp_path / "events.csv"
    _write_events(events, _click_move_stream([
        (0.3, 200, 0), (0.6, 100, 0), (0.85, 260, 0),
    ]))
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["movement_direction_changes"] >= 1
    assert s["movement_error_px"] == pytest.approx(0.0, abs=0.01)  # stays on the axis


def test_accuracy_measures_none_without_segment(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [{"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0}])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["movement_error_px"] is None
    assert s["task_axis_crossings"] is None


def test_modality_switches_counts_mouse_keyboard_transitions(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 1, "y": 1},
        {"timestamp": 0.1, "event_type": "mouse_move", "x": 2, "y": 2},  # ignored
        {"timestamp": 0.2, "event_type": "key_press", "key": "a"},       # switch 1
        {"timestamp": 0.3, "event_type": "key_press", "key": "b"},       # same modality
        {"timestamp": 0.4, "event_type": "scroll", "x": 2, "y": 2, "dy": -1},  # switch 2
        {"timestamp": 0.5, "event_type": "key_press", "key": "c"},       # switch 3
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["modality_switches"] == 3


def test_scroll_reversals_counts_direction_flips(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "scroll", "x": 0, "y": 0, "dy": -1},
        {"timestamp": 0.1, "event_type": "scroll", "x": 0, "y": 0, "dy": -1},
        {"timestamp": 0.2, "event_type": "scroll", "x": 0, "y": 0, "dy": 1},   # flip 1
        {"timestamp": 0.3, "event_type": "scroll", "x": 0, "y": 0, "dy": -1},  # flip 2
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    assert a.calculate_statistics()["scroll_reversals"] == 2


def test_pre_click_dwell_measures_settling_time(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_move", "x": 10, "y": 10},   # far from target
        {"timestamp": 0.5, "event_type": "mouse_move", "x": 100, "y": 100},  # arrives at target
        {"timestamp": 0.7, "event_type": "mouse_move", "x": 101, "y": 101},  # lingers within radius
        {"timestamp": 1.0, "event_type": "mouse_down", "x": 100, "y": 100},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    # dwell = click_t (1.0) - first arrival within 8 px (0.5)
    assert a.calculate_statistics()["pre_click_dwell_seconds"] == pytest.approx(0.5, abs=0.01)


def test_click_dispersion_spread_and_bbox(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": t, "event_type": "mouse_down", "x": x, "y": y}
        for t, (x, y) in enumerate([(0, 0), (100, 0), (0, 100), (100, 100)])
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    # centroid (50,50); every click is sqrt(50^2+50^2) ~= 70.71 px away
    assert s["click_spread_px"] == pytest.approx(70.7, abs=0.2)
    assert s["click_bbox_width_px"] == 100
    assert s["click_bbox_height_px"] == 100


def test_interkey_variability(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": t, "event_type": "key_press", "key": k}
        for t, k in [(0.0, "a"), (1.0, "b"), (2.0, "c"), (4.0, "d")]  # intervals 1,1,2
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["mean_interkey_interval_seconds"] == pytest.approx(4 / 3, abs=0.001)
    assert s["interkey_interval_sd_seconds"] == pytest.approx(0.577, abs=0.01)
    assert s["interkey_interval_cv"] == pytest.approx(0.433, abs=0.01)


def test_accuracy_counts_are_sampling_rate_invariant(tmp_path):
    """The direction-change counts must not inflate with mouse sampling rate.

    The same one-sided-bump motion sampled densely vs sparsely should yield the
    same orthogonal-direction-change count, because measures are computed on a
    fixed-rate resampled trajectory.
    """
    def odc_for(n):
        # n intervening samples tracing the same smooth bump y = 60*sin(pi*x/300)
        moves = []
        for i in range(1, n + 1):
            frac = i / (n + 1)
            x = int(300 * frac)
            y = int(60 * math.sin(math.pi * frac))
            moves.append((frac, x, y))
        events = tmp_path / f"events_{n}.csv"
        _write_events(events, _click_move_stream(moves))
        a = InteractionAnalyzer(events)
        a.load_events()
        return a.calculate_statistics()["orthogonal_direction_changes"]

    assert odc_for(6) == odc_for(40)


def test_calculate_intensity_rejects_nonpositive_bucket(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [{"timestamp": 0.0, "event_type": "mouse_down", "x": 1, "y": 1}])
    a = InteractionAnalyzer(events)
    a.load_events()
    with pytest.raises(ValueError, match="bucket_size"):
        a.calculate_intensity(0)


# --- recorder --------------------------------------------------------------

def test_session_dir_and_filenames(tmp_path):
    log = InteractionLogger(output_dir=str(tmp_path), session_name="s1")
    assert log.session_dir == tmp_path / "s1"
    assert log.session_dir.is_dir()
    assert log.events_file.name == "events.csv"
    assert log.metadata_file.name == "metadata.json"


def test_timestamp_is_monotonic(tmp_path):
    log = InteractionLogger(output_dir=str(tmp_path), session_name="s1")
    assert log._get_timestamp() == 0.0  # before start
    log._mono_start = time.monotonic() - 5.0
    assert log._get_timestamp() == pytest.approx(5.0, abs=0.5)


def test_drag_detection(tmp_path):
    log = InteractionLogger(output_dir=str(tmp_path), session_name="s1")
    log._mono_start = time.monotonic()

    # press -> move -> release  => a drag
    log.on_click(10, 10, "Button.left", True)
    log.on_move(60, 60)
    log.on_click(60, 60, "Button.left", False)
    # plain click (no move) => no drag
    log.on_click(200, 200, "Button.left", True)
    log.on_click(200, 200, "Button.left", False)

    types = [e["event_type"] for e in log.events]
    assert types.count("drag") == 1


def test_flush_writes_rows(tmp_path):
    log = InteractionLogger(output_dir=str(tmp_path), session_name="s1")
    log._mono_start = time.monotonic()
    with open(log.events_file, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=EVENT_FIELDS).writeheader()
    log._log_event("mouse_down", x=1, y=2, button="Button.left")
    log._log_event("key_press", key="a")
    log._flush_events()

    with open(log.events_file) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert not log.events  # buffer cleared after flush


# --- sync (event <-> video alignment) --------------------------------------

def test_event_offset_recovers_video_time():
    """Mapping an event through the offset lands it on the video clock exactly.

    An event captured at absolute monotonic time T has session time
    T - mono_start and should map to video time T - first_frame. Composing
    event_offset + video_time_for_event must recover that, with the mono_start
    terms cancelling — for any clock origins.
    """
    mono_start = 1000.0
    first_frame = 998.5            # video began 1.5 s before logging started
    offset = event_offset(mono_start, first_frame)
    assert offset == pytest.approx(1.5)

    for abs_t in (1000.0, 1002.25, 1010.0):       # absolute monotonic capture times
        event_time = abs_t - mono_start            # what the recorder stores
        expected_video_time = abs_t - first_frame  # ground truth on the video clock
        assert video_time_for_event(event_time, offset) == pytest.approx(expected_video_time)


def test_event_offset_negative_when_logging_leads_video():
    # Logger started before the first frame -> early events map before video t=0.
    offset = event_offset(1000.0, 1002.0)
    assert offset == pytest.approx(-2.0)
    assert video_time_for_event(0.5, offset) == pytest.approx(-1.5)


def test_frame_quantization_error_halves_with_fps():
    assert frame_quantization_error(15) == pytest.approx(1 / 30)
    assert frame_quantization_error(30) == pytest.approx(1 / 60)
    assert frame_quantization_error(30) < frame_quantization_error(15)


def test_frame_quantization_error_rejects_nonpositive_fps():
    with pytest.raises(ValueError):
        frame_quantization_error(0)


# --- session metadata ------------------------------------------------------

def test_metadata_includes_provenance(tmp_path):
    log = InteractionLogger(output_dir=str(tmp_path), session_name="s1")
    meta = log._build_metadata()
    prov = meta["provenance"]
    assert prov["interlog_version"]            # non-empty version string
    assert prov["python_version"]
    assert prov["system"]
    assert "video_start_offset" not in meta    # no video attached


def test_metadata_carries_sync_offset_and_error_budget(tmp_path):
    log = InteractionLogger(output_dir=str(tmp_path), session_name="s1")
    log._mono_start = 1000.0
    log.video_file = log.session_dir / "recording.mp4"
    log.video_first_frame_time = 998.5
    log.video_fps = 15
    log.video_start_offset = event_offset(log._mono_start, log.video_first_frame_time)

    meta = log._build_metadata()
    assert meta["video_start_offset"] == pytest.approx(1.5)
    assert meta["video_fps"] == 15
    assert meta["sync_frame_quantization_seconds"] == pytest.approx(1 / 30, abs=1e-4)


# --- viewer ----------------------------------------------------------------

def _embedded_data(html):
    return json.loads(re.search(r"window\.INTERLOG_DATA = (\{.*?\});", html).group(1))


def test_build_viewer_folder_with_metadata(tmp_path):
    session = tmp_path / "p01"
    _write_events(session / "events.csv", [
        {"timestamp": 0.1, "event_type": "mouse_down", "x": 10, "y": 10},
        {"timestamp": 0.5, "event_type": "key_press", "key": "a"},
        {"timestamp": 1.0, "event_type": "scroll", "x": 5, "y": 5, "dy": -2},
    ])
    (session / "metadata.json").write_text(json.dumps({
        "session_name": "p01",
        "video_start_offset": 2.5,
        "capture_region": {"x": 0, "y": 0, "width": 1920, "height": 1080, "dpi_scale": 1.0},
    }))

    out = build_viewer(session / "events.csv", open_browser=False)
    assert out.exists()
    assert out.name == "viewer.html"

    data = _embedded_data(out.read_text(encoding="utf-8"))
    assert data["session"] == "p01"
    assert data["offset"] == 2.5
    assert data["captureRegion"]["width"] == 1920
    assert len(data["markers"]) == 3


def test_reconstruct_text_handles_backspace_and_whitespace():
    events = [
        {"event_type": "key_press", "key": "h"},
        {"event_type": "key_press", "key": "e"},
        {"event_type": "key_press", "key": "y"},
        {"event_type": "key_press", "key": "Key.backspace"},
        {"event_type": "key_press", "key": "Key.space"},
        {"event_type": "key_press", "key": "u"},
        {"event_type": "key_press", "key": "Key.shift"},   # ignored
        {"event_type": "mouse_down", "key": ""},            # non-key ignored
    ]
    assert reconstruct_text(events) == "he u"


def test_lexical_stats_keywords_and_counts():
    stats = lexical_stats("The cat sat on the mat. The cat ran.")
    assert stats["word_count"] == 9
    # stopwords ("the", "on") excluded; "cat" is the top keyword
    assert stats["top_keywords"][0] == ("cat", 2)


def test_is_redacted_detects_privacy_mode():
    assert is_redacted([{"event_type": "key_press", "key": "[REDACTED]"}]) is True
    assert is_redacted([{"event_type": "key_press", "key": "a"}]) is False


def test_build_viewer_rejects_empty(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [])
    with pytest.raises(ValueError, match="No events"):
        build_viewer(events, open_browser=False)


# --- serve -----------------------------------------------------------------

def test_parse_range_full():
    assert _parse_range("bytes=0-99", 200) == (0, 99)


def test_parse_range_suffix():
    assert _parse_range("bytes=-100", 200) == (100, 199)


def test_parse_range_open_end():
    assert _parse_range("bytes=50-", 200) == (50, 199)


def test_parse_range_unsatisfiable():
    with pytest.raises(ValueError, match="unsatisfiable"):
        _parse_range("bytes=200-300", 100)


def test_parse_range_bad_prefix():
    with pytest.raises(ValueError, match="bytes range"):
        _parse_range("chunks=0-10", 100)


def test_serve_viewer_starts_and_stops(tmp_path):
    html = tmp_path / "viewer.html"
    html.write_text("<html></html>")
    httpd, url = serve_viewer(tmp_path, "viewer.html")
    assert url.startswith("http://127.0.0.1:")
    assert "viewer.html" in url
    httpd.server_close()


# --- heatmap helpers -------------------------------------------------------

def test_infer_bounds_from_events():
    events = [
        {"event_type": "mouse_move", "x": 100, "y": 200},
        {"event_type": "mouse_move", "x": 800, "y": 600},
        {"event_type": "mouse_down", "x": 999, "y": 999},  # clicks excluded
    ]
    w, h = _infer_bounds(events)
    assert w == 900   # max x (800) + 100
    assert h == 700   # max y (600) + 100


def test_rage_timestamps_detects_burst():
    clicks = [
        {"timestamp": 0.1, "x": 50, "y": 50},
        {"timestamp": 0.2, "x": 52, "y": 51},
        {"timestamp": 0.3, "x": 51, "y": 50},
    ]
    rage = _rage_timestamps(clicks)
    assert len(rage) == 3


def test_rage_timestamps_ignores_spread_clicks():
    clicks = [
        {"timestamp": 0.1, "x": 50,  "y": 50},
        {"timestamp": 0.2, "x": 500, "y": 500},  # too far
        {"timestamp": 0.3, "x": 52,  "y": 51},
    ]
    assert len(_rage_timestamps(clicks)) == 0


# --- sparkline -------------------------------------------------------------

def test_sparkline_non_empty(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
        for i in range(20)
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    a.calculate_statistics()
    spark = a._sparkline()
    assert len(spark) > 0
    assert all(c in " ▁▂▃▄▅▆▇█" for c in spark)


# --- batch_analyze ---------------------------------------------------------

def test_batch_analyze_returns_one_row_per_session(tmp_path):
    for name in ("p01", "p02"):
        events = tmp_path / name / "events.csv"
        _write_events(events, [
            {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
            for i in range(10)
        ])
    rows = batch_analyze(tmp_path)
    assert len(rows) == 2
    sessions = {r["session"] for r in rows}
    assert sessions == {"p01", "p02"}
    for r in rows:
        assert "clicks_per_minute" in r
        assert "long_pauses" in r
        assert "mean_path_efficiency" in r
        assert "struggle_score" not in r


# --- build_report ----------------------------------------------------------

def test_build_report_creates_html(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 10*i, "y": 10*i}
        for i in range(1, 20)
    ] + [
        {"timestamp": float(i) + 0.1, "event_type": "mouse_move", "x": 10*i+1, "y": 10*i+1}
        for i in range(1, 20)
    ])
    output = build_report(tmp_path)
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "InterLog Report" in html
    assert "<svg" in html
    assert "Interaction Signals" in html
    assert "Struggle" not in html


def test_build_report_embeds_heatmap(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
        for i in range(10)
    ])
    # Fake heatmap PNG (minimal valid 1x1 PNG)
    import base64
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    (tmp_path / "heatmap.png").write_bytes(png_bytes)
    output = build_report(tmp_path)
    html = output.read_text(encoding="utf-8")
    assert 'data:image/png;base64,' in html


def test_batch_analyze_skips_missing_events(tmp_path):
    (tmp_path / "empty_session").mkdir()
    events = tmp_path / "good" / "events.csv"
    _write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
        for i in range(5)
    ])
    rows = batch_analyze(tmp_path)
    assert len(rows) == 1
    assert rows[0]["session"] == "good"


# --- serve (request-level) -------------------------------------------------

def _serve(tmp_path, body=b"0123456789"):
    """Start a real server in a thread; return (conn, httpd) and the file name."""
    (tmp_path / "viewer.html").write_text("<html></html>")
    (tmp_path / "rec.bin").write_bytes(body)
    httpd, url = serve_viewer(tmp_path, "viewer.html")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address
    return http.client.HTTPConnection(host, port), httpd


def test_serve_full_get_returns_200(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/rec.bin")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.read() == b"0123456789"
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()


def test_serve_range_returns_206(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/rec.bin", headers={"Range": "bytes=2-5"})
        resp = conn.getresponse()
        assert resp.status == 206
        assert resp.getheader("Content-Range") == "bytes 2-5/10"
        assert resp.getheader("Content-Length") == "4"
        assert resp.read() == b"2345"
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()


def test_serve_unsatisfiable_range_returns_416(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/rec.bin", headers={"Range": "bytes=100-200"})
        assert conn.getresponse().status == 416
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()


def test_serve_missing_file_with_range_returns_404(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/nope.bin", headers={"Range": "bytes=0-1"})
        assert conn.getresponse().status == 404
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()


def test_parse_range_suffix_longer_than_file_serves_whole():
    # bytes=-500 on a 10-byte file => the whole file, not 416.
    assert _parse_range("bytes=-500", 10) == (0, 9)


# --- branding --------------------------------------------------------------

def test_banner_plain_has_no_ansi():
    out = branding.banner(color=False)
    assert "\033[" not in out
    assert "capture . measure . replay" in out


def test_banner_color_has_ansi():
    assert "\033[" in branding.banner(color=True)


def test_supports_color_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert branding._supports_color() is False


# --- viewer (directory output) ---------------------------------------------

def test_build_viewer_into_directory_uses_session_prefix(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 0.1, "event_type": "mouse_down", "x": 1, "y": 1},
    ])
    out_dir = tmp_path / "out"
    out = build_viewer(events, output=out_dir, open_browser=False)
    # session-folder layout -> "viewer.html" in both the default and dir branch
    assert out == out_dir / "viewer.html"
    assert out.exists()


# --- demo reproducibility --------------------------------------------------

def test_demo_metadata_is_reproducible_for_seed(tmp_path):
    a = write_session(tmp_path / "a", "s", profile="checkout", seed=42)
    b = write_session(tmp_path / "b", "s", profile="checkout", seed=42)
    assert (a / "metadata.json").read_text() == (b / "metadata.json").read_text()


def test_demo_generate_rejects_zero_sessions(tmp_path):
    with pytest.raises(ValueError):
        generate(tmp_path, sessions=0)


# --- regressions -----------------------------------------------------------

def test_sparkline_downsamples_without_saturating(tmp_path):
    # A long, uneven session must not collapse to a solid bar (every cell full).
    events = tmp_path / "events.csv"
    rows = []
    for i in range(300):
        # heavy activity early, sparse later -> the sparkline should vary
        count = 5 if i < 50 else 1
        for j in range(count):
            rows.append({"timestamp": i + j * 0.01, "event_type": "mouse_down",
                         "x": 1, "y": 1})
    _write_events(events, rows)
    a = InteractionAnalyzer(events)
    a.load_events()
    a.calculate_statistics()
    spark = a._sparkline(bucket_size=1.0, width=52)
    assert len(spark) == 52
    assert len(set(spark)) > 1            # not a single repeated glyph
    assert spark.count("█") < len(spark)  # not saturated


def test_reconstruct_text_handles_delete():
    events = [
        {"event_type": "key_press", "key": "h"},
        {"event_type": "key_press", "key": "i"},
        {"event_type": "key_press", "key": "Key.delete"},
    ]
    assert reconstruct_text(events) == "h"


def test_lexical_stats_ignores_bare_apostrophe():
    stats = lexical_stats("don't ' '' stop")
    words = {"don't", "stop"}
    assert stats["word_count"] == len(words)
