"""Tests for interlog.demo: synthetic session generation and reproducibility."""

import json

import pytest

from interlog.analyzer import InteractionAnalyzer, batch_analyze
from interlog.demo import generate, write_session


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


def test_demo_metadata_is_reproducible_for_seed(tmp_path):
    a = write_session(tmp_path / "a", "s", profile="checkout", seed=42)
    b = write_session(tmp_path / "b", "s", profile="checkout", seed=42)
    assert (a / "metadata.json").read_text() == (b / "metadata.json").read_text()


def test_demo_generate_rejects_zero_sessions(tmp_path):
    with pytest.raises(ValueError):
        generate(tmp_path, sessions=0)
