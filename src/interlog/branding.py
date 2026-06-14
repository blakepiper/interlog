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

_CYAN = "\033[38;5;44m"
_BLUE = "\033[38;5;39m"
_YELLOW = "\033[38;5;221m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _enable_color():
    """Return True if we should emit ANSI color (enabling VT on Windows)."""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VT_PROCESSING
        except Exception:
            return False
    return True


def banner(color=None):
    """Return the banner as a string."""
    if color is None:
        color = _enable_color()

    chevrons = f"   >>>>  {_TAGLINE}  <<<<"
    subtitle = f"        {_SUBTITLE}"

    if not color:
        return f"{_ART}\n{chevrons}\n{subtitle}"

    art = f"{_BOLD}{_CYAN}{_ART}{_RESET}"
    chevrons = f"{_BOLD}{_YELLOW}   >>>>  {_RESET}{_BLUE}{_TAGLINE}{_RESET}{_BOLD}{_YELLOW}  <<<<{_RESET}"
    subtitle = f"{_DIM}        {_SUBTITLE}{_RESET}"
    return f"{art}\n{chevrons}\n{subtitle}"


def print_banner(color=None):
    print(banner(color))
