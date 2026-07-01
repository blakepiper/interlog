"""Tests for interlog.recorder: session layout, timing, drags, metadata."""

import csv
import time

import pytest

from interlog.recorder import EVENT_FIELDS, InteractionLogger
from interlog.sync import event_offset


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
