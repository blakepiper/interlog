"""Tests for interlog.analyzer: metrics, rage clicks, summary export, batch."""

import json
import math

import pytest

from interlog.analyzer import InteractionAnalyzer, base_prefix, batch_analyze
from interlog.demo import generate


# --- base_prefix -----------------------------------------------------------

@pytest.mark.parametrize(("name", "expected"), [
    ("events.csv", ""),
    ("p01_events.csv", "p01_"),
    ("sample_events.csv", "sample_"),
    ("foo.csv", "foo_"),
])
def test_base_prefix(name, expected):
    assert base_prefix(name) == expected


# --- statistics & rage clicks ----------------------------------------------

def test_statistics_and_rage_clicks(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_rage_clicks_count_each_burst_once(tmp_path, write_events):
    # A single sustained burst must be counted once, not once per start index.
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": 0.1 * i, "event_type": "mouse_down", "x": 100, "y": 100,
         "button": "Button.left"}
        for i in range(6)
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["rage_clicks_detected"] == 1


def test_rage_clicks_chain_across_drift(tmp_path, write_events):
    # A drifting burst: each click is within the 50px threshold of the previous
    # one, but click 1 -> click 3 (100px) exceeds it. Chained distance should
    # still register this as a single burst; anchoring to the seed would miss it.
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": 0.10, "event_type": "mouse_down", "x": 100, "y": 100, "button": "Button.left"},
        {"timestamp": 0.20, "event_type": "mouse_down", "x": 145, "y": 100, "button": "Button.left"},
        {"timestamp": 0.30, "event_type": "mouse_down", "x": 190, "y": 100, "button": "Button.left"},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["rage_clicks_detected"] == 1


# --- pointer-path efficiency -----------------------------------------------

def test_path_efficiency_direct_move_is_one(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0},
        {"timestamp": 0.1, "event_type": "mouse_move", "x": 50, "y": 0},
        {"timestamp": 0.2, "event_type": "mouse_move", "x": 100, "y": 0},
        {"timestamp": 0.3, "event_type": "mouse_down", "x": 100, "y": 0},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["mean_path_efficiency"] == pytest.approx(1.0, abs=0.01)


def test_path_efficiency_penalizes_detour(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_path_efficiency_none_without_moves(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_path_efficiency_is_sampling_rate_invariant(tmp_path, write_events):
    # The same physical motion captured at different mouse-sampling rates must
    # yield (near-)identical efficiency — that's what makes it cross-machine.
    eff = {}
    for rate in (60, 120, 240):
        path = tmp_path / f"events_{rate}.csv"
        write_events(path, _semicircle_events(rate))
        a = InteractionAnalyzer(path)
        a.load_events()
        eff[rate] = a.calculate_statistics()["mean_path_efficiency"]

    # Each rate lands near the analytic semicircle efficiency 2/pi ...
    for rate, value in eff.items():
        assert value == pytest.approx(2 / math.pi, abs=0.02)
    # ... and crucially they agree with each other regardless of native rate.
    assert max(eff.values()) - min(eff.values()) < 0.01


def test_pointer_and_timing_metrics(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_click_quality_and_keyboard_metrics(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_privacy_mode_nulls_keyboard_identity_metrics(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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

def test_build_summary_export_structure(tmp_path, write_events):
    session = tmp_path / "p01"
    write_events(session / "events.csv", [
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


def test_save_summary_json_roundtrips(tmp_path, write_events):
    session = tmp_path / "s"
    write_events(session / "events.csv", [
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


# --- terminal rendering ----------------------------------------------------

def test_print_summary_labels_no_typing_distinctly(tmp_path, write_events, render):
    # A mouse-only session must read "none", not be mislabelled "privacy mode".
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_down", "x": 5, "y": 5},
        {"timestamp": 0.5, "event_type": "mouse_down", "x": 9, "y": 9},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    a.calculate_statistics()
    out = render(a.print_summary)
    assert "none" in out
    assert "privacy mode" not in out


# --- movement / input metrics ----------------------------------------------

def _click_move_stream(moves):
    """Two clicks 300 px apart on the x-axis with the given intervening moves.

    ``moves`` is a list of (t, x, y). Returns rows ready for write_events.
    """
    rows = [{"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0}]
    rows += [{"timestamp": t, "event_type": "mouse_move", "x": x, "y": y} for t, x, y in moves]
    rows += [{"timestamp": 1.0, "event_type": "mouse_down", "x": 300, "y": 0}]
    return rows


def test_accuracy_measures_straight_move_is_clean(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, _click_move_stream([
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


def test_accuracy_measures_one_sided_bump(tmp_path, write_events):
    # Path bows to one side of the axis and returns: biased + one orthogonal turn.
    events = tmp_path / "events.csv"
    write_events(events, _click_move_stream([
        (0.25, 75, 40), (0.5, 150, 60), (0.75, 225, 40),
    ]))
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()

    assert s["movement_offset_px"] > 0       # consistently one side of the axis
    assert s["movement_error_px"] > 0
    assert s["task_axis_crossings"] == 0     # never reaches the other side
    assert s["orthogonal_direction_changes"] >= 1  # out then back


def test_accuracy_measures_axis_crossing_zigzag(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, _click_move_stream([
        (0.25, 75, 40), (0.5, 150, -40), (0.75, 225, 40),  # crosses the axis twice
    ]))
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["task_axis_crossings"] >= 2


def test_accuracy_measures_backtrack_along_axis(tmp_path, write_events):
    # Overshoot forward, retreat, finish: reversals *along* the axis.
    events = tmp_path / "events.csv"
    write_events(events, _click_move_stream([
        (0.3, 200, 0), (0.6, 100, 0), (0.85, 260, 0),
    ]))
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["movement_direction_changes"] >= 1
    assert s["movement_error_px"] == pytest.approx(0.0, abs=0.01)  # stays on the axis


def test_accuracy_measures_none_without_segment(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [{"timestamp": 0.0, "event_type": "mouse_down", "x": 0, "y": 0}])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["movement_error_px"] is None
    assert s["task_axis_crossings"] is None


def test_modality_switches_counts_mouse_keyboard_transitions(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_scroll_reversals_counts_direction_flips(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": 0.0, "event_type": "scroll", "x": 0, "y": 0, "dy": -1},
        {"timestamp": 0.1, "event_type": "scroll", "x": 0, "y": 0, "dy": -1},
        {"timestamp": 0.2, "event_type": "scroll", "x": 0, "y": 0, "dy": 1},   # flip 1
        {"timestamp": 0.3, "event_type": "scroll", "x": 0, "y": 0, "dy": -1},  # flip 2
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    assert a.calculate_statistics()["scroll_reversals"] == 2


def test_pre_click_dwell_measures_settling_time(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": 0.0, "event_type": "mouse_move", "x": 10, "y": 10},   # far from target
        {"timestamp": 0.5, "event_type": "mouse_move", "x": 100, "y": 100},  # arrives at target
        {"timestamp": 0.7, "event_type": "mouse_move", "x": 101, "y": 101},  # lingers within radius
        {"timestamp": 1.0, "event_type": "mouse_down", "x": 100, "y": 100},
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    # dwell = click_t (1.0) - first arrival within 8 px (0.5)
    assert a.calculate_statistics()["pre_click_dwell_seconds"] == pytest.approx(0.5, abs=0.01)


def test_click_dispersion_spread_and_bbox(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_interkey_variability(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": t, "event_type": "key_press", "key": k}
        for t, k in [(0.0, "a"), (1.0, "b"), (2.0, "c"), (4.0, "d")]  # intervals 1,1,2
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()
    assert s["mean_interkey_interval_seconds"] == pytest.approx(4 / 3, abs=0.001)
    assert s["interkey_interval_sd_seconds"] == pytest.approx(0.577, abs=0.01)
    assert s["interkey_interval_cv"] == pytest.approx(0.433, abs=0.01)


def test_accuracy_counts_are_sampling_rate_invariant(tmp_path, write_events):
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
        write_events(events, _click_move_stream(moves))
        a = InteractionAnalyzer(events)
        a.load_events()
        return a.calculate_statistics()["orthogonal_direction_changes"]

    assert odc_for(6) == odc_for(40)


def test_calculate_intensity_rejects_nonpositive_bucket(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [{"timestamp": 0.0, "event_type": "mouse_down", "x": 1, "y": 1}])
    a = InteractionAnalyzer(events)
    a.load_events()
    with pytest.raises(ValueError, match="bucket_size"):
        a.calculate_intensity(0)


# --- sparkline -------------------------------------------------------------

def test_sparkline_non_empty(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
        for i in range(20)
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    a.calculate_statistics()
    spark = a._sparkline()
    assert len(spark) > 0
    assert all(c in " ▁▂▃▄▅▆▇█" for c in spark)


def test_sparkline_downsamples_without_saturating(tmp_path, write_events):
    # A long, uneven session must not collapse to a solid bar (every cell full).
    events = tmp_path / "events.csv"
    rows = []
    for i in range(300):
        # heavy activity early, sparse later -> the sparkline should vary
        count = 5 if i < 50 else 1
        for j in range(count):
            rows.append({"timestamp": i + j * 0.01, "event_type": "mouse_down",
                         "x": 1, "y": 1})
    write_events(events, rows)
    a = InteractionAnalyzer(events)
    a.load_events()
    a.calculate_statistics()
    spark = a._sparkline(bucket_size=1.0, width=52)
    assert len(spark) == 52
    assert len(set(spark)) > 1            # not a single repeated glyph
    assert spark.count("█") < len(spark)  # not saturated


# --- batch_analyze ---------------------------------------------------------

def test_batch_analyze_returns_one_row_per_session(tmp_path, write_events):
    for name in ("p01", "p02"):
        events = tmp_path / name / "events.csv"
        write_events(events, [
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


def test_batch_analyze_skips_missing_events(tmp_path, write_events):
    (tmp_path / "empty_session").mkdir()
    events = tmp_path / "good" / "events.csv"
    write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
        for i in range(5)
    ])
    rows = batch_analyze(tmp_path)
    assert len(rows) == 1
    assert rows[0]["session"] == "good"


def test_batch_analyze_warns_on_failed_session_but_keeps_others(tmp_path, write_events, monkeypatch):
    """A session that errors during analysis is skipped with a warning naming it,
    not silently dropped, and other sessions are still returned."""
    for name in ("bad", "good"):
        write_events(tmp_path / name / "events.csv", [
            {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
            for i in range(5)
        ])

    real_calc = InteractionAnalyzer.calculate_statistics

    def flaky_calc(self):
        if self.events_file.parent.name == "bad":
            raise ValueError("boom")
        return real_calc(self)

    monkeypatch.setattr(InteractionAnalyzer, "calculate_statistics", flaky_calc)

    with pytest.warns(UserWarning, match="bad"):
        rows = batch_analyze(tmp_path)

    assert [r["session"] for r in rows] == ["good"]
