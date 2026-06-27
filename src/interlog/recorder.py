"""Interaction recorder: captures mouse and keyboard events to CSV."""

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from threading import Event

from interlog.branding import print_banner

# Column order for the events CSV. Defined once so the header and every
# subsequent flush stay in sync.
EVENT_FIELDS = [
    "timestamp", "event_type", "x", "y", "button",
    "dx", "dy", "key", "start_x", "start_y", "end_x", "end_y",
]

# How many buffered events trigger a flush to disk.
FLUSH_THRESHOLD = 10


class InteractionLogger:
    """Captures and logs keyboard and mouse interactions."""

    def __init__(self, output_dir="interlog-data", privacy_mode=False, session_name=None):
        """
        Initialize the interaction logger.

        Args:
            output_dir: Root data directory. Each session gets its own subfolder
                inside it (named after session_name / the start timestamp).
            privacy_mode: If True, only log that keys were pressed, not which keys.
            session_name: Name for this session (auto-generated if None).
        """
        self.privacy_mode = privacy_mode
        self.session_name = session_name or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Each session lives in its own subfolder under the data directory, with
        # clean filenames inside (the folder, not a prefix, identifies the session).
        self.output_dir = Path(output_dir)
        self.session_dir = self.output_dir / self.session_name
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Event storage
        self.events = []
        self.total_events = 0
        self.start_time = None       # wall clock (for metadata display only)
        self._mono_start = None      # monotonic clock (source of truth for timing)
        self.stop_event = Event()

        # Output file paths
        self.events_file = self.session_dir / "events.csv"
        self.metadata_file = self.session_dir / "metadata.json"

        # Listeners
        self.mouse_listener = None
        self.keyboard_listener = None

        # Drag state: a drag is a press, followed by movement, then a release.
        self.drag_start_pos = None
        self.is_dragging = False

        # Optional companion screen recording (set by `record --screen`).
        self.video_file = None              # Path to the recording, if any
        self.video_first_frame_time = None  # monotonic time of the video's first frame
        self.video_start_offset = None      # seconds into the video at logger t=0
        self.capture_region = None          # {x, y, width, height, dpi_scale} of the capture
        self.stop_callback = None           # called during stop() (e.g. stop ffmpeg)

    def _get_timestamp(self):
        """Get relative timestamp in seconds since session start.

        Uses a monotonic clock so timestamps are immune to wall-clock
        adjustments (NTP, DST, manual changes) during a session.
        """
        if self._mono_start is None:
            return 0.0
        return time.monotonic() - self._mono_start

    def _log_event(self, event_type, **kwargs):
        """Log an interaction event with timestamp."""
        event = {
            "timestamp": self._get_timestamp(),
            "event_type": event_type,
            **kwargs,
        }
        self.events.append(event)
        self.total_events += 1

    # Mouse event handlers
    def on_move(self, x, y):
        """Handle mouse move events."""
        # Movement while a button is held marks the gesture as a drag.
        if self.drag_start_pos is not None:
            self.is_dragging = True
        self._log_event("mouse_move", x=x, y=y)

    def on_click(self, x, y, button, pressed):
        """Handle mouse click events."""
        if pressed:
            self._log_event("mouse_down", x=x, y=y, button=str(button))
            # Begin tracking a potential drag from this point.
            self.drag_start_pos = (x, y)
            self.is_dragging = False
        else:
            self._log_event("mouse_up", x=x, y=y, button=str(button))

            # If the pointer moved while held, record the completed drag.
            if self.is_dragging and self.drag_start_pos:
                self._log_event(
                    "drag",
                    start_x=self.drag_start_pos[0],
                    start_y=self.drag_start_pos[1],
                    end_x=x,
                    end_y=y,
                )
            self.drag_start_pos = None
            self.is_dragging = False

    def on_scroll(self, x, y, dx, dy):
        """Handle mouse scroll events."""
        self._log_event("scroll", x=x, y=y, dx=dx, dy=dy)

    # Keyboard event handlers
    def _key_to_str(self, key):
        """Return a printable representation of a key, honoring privacy mode."""
        if self.privacy_mode:
            return "[REDACTED]"
        try:
            return key.char if hasattr(key, "char") and key.char is not None else str(key)
        except AttributeError:
            return str(key)

    def on_press(self, key):
        """Handle key press events."""
        self._log_event("key_press", key=self._key_to_str(key))

    def on_release(self, key):
        """Handle key release events."""
        self._log_event("key_release", key=self._key_to_str(key))

    def start(self):
        """Start capturing interactions. Blocks until interrupted."""
        from rich.console import Console
        from rich.live import Live

        console = Console(highlight=False)

        self.start_time = time.time()
        self._mono_start = time.monotonic()

        # If a screen recording is already rolling, compute how far into the
        # video this session's t=0 lands, so the viewer can pre-align them.
        # Both clocks are monotonic, so the difference is drift-free.
        if self.video_first_frame_time is not None:
            self.video_start_offset = self._mono_start - self.video_first_frame_time

        print_banner()
        console.print()
        console.rule("[bold cyan]Recording[/bold cyan]", style="cyan dim")
        console.print()
        console.print(f"  [dim]Session[/dim]  [white]{self.session_name}[/white]")
        privacy_str = "[yellow]on[/yellow]" if self.privacy_mode else "[dim]off[/dim]"
        console.print(f"  [dim]Privacy[/dim]  {privacy_str}")
        console.print(f"  [dim]Output[/dim]   [white]{self.session_dir}[/white]")
        if self.video_file:
            console.print(f"  [dim]Video[/dim]    [white]{Path(self.video_file).name}[/white]")
        console.print()

        # Save initial metadata
        metadata = {
            "session_name": self.session_name,
            "start_time": datetime.now().isoformat(),
            "privacy_mode": self.privacy_mode,
            "session_dir": str(self.session_dir.absolute()),
        }
        if self.video_file is not None:
            metadata["video_file"] = Path(self.video_file).name
            metadata["video_start_offset"] = round(self.video_start_offset or 0.0, 3)
            if self.capture_region is not None:
                metadata["capture_region"] = self.capture_region
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        # Start listeners (pynput imported lazily so the rest of the package -
        # analysis, viewer, tests - doesn't require an input backend/display).
        from pynput import keyboard, mouse

        self.mouse_listener = mouse.Listener(
            on_move=self.on_move,
            on_click=self.on_click,
            on_scroll=self.on_scroll,
        )
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release,
        )

        self.mouse_listener.start()
        self.keyboard_listener.start()

        # Write CSV header
        with open(self.events_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
            writer.writeheader()

        try:
            with Live("", refresh_per_second=2, console=console, transient=True) as live:
                while not self.stop_event.is_set():
                    time.sleep(0.5)
                    # Flush every tick so an unclean exit loses at most ~0.5s of events.
                    if self.events:
                        self._flush_events()
                    elapsed = self._get_timestamp()
                    m, s = divmod(int(elapsed), 60)
                    live.update(
                        f"  [green]●[/green]  [bold white]{self.total_events:,}[/bold white] events"
                        f"  [dim]{m}:{s:02d}  ·  Ctrl+C to stop[/dim]"
                    )
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Stop capturing and save all events."""
        from rich.console import Console
        console = Console(highlight=False)

        self.stop_event.set()

        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()

        # Stop any companion screen recording (finalizes the video file).
        if self.stop_callback:
            try:
                console.print("  [dim]Finalizing screen recording…[/dim]")
                self.stop_callback()
            except Exception as e:
                console.print(f"  [yellow]![/yellow]  Screen recorder: {e}")

        # Flush remaining events
        self._flush_events()

        # Update metadata with end time and totals
        try:
            with open(self.metadata_file) as f:
                metadata = json.load(f)
            metadata["end_time"] = datetime.now().isoformat()
            metadata["duration_seconds"] = self._get_timestamp()
            metadata["total_events"] = self.total_events
            with open(self.metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            console.print(f"  [yellow]![/yellow]  Could not update metadata: {e}")

        dur = self._get_timestamp()
        m, s = divmod(int(dur), 60)
        session = str(self.session_dir)

        console.print()
        console.rule("[dim]Session saved[/dim]", style="dim")
        console.print()
        console.print(f"  [green]✓[/green]  [bold white]{self.session_name}[/bold white]  [dim]→[/dim]  [white]{session}[/white]")
        console.print()
        console.print(f"  [dim]Events  [/dim]  [cyan]{self.total_events:,}[/cyan]")
        console.print(f"  [dim]Duration[/dim]  [cyan]{m}:{s:02d}[/cyan]")
        if self.video_file:
            console.print(f"  [dim]Video   [/dim]  [white]{Path(self.video_file).name}[/white]")

        console.print()
        console.rule("[dim]Next steps[/dim]", style="dim")
        console.print(f"  [bold cyan]interlog analyze[/bold cyan] [white]{session}[/white]")
        console.print(f"  [bold cyan]interlog heatmap[/bold cyan] [white]{session}[/white]")
        if self.video_file:
            console.print(f"  [bold cyan]interlog view[/bold cyan] [white]{session}[/white] [dim]--serve[/dim]")
        else:
            console.print(f"  [bold cyan]interlog view[/bold cyan] [white]{session}[/white]")
        console.print(f"  [bold cyan]interlog report[/bold cyan] [white]{session}[/white]")
        console.print()

    def _flush_events(self):
        """Write accumulated events to CSV file.

        Listener threads append to ``self.events`` concurrently, so we detach
        the current buffer with a single atomic rebind before writing. Writing
        the old list and clearing it separately would drop any event appended
        in between; swapping first means those events simply land in the next
        flush instead of being lost.
        """
        if not self.events:
            return

        batch, self.events = self.events, []

        with open(self.events_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
            writer.writerows(batch)
