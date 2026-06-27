"""InterLog - Interaction logger for HCI research.

Captures timestamped keyboard and mouse events, optionally records the screen,
and turns a session into structured, analyzable data. Everything runs locally —
no cloud, no accounts, no telemetry.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("interlog")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
