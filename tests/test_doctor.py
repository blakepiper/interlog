"""Tests for interlog.doctor: environment checks with a captured console."""

import io
import sys
from types import SimpleNamespace

from interlog import doctor


def _doctor_console():
    from rich.console import Console
    buf = io.StringIO()
    return Console(file=buf, highlight=False, force_terminal=False), buf


def test_check_python_version_pass_and_fail(monkeypatch):
    console, buf = _doctor_console()
    assert doctor._check_python_version(console) is True
    assert "Python" in buf.getvalue()

    console, buf = _doctor_console()
    monkeypatch.setattr(sys, "version_info", SimpleNamespace(major=3, minor=8, micro=0))
    assert doctor._check_python_version(console) is False
    assert "✗" in buf.getvalue()


def test_check_ffmpeg_present_and_absent(monkeypatch):
    console, buf = _doctor_console()
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")
    doctor._check_ffmpeg(console)
    assert "ffmpeg" in buf.getvalue() and "✓" in buf.getvalue()

    console, buf = _doctor_console()
    monkeypatch.setattr("shutil.which", lambda name: None)
    doctor._check_ffmpeg(console)
    assert "not found" in buf.getvalue() and "!" in buf.getvalue()


def test_check_heatmap_deps_warns_when_missing(monkeypatch):
    console, buf = _doctor_console()
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name in ("matplotlib", "numpy", "PIL"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    doctor._check_heatmap_deps(console)
    out = buf.getvalue()
    assert "missing" in out and "matplotlib" in out


def test_check_display_server_early_returns_off_linux(monkeypatch):
    console, buf = _doctor_console()
    monkeypatch.setattr(sys, "platform", "darwin")
    doctor._check_display_server(console)
    assert buf.getvalue() == ""


def test_check_display_server_reports_x11(monkeypatch):
    console, buf = _doctor_console()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    doctor._check_display_server(console)
    assert "X11" in buf.getvalue()


def test_check_wayland_screen_deps_skips_off_wayland(monkeypatch):
    console, buf = _doctor_console()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    doctor._check_wayland_screen_deps(console)
    assert buf.getvalue() == ""


def test_run_doctor_healthy_returns_zero(monkeypatch):
    monkeypatch.setattr(doctor, "_check_python_version", lambda c: True)
    monkeypatch.setattr(doctor, "_check_pynput", lambda c: True)
    assert doctor.run_doctor(live=False) == 0


def test_run_doctor_unhealthy_returns_one(monkeypatch):
    monkeypatch.setattr(doctor, "_check_python_version", lambda c: True)
    monkeypatch.setattr(doctor, "_check_pynput", lambda c: False)
    assert doctor.run_doctor(live=False) == 1
