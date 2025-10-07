#!/usr/bin/env python3
"""
InterLog Analyzer - Statistical analysis of interaction logs
Generates summary statistics and interaction intensity data.
"""

import argparse
import csv
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path


class InteractionAnalyzer:
    """Analyzes interaction logs and generates statistics."""

    def __init__(self, events_file):
        """
        Initialize analyzer with events file.

        Args:
            events_file: Path to the events CSV file
        """
        self.events_file = Path(events_file)
        self.events = []
        self.stats = {}

    def load_events(self):
        """Load events from CSV file."""
        print(f"Loading events from {self.events_file}...")

        with open(self.events_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                if row.get('timestamp'):
                    row['timestamp'] = float(row['timestamp'])
                if row.get('x'):
                    row['x'] = int(float(row['x']))
                if row.get('y'):
                    row['y'] = int(float(row['y']))
                if row.get('dx'):
                    row['dx'] = int(float(row['dx']))
                if row.get('dy'):
                    row['dy'] = int(float(row['dy']))

                self.events.append(row)

        print(f"Loaded {len(self.events)} events")

    def calculate_statistics(self):
        """Calculate summary statistics from events."""
        if not self.events:
            print("No events to analyze")
            return

        print("Calculating statistics...")

        # Basic counts
        event_counts = defaultdict(int)
        for event in self.events:
            event_counts[event['event_type']] += 1

        # Session duration
        timestamps = [e['timestamp'] for e in self.events]
        duration = max(timestamps) - min(timestamps) if timestamps else 0

        # Click locations for rage click detection
        clicks = []
        for event in self.events:
            if event['event_type'] == 'mouse_down':
                clicks.append({
                    'timestamp': event['timestamp'],
                    'x': event.get('x'),
                    'y': event.get('y')
                })

        # Detect rage clicks (3+ clicks within 1 second in same area)
        rage_clicks = self._detect_rage_clicks(clicks)

        # Calculate pauses (gaps between events)
        pauses = []
        for i in range(1, len(self.events)):
            gap = self.events[i]['timestamp'] - self.events[i-1]['timestamp']
            pauses.append(gap)

        longest_pause = max(pauses) if pauses else 0
        avg_pause = sum(pauses) / len(pauses) if pauses else 0

        # Count total interactions (excluding mouse moves)
        interaction_events = [e for e in self.events if e['event_type'] != 'mouse_move']
        total_interactions = len(interaction_events)

        # Calculate rates (per minute)
        duration_minutes = duration / 60 if duration > 0 else 0
        clicks_per_minute = event_counts.get('mouse_down', 0) / duration_minutes if duration_minutes > 0 else 0
        actions_per_minute = total_interactions / duration_minutes if duration_minutes > 0 else 0
        keypresses_per_minute = event_counts.get('key_press', 0) / duration_minutes if duration_minutes > 0 else 0

        # Scroll analysis
        scroll_events = [e for e in self.events if e['event_type'] == 'scroll']
        total_scroll_distance = sum(abs(e.get('dy', 0)) for e in scroll_events)

        # Store statistics
        self.stats = {
            'session_duration_seconds': duration,
            'session_duration_formatted': str(timedelta(seconds=int(duration))),
            'total_events': len(self.events),
            'total_interactions': total_interactions,
            'total_mouse_moves': event_counts.get('mouse_move', 0),
            'total_clicks': event_counts.get('mouse_down', 0),
            'total_scrolls': event_counts.get('scroll', 0),
            'total_keypresses': event_counts.get('key_press', 0),
            'total_drags': event_counts.get('drag', 0),
            'clicks_per_minute': round(clicks_per_minute, 2),
            'actions_per_minute': round(actions_per_minute, 2),
            'keypresses_per_minute': round(keypresses_per_minute, 2),
            'rage_clicks_detected': len(rage_clicks),
            'longest_pause_seconds': round(longest_pause, 2),
            'average_pause_seconds': round(avg_pause, 3),
            'total_scroll_distance': total_scroll_distance,
        }

        return self.stats

    def _detect_rage_clicks(self, clicks, time_window=1.0, distance_threshold=50):
        """
        Detect rage clicks (multiple rapid clicks in same area).

        Args:
            clicks: List of click events with timestamp, x, y
            time_window: Time window in seconds to consider (default 1.0)
            distance_threshold: Maximum distance in pixels to consider same area

        Returns:
            List of rage click instances
        """
        rage_clicks = []

        for i in range(len(clicks) - 2):
            # Get window of clicks
            window_clicks = []
            for j in range(i, len(clicks)):
                if clicks[j]['timestamp'] - clicks[i]['timestamp'] <= time_window:
                    window_clicks.append(clicks[j])
                else:
                    break

            # Check if we have 3+ clicks in same area
            if len(window_clicks) >= 3:
                # Check if all clicks are in same area
                first_click = window_clicks[0]
                same_area = True

                for click in window_clicks[1:]:
                    if first_click['x'] is None or click['x'] is None:
                        same_area = False
                        break

                    distance = ((click['x'] - first_click['x'])**2 +
                              (click['y'] - first_click['y'])**2)**0.5

                    if distance > distance_threshold:
                        same_area = False
                        break

                if same_area:
                    rage_clicks.append({
                        'timestamp': first_click['timestamp'],
                        'x': first_click['x'],
                        'y': first_click['y'],
                        'click_count': len(window_clicks)
                    })

        return rage_clicks

    def calculate_intensity(self, bucket_size=5.0):
        """
        Calculate interaction intensity over time.

        Args:
            bucket_size: Time bucket size in seconds

        Returns:
            List of time buckets with interaction counts
        """
        print(f"Calculating interaction intensity (bucket size: {bucket_size}s)...")

        if not self.events:
            return []

        # Get time range
        timestamps = [e['timestamp'] for e in self.events]
        min_time = min(timestamps)
        max_time = max(timestamps)

        # Create buckets
        buckets = []
        current_time = min_time

        while current_time <= max_time:
            bucket_end = current_time + bucket_size

            # Count events in this bucket (excluding mouse moves)
            bucket_events = [
                e for e in self.events
                if current_time <= e['timestamp'] < bucket_end
                and e['event_type'] != 'mouse_move'
            ]

            # Count by type
            event_counts = defaultdict(int)
            for event in bucket_events:
                event_counts[event['event_type']] += 1

            buckets.append({
                'time_start': round(current_time, 2),
                'time_end': round(bucket_end, 2),
                'total_interactions': len(bucket_events),
                'clicks': event_counts.get('mouse_down', 0),
                'scrolls': event_counts.get('scroll', 0),
                'keypresses': event_counts.get('key_press', 0),
            })

            current_time = bucket_end

        return buckets

    def save_summary(self, output_file=None):
        """Save summary statistics to CSV file."""
        if output_file is None:
            output_file = self.events_file.parent / f"{self.events_file.stem}_summary.csv"
        else:
            output_file = Path(output_file)

        print(f"Saving summary to {output_file}...")

        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['metric', 'value'])

            for key, value in self.stats.items():
                writer.writerow([key, value])

        return output_file

    def save_intensity(self, output_file=None, bucket_size=5.0):
        """Save interaction intensity data to CSV file."""
        if output_file is None:
            output_file = self.events_file.parent / f"{self.events_file.stem}_intensity.csv"
        else:
            output_file = Path(output_file)

        buckets = self.calculate_intensity(bucket_size)

        print(f"Saving intensity data to {output_file}...")

        with open(output_file, 'w', newline='') as f:
            if buckets:
                writer = csv.DictWriter(f, fieldnames=buckets[0].keys())
                writer.writeheader()
                writer.writerows(buckets)

        return output_file

    def print_summary(self):
        """Print summary statistics to console."""
        if not self.stats:
            print("No statistics calculated")
            return

        print("\n" + "="*60)
        print("INTERACTION LOG SUMMARY")
        print("="*60)

        print(f"\nSession Duration: {self.stats['session_duration_formatted']}")
        print(f"Total Events: {self.stats['total_events']:,}")
        print(f"Total Interactions: {self.stats['total_interactions']:,}")

        print(f"\n--- Event Counts ---")
        print(f"Mouse Moves: {self.stats['total_mouse_moves']:,}")
        print(f"Clicks: {self.stats['total_clicks']:,}")
        print(f"Scrolls: {self.stats['total_scrolls']:,}")
        print(f"Keypresses: {self.stats['total_keypresses']:,}")
        print(f"Drags: {self.stats['total_drags']:,}")

        print(f"\n--- Rates (per minute) ---")
        print(f"Clicks/min: {self.stats['clicks_per_minute']:.2f}")
        print(f"Actions/min: {self.stats['actions_per_minute']:.2f}")
        print(f"Keypresses/min: {self.stats['keypresses_per_minute']:.2f}")

        print(f"\n--- Behavioral Patterns ---")
        print(f"Rage Clicks: {self.stats['rage_clicks_detected']}")
        print(f"Longest Pause: {self.stats['longest_pause_seconds']:.2f}s")
        print(f"Average Pause: {self.stats['average_pause_seconds']:.3f}s")
        print(f"Total Scroll Distance: {self.stats['total_scroll_distance']:,} pixels")

        print("\n" + "="*60 + "\n")


def main():
    """Main entry point for analyzer."""
    parser = argparse.ArgumentParser(
        description="Analyze InterLog event data and generate statistics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze events and save all outputs
  python analyzer.py session_events.csv

  # Custom output location
  python analyzer.py session_events.csv --output ./analysis/

  # Custom intensity bucket size (10 seconds)
  python analyzer.py session_events.csv --bucket-size 10
        """
    )

    parser.add_argument(
        'events_file',
        help='Path to events CSV file'
    )

    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output directory for analysis files (default: same as events file)'
    )

    parser.add_argument(
        '--bucket-size', '-b',
        type=float,
        default=5.0,
        help='Time bucket size in seconds for intensity analysis (default: 5.0)'
    )

    parser.add_argument(
        '--json',
        action='store_true',
        help='Also output summary as JSON'
    )

    args = parser.parse_args()

    # Create analyzer
    analyzer = InteractionAnalyzer(args.events_file)

    # Load and analyze
    analyzer.load_events()
    analyzer.calculate_statistics()

    # Print summary to console
    analyzer.print_summary()

    # Determine output directory
    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_file = output_dir / f"{Path(args.events_file).stem}_summary.csv"
        intensity_file = output_dir / f"{Path(args.events_file).stem}_intensity.csv"
    else:
        summary_file = None
        intensity_file = None

    # Save outputs
    summary_path = analyzer.save_summary(summary_file)
    intensity_path = analyzer.save_intensity(intensity_file, args.bucket_size)

    print(f"\nAnalysis complete!")
    print(f"Summary: {summary_path}")
    print(f"Intensity: {intensity_path}")

    # Optional JSON output
    if args.json:
        json_file = summary_path.parent / f"{summary_path.stem}.json"
        with open(json_file, 'w') as f:
            json.dump(analyzer.stats, f, indent=2)
        print(f"JSON: {json_file}")


if __name__ == '__main__':
    main()
