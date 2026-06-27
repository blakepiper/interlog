"""Shared ASCII branding for the CLI.

Renders the InterLog banner, with ANSI color when the terminal supports it and
plain ASCII otherwise (so it never garbles a pipe, a file, or a legacy console).
"""

import os
import sys

_ART = r"""
     ____      __            __
    /  _/___  / /____  _____/ /___  ____ _
    / // __ \/ __/ _ \/ ___/ / __ \/ __ `/
  _/ // / / / /_/  __/ /  / / /_/ / /_/ /
 /___/_/ /_/\__/\___/_/  /_/\____/\__, /
                                 /____/"""

_TAGLINE = "capture . measure . replay"
_SUBTITLE = "interaction logging for HCI research"

# Per-line cyan→blue gradient applied down the logo (xterm-256 color indices).
_GRADIENT = [87, 51, 45, 39, 33, 27]

_BLUE = "\033[38;5;39m"
_YELLOW = "\033[38;5;221m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _gradient_art():
    """The logo with a cyan→blue vertical gradient, one color per line."""
    lines = _ART.split("\n")[1:]  # drop the leading blank line
    out = []
    for i, line in enumerate(lines):
        color = _GRADIENT[min(i, len(_GRADIENT) - 1)]
        out.append(f"{_BOLD}\033[38;5;{color}m{line}{_RESET}")
    return "\n" + "\n".join(out)


def _enable_windows_vt():
    """Enable ANSI escape processing on the Windows console. Returns success."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VT_PROCESSING
        return True
    except Exception:
        return False


def _supports_color():
    """Return True if we should emit ANSI color (enabling VT on Windows)."""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        return _enable_windows_vt()
    return True


def banner(color=None):
    """Return the banner as a string."""
    if color is None:
        color = _supports_color()

    if not color:
        chevrons = f"   >>>>  {_TAGLINE}  <<<<"
        subtitle = f"        {_SUBTITLE}"
        return f"{_ART}\n{chevrons}\n{subtitle}"

    chevrons = f"{_BOLD}{_YELLOW}   >>>>  {_RESET}{_BLUE}{_TAGLINE}{_RESET}{_BOLD}{_YELLOW}  <<<<{_RESET}"
    subtitle = f"{_DIM}        {_SUBTITLE}{_RESET}"
    return f"{_gradient_art()}\n{chevrons}\n{subtitle}"


def print_banner(color=None):
    print(banner(color))
