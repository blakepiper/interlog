"""Tests for interlog.viewer: embedded data and output path handling."""

import json
import re

import pytest

from interlog.viewer import build_viewer


def _embedded_data(html):
    return json.loads(re.search(r"window\.INTERLOG_DATA = (\{.*?\});", html).group(1))


def test_build_viewer_folder_with_metadata(tmp_path, write_events):
    session = tmp_path / "p01"
    write_events(session / "events.csv", [
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


def test_build_viewer_rejects_empty(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [])
    with pytest.raises(ValueError, match="No events"):
        build_viewer(events, open_browser=False)


def test_build_viewer_into_directory_uses_session_prefix(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": 0.1, "event_type": "mouse_down", "x": 1, "y": 1},
    ])
    out_dir = tmp_path / "out"
    out = build_viewer(events, output=out_dir, open_browser=False)
    # session-folder layout -> "viewer.html" in both the default and dir branch
    assert out == out_dir / "viewer.html"
    assert out.exists()
