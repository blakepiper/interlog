"""Tests for interlog.report: HTML report generation and escaping."""

import base64
import json

from interlog.report import build_report


def test_build_report_creates_html(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
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


def test_build_report_embeds_heatmap(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
        for i in range(10)
    ])
    # Fake heatmap PNG (minimal valid 1x1 PNG)
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    (tmp_path / "heatmap.png").write_bytes(png_bytes)
    output = build_report(tmp_path)
    html = output.read_text(encoding="utf-8")
    assert 'data:image/png;base64,' in html


def test_report_escapes_session_name(tmp_path, write_events):
    events = tmp_path / "events.csv"
    write_events(events, [
        {"timestamp": float(i), "event_type": "mouse_down", "x": 1, "y": 1}
        for i in range(5)
    ])
    (tmp_path / "metadata.json").write_text(json.dumps(
        {"session_name": "<script>alert(1)</script> & co"}))
    html = build_report(tmp_path).read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
