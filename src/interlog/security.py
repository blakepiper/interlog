"""Small filesystem-hardening helpers for captured session data.

Sessions write plaintext keystrokes, coordinates, and optionally video to disk.
These land with whatever the process umask allows, which on a multi-user machine
can be world-readable. ``lock_down`` restricts each file/dir to the owner right
after it is created. Best-effort: it never raises, so it can't take down a
recording, and it is a no-op on non-POSIX platforms (Windows ACLs differ).
"""

import os


def lock_down(path, is_dir=False):
    """Restrict a path to owner-only access. No-op on non-POSIX."""
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o700 if is_dir else 0o600)
    except OSError:
        pass  # best-effort; don't crash a session over this
