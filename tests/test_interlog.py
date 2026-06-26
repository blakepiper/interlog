"""Tests for InterLog. Run with: pytest

These avoid pynput/ffmpeg entirely (the recorder imports pynput lazily, and we
drive its event handlers directly), so they run headless in CI on any OS.
"""

import csv
import json
import re
import time

import pytest

from interlog.analyzer import InteractionAnalyzer, base_prefix, batch_analyze
from interlog.cli import _resolve_events_path
from interlog.heatmap import _infer_bounds, _rage_timestamps
from interlog.recorder import EVENT_FIELDS, InteractionLogger
from interlog.serve import _parse_range, serve_viewer
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

@pytest.mark.parametrize("name,expected", [
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
    assert s["hesitations"] == 1
    assert s["idle_time_seconds"] == pytest.approx(4.5, abs=0.1)


def test_click_quality_and_keyboard_metrics(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [
        {"timestamp": 1.0, "event_type": "mouse_down", "x": 50, "y": 50},
        {"timestamp": 1.1, "event_type": "mouse_down", "x": 50, "y": 50},  # double-click pair
        {"timestamp": 2.0, "event_type": "key_press", "key": "h"},
        {"timestamp": 2.1, "event_type": "key_press", "key": "Key.backspace"},
        {"timestamp": 2.2, "event_type": "key_press", "key": "i"},
        {"timestamp": 10.0, "event_type": "mouse_down", "x": 300, "y": 300},  # dead click (nothing after)
    ])
    a = InteractionAnalyzer(events)
    a.load_events()
    s = a.calculate_statistics()

    assert s["double_clicks"] == 1
    assert s["dead_clicks"] == 1
    assert s["backspaces"] == 1
    assert s["correction_rate"] == pytest.approx(1 / 3, abs=0.01)
    assert s["typing_chars_per_minute"] is not None
    assert s["mean_interkey_interval_seconds"] == pytest.approx(0.1, abs=0.01)
    assert s["struggle_score"] > 0


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


def test_calculate_intensity_rejects_nonpositive_bucket(tmp_path):
    events = tmp_path / "events.csv"
    _write_events(events, [{"timestamp": 0.0, "event_type": "mouse_down", "x": 1, "y": 1}])
    a = InteractionAnalyzer(events)
    a.load_events()
    with pytest.raises(ValueError):
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
    assert out.exists() and out.name == "viewer.html"

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
    with pytest.raises(ValueError):
        build_viewer(events, open_browser=False)


# --- serve -----------------------------------------------------------------

def test_parse_range_full():
    assert _parse_range("bytes=0-99", 200) == (0, 99)


def test_parse_range_suffix():
    assert _parse_range("bytes=-100", 200) == (100, 199)


def test_parse_range_open_end():
    assert _parse_range("bytes=50-", 200) == (50, 199)


def test_parse_range_unsatisfiable():
    with pytest.raises(ValueError):
        _parse_range("bytes=200-300", 100)


def test_parse_range_bad_prefix():
    with pytest.raises(ValueError):
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
        assert "struggle_score" in r


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
