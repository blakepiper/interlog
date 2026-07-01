"""Tests for interlog.cli: path resolution, command wiring, name validation."""

import json
import sys

import pytest

from interlog.analyzer import batch_analyze
from interlog.cli import _resolve_events_path, _validate_session_name, main, render_batch_table
from interlog.demo import generate


# --- _resolve_events_path --------------------------------------------------

def test_resolve_events_path_folder(tmp_path):
    (tmp_path / "events.csv").write_text("x")
    assert _resolve_events_path(str(tmp_path)) == tmp_path / "events.csv"


def test_resolve_events_path_file(tmp_path):
    f = tmp_path / "p01_events.csv"
    f.write_text("x")
    assert _resolve_events_path(str(f)) == f


# --- analyze / batch / demo commands ---------------------------------------

def test_analyze_json_flag_writes_structured_export(tmp_path):
    sess = generate(tmp_path, seed=5)[0]
    rc = main(["analyze", str(sess), "--json", "--no-text"])
    assert rc == 0
    export = json.loads((sess / "summary.json").read_text())
    assert export["schema"] == "interlog/summary"
    assert export["session"]["provenance"]["interlog_version"]


def test_render_batch_table_lists_sessions_and_footer(tmp_path, write_events, render):
    for name in ("s1", "s2"):
        write_events(tmp_path / name / "events.csv", [
            {"timestamp": 0.0, "event_type": "mouse_down", "x": 1, "y": 1},
            {"timestamp": 1.0, "event_type": "mouse_down", "x": 9, "y": 9},
        ])
    rows = batch_analyze(tmp_path)
    out = render(lambda con: render_batch_table(con, rows, tmp_path))
    assert "s1" in out and "s2" in out
    assert "mean ± SD" in out


def test_demo_command_creates_sessions(tmp_path):
    out = tmp_path / "interlog-demo"
    rc = main(["demo", "-o", str(out), "--sessions", "2"])
    assert rc == 0
    assert len(batch_analyze(out)) == 2


def test_version_matches_installed_metadata():
    import importlib.metadata

    from interlog import __version__
    assert __version__ == importlib.metadata.version("interlog")


def test_record_rejects_monitor_all_off_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    rc = main(["record", "--screen", "--monitor", "all", "-o", str(tmp_path)])
    assert rc == 1


# --- session name validation (path traversal) ------------------------------

@pytest.mark.parametrize("bad", ["../../evil", "..", "a/b", "a\\b", "sub/../x"])
def test_validate_session_name_rejects_traversal(bad):
    with pytest.raises(ValueError, match="path separators"):
        _validate_session_name(bad)


@pytest.mark.parametrize("ok", ["p01", "session_1", "2026-07-01_run", "a.b"])
def test_validate_session_name_accepts_plain(ok):
    assert _validate_session_name(ok) == ok


def test_record_rejects_traversal_name_and_writes_nothing_outside(tmp_path):
    outside = tmp_path / "escaped"
    output = tmp_path / "data"
    rc = main(["record", "--name", f"../{outside.name}", "-o", str(output)])
    assert rc == 1
    assert not outside.exists()
