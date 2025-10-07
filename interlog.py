#!/usr/bin/env python3
"""
InterLog - Interaction Logger for UX Researchers
Captures keyboard and mouse events with timestamps for analysis alongside screen recordings.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Thread, Event

from pynput import mouse, keyboard


class InteractionLogger:
    """Captures and logs keyboard and mouse interactions."""

    def __init__(self, output_dir=".", privacy_mode=False, session_name=None):
        """
        Initialize the interaction logger.

        Args:
            output_dir: Directory to save output files
            privacy_mode: If True, only log that keys were pressed, not which keys
            session_name: Name for this session (auto-generated if None)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.privacy_mode = privacy_mode
        self.session_name = session_name or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Event storage
        self.events = []
        self.total_events = 0
        self.start_time = None
        self.stop_event = Event()

        # Output file paths
        self.events_file = self.output_dir / f"{self.session_name}_events.csv"
        self.metadata_file = self.output_dir / f"{self.session_name}_metadata.json"

        # Listeners
        self.mouse_listener = None
        self.keyboard_listener = None

        # Track drag state
        self.is_dragging = False
        self.drag_start_pos = None

    def _get_timestamp(self):
        """Get relative timestamp in seconds since session start."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def _log_event(self, event_type, **kwargs):
        """Log an interaction event with timestamp."""
        event = {
            'timestamp': self._get_timestamp(),
            'event_type': event_type,
            **kwargs
        }
        self.events.append(event)
        self.total_events += 1

        # Print event count every 50 events for feedback
        if self.total_events % 50 == 0:
            print(f"  Events captured: {self.total_events}", end='\r')

    # Mouse event handlers
    def on_move(self, x, y):
        """Handle mouse move events."""
        self._log_event('mouse_move', x=x, y=y)

    def on_click(self, x, y, button, pressed):
        """Handle mouse click events."""
        if pressed:
            self._log_event('mouse_down', x=x, y=y, button=str(button))
        else:
            self._log_event('mouse_up', x=x, y=y, button=str(button))

            # Check if this was a drag
            if self.is_dragging and self.drag_start_pos:
                self._log_event('drag',
                               start_x=self.drag_start_pos[0],
                               start_y=self.drag_start_pos[1],
                               end_x=x,
                               end_y=y)
                self.is_dragging = False
                self.drag_start_pos = None

    def on_scroll(self, x, y, dx, dy):
        """Handle mouse scroll events."""
        self._log_event('scroll', x=x, y=y, dx=dx, dy=dy)

    # Keyboard event handlers
    def on_press(self, key):
        """Handle key press events."""
        if self.privacy_mode:
            # Privacy mode: don't log which key
            self._log_event('key_press', key='[REDACTED]')
        else:
            try:
                # Try to get character representation
                key_str = key.char if hasattr(key, 'char') else str(key)
            except AttributeError:
                key_str = str(key)

            self._log_event('key_press', key=key_str)

    def on_release(self, key):
        """Handle key release events."""
        if self.privacy_mode:
            self._log_event('key_release', key='[REDACTED]')
        else:
            try:
                key_str = key.char if hasattr(key, 'char') else str(key)
            except AttributeError:
                key_str = str(key)

            self._log_event('key_release', key=key_str)

    def start(self):
        """Start capturing interactions."""
        self.start_time = time.time()

        # Print ASCII art banner (Ogre font style)
        print(r"""
  ___       _              _
 |_ _|_ __ | |_ ___ _ __  | |    ___   __ _
  | || '_ \| __/ _ \ '__| | |   / _ \ / _` |
  | || | | | ||  __/ |    | |__| (_) | (_| |
 |___|_| |_|\__\___|_|    |_____\___/ \__, |
                                      |___/
        Interaction Logger for UX Research
        """)

        print(f"Session:  {self.session_name}")
        print(f"Privacy:  {'ENABLED' if self.privacy_mode else 'DISABLED'}")
        print(f"Output:   {self.output_dir.absolute()}")
        print("\nRecording... Press Ctrl+C to stop.\n")

        # Save metadata
        metadata = {
            'session_name': self.session_name,
            'start_time': datetime.now().isoformat(),
            'privacy_mode': self.privacy_mode,
            'output_dir': str(self.output_dir.absolute())
        }
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Start listeners
        self.mouse_listener = mouse.Listener(
            on_move=self.on_move,
            on_click=self.on_click,
            on_scroll=self.on_scroll
        )

        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )

        self.mouse_listener.start()
        self.keyboard_listener.start()

        # Write CSV header
        with open(self.events_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'event_type', 'x', 'y', 'button',
                'dx', 'dy', 'key', 'start_x', 'start_y', 'end_x', 'end_y'
            ])
            writer.writeheader()

        try:
            # Keep running until interrupted
            while not self.stop_event.is_set():
                time.sleep(0.5)

                # Periodically flush events to disk (every 10 events or every 0.5s)
                if len(self.events) >= 10:
                    self._flush_events()

        except KeyboardInterrupt:
            print("\n\nStopping...")

        finally:
            self.stop()

    def stop(self):
        """Stop capturing and save all events."""
        self.stop_event.set()

        # Stop listeners
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()

        # Flush remaining events
        self._flush_events()

        # Update metadata with end time
        try:
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)

            metadata['end_time'] = datetime.now().isoformat()
            metadata['duration_seconds'] = self._get_timestamp()
            metadata['total_events'] = self.total_events

            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not update metadata: {e}")

        print(f"\nSession saved!")
        print(f"Events: {self.events_file}")
        print(f"Metadata: {self.metadata_file}")
        print(f"\nTotal events captured: {self.total_events}")
        print(f"Duration: {self._get_timestamp():.2f} seconds")
        print(f"\nRun analyzer to generate statistics:")
        print(f"  python analyzer.py {self.events_file}")

    def _flush_events(self):
        """Write accumulated events to CSV file."""
        if not self.events:
            return

        with open(self.events_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'event_type', 'x', 'y', 'button',
                'dx', 'dy', 'key', 'start_x', 'start_y', 'end_x', 'end_y'
            ])
            writer.writerows(self.events)

        self.events.clear()


def main():
    """Main entry point for InterLog."""
    parser = argparse.ArgumentParser(
        description="InterLog - Interaction Logger for UX Researchers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start basic session
  python interlog.py

  # Enable privacy mode (doesn't log which keys)
  python interlog.py --privacy

  # Custom output directory and session name
  python interlog.py --output ./sessions --name user_study_p1
        """
    )

    parser.add_argument(
        '--output', '-o',
        default='.',
        help='Output directory for session files (default: current directory)'
    )

    parser.add_argument(
        '--name', '-n',
        default=None,
        help='Session name (default: auto-generated timestamp)'
    )

    parser.add_argument(
        '--privacy', '-p',
        action='store_true',
        help='Enable privacy mode (log key events without recording which keys)'
    )

    args = parser.parse_args()

    # Create and start logger
    logger = InteractionLogger(
        output_dir=args.output,
        privacy_mode=args.privacy,
        session_name=args.name
    )

    logger.start()


if __name__ == '__main__':
    main()
