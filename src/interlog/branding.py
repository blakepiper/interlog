"""Shared branding for the CLI.

Renders the InterLog logo, with a cyan→blue ANSI gradient when the terminal
supports it and plain text otherwise (so it never garbles a pipe, file, or
legacy console).
"""

import os
import sys

_ART = """
██╗███╗   ██╗████████╗███████╗██████╗ ██╗      ██████╗  ██████╗ 
██║████╗  ██║╚══██╔══╝██╔════╝██╔══██╗██║     ██╔═══██╗██╔════╝ 
██║██╔██╗ ██║   ██║   █████╗  ██████╔╝██║     ██║   ██║██║  ███╗
██║██║╚██╗██║   ██║   ██╔══╝  ██╔══██╗██║     ██║   ██║██║   ██║
██║██║ ╚████║   ██║   ███████╗██║  ██║███████╗╚██████╔╝╚██████╔╝
╚═╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝  ╚═════╝ """

_TAGLINE = "capture . measure . replay"
_SUBTITLE = "interaction logging for HCI research"

# Per-line cyan→blue gradient applied down the logo (xterm-256 color indices).
_GRADIENT = [87, 51, 45, 39, 33, 27]

_BLUE = "\033[38;5;39m"
_YELLOW = "\033[38;5;221m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_ART_WIDTH = 64


def _center(text):
    """Left padding to center ``text`` under the logo."""
    return " " * max(0, (_ART_WIDTH - len(text)) // 2)


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


def _gradient_art():
    """The logo with a cyan→blue vertical gradient, one color per line."""
    lines = _ART.split("\n")[1:]  # drop the leading blank line
    out = []
    for i, line in enumerate(lines):
        color = _GRADIENT[min(i, len(_GRADIENT) - 1)]
        out.append(f"{_BOLD}\033[38;5;{color}m{line}{_RESET}")
    return "\n" + "\n".join(out)


def banner(color=None):
    """Return the banner as a string."""
    if color is None:
        color = _supports_color()

    chev_text = f">>>>  {_TAGLINE}  <<<<"
    chev_pad = _center(chev_text)
    sub_pad = _center(_SUBTITLE)

    if not color:
        return f"{_ART}\n{chev_pad}{chev_text}\n{sub_pad}{_SUBTITLE}"

    chevrons = (
        f"{chev_pad}{_BOLD}{_YELLOW}>>>>  {_RESET}"
        f"{_BLUE}{_TAGLINE}{_RESET}{_BOLD}{_YELLOW}  <<<<{_RESET}"
    )
    subtitle = f"{sub_pad}{_DIM}{_SUBTITLE}{_RESET}"
    return f"{_gradient_art()}\n{chevrons}\n{subtitle}"


def print_banner(color=None):
    print(banner(color))
