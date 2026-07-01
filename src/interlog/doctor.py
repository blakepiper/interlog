"""Environment diagnostics for InterLog.

Checks the Python version and pynput install, and can run a live listener
smoke test to confirm input capture works (useful for diagnosing OS
permission issues on macOS/Linux).
"""

import importlib.metadata
import sys
import time


def _ok(console, msg):
    console.print(f"  [bold green]✓[/bold green]  {msg}")


def _warn(console, msg):
    console.print(f"  [bold yellow]![/bold yellow]  {msg}")


def _fail(console, msg):
    console.print(f"  [bold red]✗[/bold red]  {msg}")


def _check_python_version(console):
    v = sys.version_info
    if (v.major, v.minor) >= (3, 9):
        _ok(console, f"Python [cyan]{v.major}.{v.minor}.{v.micro}[/cyan]")
        return True
    _fail(console, f"Python [cyan]{v.major}.{v.minor}.{v.micro}[/cyan]  [dim](need 3.9+)[/dim]")
    return False


def _check_pynput(console):
    try:
        import pynput  # noqa: F401
        try:
            version = importlib.metadata.version("pynput")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        _ok(console, f"pynput [cyan]{version}[/cyan]")
        return True
    except ImportError:
        _fail(console, "pynput not installed")
        console.print("       [dim]Reinstall InterLog from the repo: pip install .[/dim]")
        return False


def _check_ffmpeg(console):
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        _ok(console, f"ffmpeg  [dim]({path})[/dim]")
    else:
        _warn(console, "ffmpeg not found  [dim](optional — only needed for record --screen)[/dim]")


def _check_rich(console):
    try:
        version = importlib.metadata.version("rich")
        _ok(console, f"rich [cyan]{version}[/cyan]")
    except Exception:
        _warn(console, "rich not installed  [dim](install for better output)[/dim]")


def _check_heatmap_deps(console):
    missing = []
    for pkg, import_name in [("matplotlib", "matplotlib"), ("numpy", "numpy"), ("Pillow", "PIL")]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        _fail(console, f"Heatmap deps missing: {', '.join(missing)}  "
              f"[dim](required — needed for 'interlog heatmap')[/dim]")
        console.print("       [dim]Reinstall InterLog from the repo: pip install .[/dim]")
    else:
        try:
            mpl_v = importlib.metadata.version("matplotlib")
        except Exception:
            mpl_v = "?"
        _ok(console, f"Heatmap deps  [dim](matplotlib {mpl_v})[/dim]")


def _check_display_server(console):
    """Report the display server (Linux only)."""
    if sys.platform != "linux":
        return
    import os
    session = os.environ.get("XDG_SESSION_TYPE", "")
    display = os.environ.get("DISPLAY", "")
    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    if session == "wayland":
        xw = f"  [dim](XWayland: {display})[/dim]" if display else ""
        _ok(console, f"Display  [dim]Wayland ({wayland}){xw}[/dim]")
    elif display:
        _ok(console, f"Display  [dim]X11 ({display})[/dim]")
    else:
        _warn(console, f"Display  [dim]{session or 'unknown'}[/dim]")


def _check_wayland_screen_deps(console):
    """Check Wayland screen-capture dependencies (Linux Wayland only)."""
    if sys.platform != "linux":
        return
    import os
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return
    try:
        import jeepney  # noqa: F401
        ver = importlib.metadata.version("jeepney")
        _ok(console, f"jeepney [cyan]{ver}[/cyan]  [dim](Wayland portal screen capture)[/dim]")
    except ImportError:
        _warn(console, "jeepney not installed  [dim](needed for 'record --screen' on Wayland)[/dim]")
        console.print("       [dim]pip install jeepney[/dim]")


def _run_live_test(console):
    from pynput import keyboard, mouse

    console.print()
    console.rule("[bold]Live Capture Test[/bold]", style="cyan dim")
    console.print("  Move the mouse, click, scroll, or type to generate events.")
    console.print("  Press [bold]ESC[/bold] to finish.\n")

    count = {"n": 0}

    def bump(label):
        count["n"] += 1
        print(f"\r  {label:<22}  events captured: {count['n']}", end="", flush=True)

    def on_release(key):
        if key == keyboard.Key.esc:
            return False
        return None

    mouse_listener = mouse.Listener(
        on_move=lambda x, y: bump("mouse move"),
        on_click=lambda x, y, b, p: bump("mouse click"),
        on_scroll=lambda x, y, dx, dy: bump("scroll"),
    )
    keyboard_listener = keyboard.Listener(
        on_press=lambda k: bump("key press"),
        on_release=on_release,
    )

    mouse_listener.start()
    keyboard_listener.start()
    start = time.monotonic()
    try:
        while keyboard_listener.is_alive():
            keyboard_listener.join(0.5)
            # If nothing is captured within a few seconds, input capture isn't
            # working (the exact failure this command diagnoses) — don't hang
            # waiting for an ESC key that will never arrive.
            if count["n"] == 0 and time.monotonic() - start > 8:
                break
    except KeyboardInterrupt:
        pass
    finally:
        mouse_listener.stop()
        keyboard_listener.stop()

    print()
    console.print()
    if count["n"] == 0:
        _fail(console, "No events captured — likely an OS permissions issue")
        console.print("  [dim]macOS: System Settings › Privacy › Accessibility → add your terminal[/dim]")
        console.print("  [dim]Linux: add your user to the 'input' group, or check Wayland vs X11[/dim]")
        return False
    _ok(console, f"Input capture working  [dim]({count['n']} events captured)[/dim]")
    return True


def run_doctor(live=False):
    """Run environment checks. Returns an exit code (0 = healthy)."""
    from rich.console import Console

    console = Console(highlight=False)

    console.print()
    console.rule("[bold cyan]InterLog Doctor[/bold cyan]", style="cyan dim")
    console.print()

    python_ok = _check_python_version(console)
    pynput_ok = _check_pynput(console)
    _check_ffmpeg(console)
    _check_rich(console)
    _check_heatmap_deps(console)
    _check_display_server(console)
    _check_wayland_screen_deps(console)

    console.print()
    if python_ok and pynput_ok:
        console.print("  [green]Core checks passed.[/green]")
    else:
        console.print("  [red]Some checks failed — see above.[/red]")
        console.print()
        return 1

    if live:
        result = _run_live_test(console)
        console.print()
        return 0 if result else 1

    if not live:
        console.print("  [dim]Tip: run 'interlog doctor --live' to confirm input capture works.[/dim]")

    console.print()
    return 0
