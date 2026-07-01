"""Tests for interlog.branding: banner rendering and color detection."""

from interlog import branding


def test_banner_plain_has_no_ansi():
    out = branding.banner(color=False)
    assert "\033[" not in out
    assert "capture . measure . replay" in out


def test_banner_color_has_ansi():
    assert "\033[" in branding.banner(color=True)


def test_supports_color_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert branding._supports_color() is False
