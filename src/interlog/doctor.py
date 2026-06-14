"""Environment diagnostics for InterLog.

Checks the Python version and pynput install, and can run a live listener
smoke test to confirm input capture works (useful for diagnosing OS
permission issues on macOS/Linux).
"""

import sys


def _check_python_version():
    """Check Python version is 3.7+."""
    v = sys.version_info
    if (v.major, v.minor) >= (3, 7):
        print(f"[OK] Python {v.major}.{v.minor}.{v.micro}")
        return True
    print(f"[FAIL] Python {v.major}.{v.minor}.{v.micro} (need 3.7+)")
    return False


def _check_pynput():
    """Check if pynput is installed and importable."""
    try:
        import importlib.metadata
        import pynput  # noqa: F401  (import proves it loads)
        try:
            version = importlib.metadata.version("pynput")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        print(f"[OK] pynput is installed (version {version})")
        return True
    except ImportError:
        print("[FAIL] pynput is NOT installed")
        print("  Run: pip install interlog   (or: pip install pynput)")
        return False


def _run_live_test():
    """Start listeners and report captured events. Press ESC to stop."""
    from pynput import keyboard, mouse

    print("\nLive capture test")
    print("-" * 40)
    print("Move the mouse, click, scroll, or type to generate events.")
    print("Press ESC to finish.\n")

    count = {"n": 0}

    def bump(label):
        count["n"] += 1
        print(f"  {label} - events: {count['n']}", end="\r")

    def on_release(key):
        if key == keyboard.Key.esc:
            return False

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

    print(f"\n\nCaptured {count['n']} events.")
    if count["n"] == 0:
        print("[WARNING] No events captured - likely an OS permissions issue:")
        print("  - macOS: System Settings > Privacy & Security > Accessibility,")
        print("    then add your terminal/IDE.")
        print("  - Linux: add your user to the 'input' group, or note that")
        print("    pynput has limited support under Wayland (try X11).")
        return False
    print("[OK] Input capture is working.")
    return True


def _check_ffmpeg():
    """Check for ffmpeg, which is optional (only `record --screen` needs it)."""
    import shutil

    path = shutil.which("ffmpeg")
    if path:
        print(f"[OK] ffmpeg found ({path})")
    else:
        print("[--] ffmpeg not found (optional; only needed for 'record --screen')")
    return True  # never fatal


def run_doctor(live=False):
    """Run environment checks. Returns an exit code (0 = healthy)."""
    print("InterLog environment check")
    print("=" * 40)

    python_ok = _check_python_version()
    pynput_ok = _check_pynput()
    _check_ffmpeg()

    print("=" * 40)
    if python_ok and pynput_ok:
        print("Core checks passed.")
    else:
        print("Some checks failed - see messages above.")
        return 1

    if live and pynput_ok:
        return 0 if _run_live_test() else 1

    if not live:
        print("Tip: run 'interlog doctor --live' to test input capture.")
    return 0
