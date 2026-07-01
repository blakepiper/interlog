"""Tests for interlog.heatmap helpers (no matplotlib needed for these)."""

from interlog.heatmap import _infer_bounds, _rage_timestamps


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
