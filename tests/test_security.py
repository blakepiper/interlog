"""Tests for interlog.security: owner-only permissions on captured data."""

import os
import sys

import pytest

from interlog.analyzer import InteractionAnalyzer
from interlog.recorder import InteractionLogger
from interlog.report import build_report
from interlog.security import lock_down


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_outputs_are_owner_only(tmp_path, write_events):
    session = tmp_path / "s"
    events = session / "events.csv"
    write_events(events, [
        {"timestamp": 0.10, "event_type": "mouse_down", "x": 100, "y": 100, "button": "Button.left"},
        {"timestamp": 0.40, "event_type": "mouse_move", "x": 300, "y": 200},
        {"timestamp": 0.80, "event_type": "mouse_down", "x": 300, "y": 200, "button": "Button.left"},
        {"timestamp": 1.20, "event_type": "key_press", "key": "a"},
    ])
    # events.csv is written by the test helper, not the recorder, so lock it
    # down here to mirror what the recorder does before asserting on the rest.
    os.chmod(events, 0o600)

    a = InteractionAnalyzer(events)
    a.load_events()
    a.calculate_statistics()
    outputs = [a.save_summary(), a.save_intensity(), a.save_summary_json()]

    # Heatmap needs optional deps (matplotlib/numpy/Pillow); include it when present.
    try:
        from interlog.heatmap import build_heatmap
        outputs.append(build_heatmap(session))
    except ImportError:
        pass

    outputs.append(build_report(session))

    for path in outputs:
        assert oct(path.stat().st_mode)[-3:] == "600", path


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_recorder_session_dir_is_owner_only(tmp_path):
    logger = InteractionLogger(output_dir=str(tmp_path), session_name="s")
    # The session folder is locked down at construction.
    assert oct(logger.session_dir.stat().st_mode)[-3:] == "700"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_lock_down_is_best_effort_on_missing_path(tmp_path):
    # Never raises, even for a path that doesn't exist.
    lock_down(tmp_path / "nope.txt")
    lock_down(tmp_path / "nodir", is_dir=True)
