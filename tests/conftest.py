"""Shared fixtures for the InterLog test suite.

These tests avoid pynput/ffmpeg entirely (the recorder imports pynput lazily,
and we drive its event handlers directly), so they run headless in CI on any OS.
"""

import csv

import pytest

from interlog.recorder import EVENT_FIELDS


@pytest.fixture
def write_events():
    """Return a helper that writes an events CSV with the canonical header.

    Usage: ``write_events(path, [{...event dict...}, ...])``. Missing columns are
    filled blank, so tests only specify the fields they care about.
    """
    def _write(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in EVENT_FIELDS})

    return _write


@pytest.fixture
def render():
    """Return a helper that renders a rich renderable to plain text.

    Lets tests assert on terminal output without a real TTY. The callable takes a
    function of one argument (the console) and returns the exported text.
    """
    from rich.console import Console

    def _render(renderable_call):
        con = Console(record=True, width=90, highlight=False, force_terminal=True)
        renderable_call(con)
        return con.export_text()

    return _render
