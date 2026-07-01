"""Tests for interlog.screen: geometry, ffmpeg command building, remux.

These avoid real ffmpeg/portal/ctypes by monkeypatching geometry detection and
the subprocess boundary.
"""

import sys
from types import SimpleNamespace

import pytest

from interlog import screen
from interlog.screen import ScreenRecorder


def _make_recorder(tmp_path, monkeypatch, geometry=None):
    """Build a ScreenRecorder without touching real OS geometry detection."""
    monkeypatch.setattr(screen, "capture_geometry", lambda monitor="primary": geometry)
    return ScreenRecorder(tmp_path / "out.mp4", fps=15)


def test_ffmpeg_path_reflects_which(monkeypatch):
    monkeypatch.setattr(screen.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert screen.ffmpeg_path() == "/usr/bin/ffmpeg"
    monkeypatch.setattr(screen.shutil, "which", lambda name: None)
    assert screen.ffmpeg_path() is None


def test_capture_geometry_linux_parses_primary(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    xrandr = "Screen 0\nHDMI-1 connected primary 1920x1080+0+0 (normal)\n"
    monkeypatch.setattr(
        screen.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=xrandr),
    )
    g = screen._capture_geometry_linux()
    assert g == {"x": 0, "y": 0, "width": 1920, "height": 1080, "dpi_scale": 1.0}


def test_capture_geometry_linux_parses_non_primary(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    xrandr = "DP-1 connected 1280x720+100+50 (normal)\n"
    monkeypatch.setattr(
        screen.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=xrandr),
    )
    g = screen._capture_geometry_linux()
    assert g == {"x": 100, "y": 50, "width": 1280, "height": 720, "dpi_scale": 1.0}


def test_capture_geometry_linux_none_on_wayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert screen._capture_geometry_linux() is None


def test_capture_geometry_linux_none_without_display(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert screen._capture_geometry_linux() is None


def test_command_windows_with_geometry(monkeypatch, tmp_path):
    monkeypatch.setattr(screen, "ffmpeg_path", lambda: "/ff")
    monkeypatch.setattr(sys, "platform", "win32")
    rec = _make_recorder(tmp_path, monkeypatch)
    rec.geometry = {"x": 5, "y": 7, "width": 1920, "height": 1080, "dpi_scale": 1.0}
    cmd = rec._command()
    assert "gdigrab" in cmd
    assert "-offset_x" in cmd and "5" in cmd
    assert "1920x1080" in cmd
    assert cmd[-1].endswith(".mkv")


def test_command_windows_without_geometry(monkeypatch, tmp_path):
    monkeypatch.setattr(screen, "ffmpeg_path", lambda: "/ff")
    monkeypatch.setattr(sys, "platform", "win32")
    rec = _make_recorder(tmp_path, monkeypatch)
    rec.geometry = None
    cmd = rec._command()
    assert "gdigrab" in cmd
    assert "-offset_x" not in cmd
    assert "desktop" in cmd


def test_command_macos(monkeypatch, tmp_path):
    monkeypatch.setattr(screen, "ffmpeg_path", lambda: "/ff")
    monkeypatch.setattr(sys, "platform", "darwin")
    rec = _make_recorder(tmp_path, monkeypatch)
    cmd = rec._command()
    assert "avfoundation" in cmd
    assert "Capture screen 0:none" in cmd


def test_command_raises_without_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(screen, "ffmpeg_path", lambda: None)
    rec = _make_recorder(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="ffmpeg not found"):
        rec._command()


def test_linux_grab_args_x11(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    rec = _make_recorder(tmp_path, monkeypatch)
    assert rec._linux_grab_args() == ["-f", "x11grab", "-i", ":0"]


def test_linux_grab_args_raises_without_display(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("DISPLAY", raising=False)
    rec = _make_recorder(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="DISPLAY"):
        rec._linux_grab_args()


def test_on_stdout_sets_live_on_first_frame(monkeypatch, tmp_path):
    rec = _make_recorder(tmp_path, monkeypatch)
    rec._on_stdout("frame=0")
    assert not rec._live.is_set()
    rec._on_stdout("frame=abc")  # non-int must not raise
    assert not rec._live.is_set()
    rec._on_stdout("frame=1")
    assert rec._live.is_set()


def test_error_message_with_and_without_tail(monkeypatch, tmp_path):
    rec = _make_recorder(tmp_path, monkeypatch)
    assert rec._error_message() == "ffmpeg exited unexpectedly."
    rec._on_stderr("x11grab: cannot open display")
    assert "cannot open display" in rec._error_message()


def test_remux_success_removes_mkv(monkeypatch, tmp_path):
    rec = _make_recorder(tmp_path, monkeypatch)
    rec.capture_file.write_bytes(b"mkv")
    monkeypatch.setattr(screen, "ffmpeg_path", lambda: "/ff")

    def fake_run(cmd, **kw):
        rec.output_file.write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(screen.subprocess, "run", fake_run)
    rec._remux()
    assert rec.output_file.exists()
    assert not rec.capture_file.exists()


def test_remux_failure_keeps_mkv_and_warns(monkeypatch, tmp_path):
    rec = _make_recorder(tmp_path, monkeypatch)
    rec.capture_file.write_bytes(b"mkv")
    monkeypatch.setattr(screen, "ffmpeg_path", lambda: "/ff")
    monkeypatch.setattr(
        screen.subprocess, "run",
        lambda cmd, **kw: SimpleNamespace(returncode=1, stderr="boom"),
    )
    with pytest.warns(UserWarning, match="could not remux"):
        rec._remux()
    assert rec.capture_file.exists()
