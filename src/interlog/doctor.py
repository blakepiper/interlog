"""Environment diagnostics for InterLog.

Checks the Python version and pynput install, and can run a live listener
smoke test to confirm input capture works (useful for diagnosing OS
permission issues on macOS/Linux).
"""

import sys


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
        import importlib.metadata
        import pynput  # noqa: F401
        try:
            version = importlib.metadata.version("pynput")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        _ok(console, f"pynput [cyan]{version}[/cyan]")
        return True
    except ImportError:
        _fail(console, "pynput not installed")
        console.print("       [dim]Run: pip install interlog   (or: pip install pynput)[/dim]")
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
        import importlib.metadata
        version = importlib.metadata.version("rich")
        _ok(console, f"rich [cyan]{version}[/cyan]")
    except Exception:
        _warn(console, "rich not installed  [dim](install for better output)[/dim]")


def _check_heatmap_deps(console):
    import importlib.metadata
    missing = []
    for pkg, import_name in [("matplotlib", "matplotlib"), ("numpy", "numpy"), ("Pillow", "PIL")]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        _warn(console, f"Heatmap deps missing: {', '.join(missing)}  "
              f"[dim](optional — needed for 'interlog heatmap')[/dim]")
        console.print("       [dim]pip install 'interlog[heatmap]'[/dim]")
    else:
        try:
            mpl_v = importlib.metadata.version("matplotlib")
        except Exception:
            mpl_v = "?"
        _ok(console, f"Heatmap deps  [dim](matplotlib {mpl_v})[/dim]")


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
    try:
        keyboard_listener.join()
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

    console.print()
    if python_ok and pynput_ok:
        console.print("  [green]Core checks passed.[/green]")
    else:
        console.print("  [red]Some checks failed — see above.[/red]")
        console.print()
        return 1

    if live and pynput_ok:
        result = _run_live_test(console)
        console.print()
        return 0 if result else 1

    if not live:
        console.print("  [dim]Tip: run 'interlog doctor --live' to confirm input capture works.[/dim]")

    console.print()
    return 0
