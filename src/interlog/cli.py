"""Command-line interface for InterLog.

Exposes a single ``interlog`` command with subcommands:

    interlog record    Capture mouse/keyboard interactions to CSV.
    interlog analyze   Generate statistics from a recorded session.
    interlog doctor    Check the environment and input-capture permissions.
"""

import argparse
import json
from pathlib import Path

from interlog import __version__


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="interlog",
        description="InterLog - interaction logger for HCI research.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  interlog record                              Start a session in the current directory
  interlog record --privacy --name p01         Privacy mode, custom session name
  interlog record -o ./sessions                Write session files to ./sessions
  interlog record --screen --name p01          Record the screen + interactions together
  interlog analyze p01_events.csv              Generate statistics for a session
  interlog analyze p01_events.csv -b 10 --json Custom bucket size, also emit JSON
  interlog analyze p01 --no-text                Skip the typed-text reconstruction
  interlog view p01_events.csv                 Open the timeline viewer for a session
  interlog doctor --live                       Verify input capture works
""",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # record
    p_record = sub.add_parser(
        "record", help="Capture mouse/keyboard interactions to CSV."
    )
    p_record.add_argument(
        "-o", "--output", default="interlog-data",
        help="Data directory root (default: ./interlog-data). Each session is "
             "saved in its own subfolder named after --name or the start timestamp.",
    )
    p_record.add_argument(
        "-n", "--name", default=None,
        help="Session name (default: auto-generated timestamp).",
    )
    p_record.add_argument(
        "-p", "--privacy", action="store_true",
        help="Enable privacy mode (log key events without recording which keys).",
    )
    p_record.add_argument(
        "--screen", action="store_true",
        help="Also record the primary screen with ffmpeg (requires ffmpeg on PATH).",
    )
    p_record.add_argument(
        "--fps", type=int, default=15,
        help="Screen capture frame rate when using --screen (default: 15).",
    )
    p_record.add_argument(
        "--monitor", choices=["primary", "all"], default="primary",
        help="Which display to capture with --screen (default: primary).",
    )
    p_record.set_defaults(func=_cmd_record)

    # analyze
    p_analyze = sub.add_parser(
        "analyze", help="Generate statistics from a recorded session."
    )
    p_analyze.add_argument("events_file", help="Path to an events CSV, or a session folder containing events.csv.")
    p_analyze.add_argument(
        "-o", "--output", default=None,
        help="Output directory for analysis files (default: alongside the events file).",
    )
    p_analyze.add_argument(
        "-b", "--bucket-size", type=float, default=5.0,
        help="Time bucket size in seconds for intensity analysis (default: 5.0).",
    )
    p_analyze.add_argument(
        "--json", action="store_true", help="Also output summary as JSON."
    )
    p_analyze.add_argument(
        "--no-text", action="store_true",
        help="Skip typed-text reconstruction (it runs by default, and is always "
             "skipped automatically for privacy-mode sessions).",
    )
    p_analyze.set_defaults(func=_cmd_analyze)

    # view
    p_view = sub.add_parser(
        "view", help="Open an HTML viewer that syncs interactions with a recording."
    )
    p_view.add_argument("events_file", help="Path to an events CSV, or a session folder containing events.csv.")
    p_view.add_argument(
        "-o", "--output", default=None,
        help="Output path or directory for the viewer HTML (default: alongside the events file).",
    )
    p_view.add_argument(
        "-b", "--bucket-size", type=float, default=2.0,
        help="Time bucket size in seconds for the intensity timeline (default: 2.0).",
    )
    p_view.add_argument(
        "--no-open", action="store_true",
        help="Generate the HTML without opening a browser.",
    )
    p_view.set_defaults(func=_cmd_view)

    # doctor
    p_doctor = sub.add_parser(
        "doctor", help="Check the environment and input-capture permissions."
    )
    p_doctor.add_argument(
        "--live", action="store_true",
        help="Run a live input-capture test (press ESC to finish).",
    )
    p_doctor.set_defaults(func=_cmd_doctor)

    return parser


def _cmd_record(args):
    from interlog.recorder import InteractionLogger

    logger = InteractionLogger(
        output_dir=args.output,
        privacy_mode=args.privacy,
        session_name=args.name,
    )

    if args.screen:
        if args.fps < 1:
            print("Error: --fps must be at least 1.")
            return 1
        if not _attach_screen_recorder(logger, fps=args.fps, monitor=args.monitor):
            return 1

    logger.start()
    return 0


def _attach_screen_recorder(logger, fps, monitor="primary"):
    """Start ffmpeg screen capture and attach it to the logger. Returns success."""
    from interlog.screen import ScreenRecorder, ffmpeg_path

    if not ffmpeg_path():
        print("Error: ffmpeg not found on PATH, so --screen is unavailable.")
        print("Install ffmpeg (https://ffmpeg.org/download.html), then check with: interlog doctor")
        return False

    video_file = logger.session_dir / "recording.mp4"
    recorder = ScreenRecorder(video_file, fps=fps, monitor=monitor)

    print("Starting screen recorder (ffmpeg)...")
    try:
        # Start the video first and wait for real frames, so the input log
        # (started right after) aligns to a known point in the recording.
        first_frame = recorder.start_and_wait_until_live()
    except RuntimeError as e:
        print(f"Error: {e}")
        return False

    logger.video_file = video_file
    logger.video_first_frame_time = first_frame
    logger.capture_region = recorder.geometry
    logger.stop_callback = recorder.stop
    print(f"Screen recording to: {video_file}")
    return True


def _cmd_analyze(args):
    from interlog.analyzer import InteractionAnalyzer, base_prefix

    if args.bucket_size <= 0:
        print("Error: --bucket-size must be greater than 0.")
        return 1

    events_path = _resolve_events_path(args.events_file)
    if not events_path.exists():
        print(f"Error: events file not found: {events_path}")
        return 1

    analyzer = InteractionAnalyzer(events_path)
    analyzer.load_events()
    analyzer.calculate_statistics()
    analyzer.print_summary()

    # Resolve output paths
    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_file = output_dir / f"{base_prefix(events_path)}summary.csv"
        intensity_file = output_dir / f"{base_prefix(events_path)}intensity.csv"
    else:
        summary_file = None
        intensity_file = None

    summary_path = analyzer.save_summary(summary_file)
    intensity_path = analyzer.save_intensity(intensity_file, args.bucket_size)

    print("\nAnalysis complete!")
    print(f"Summary:   {summary_path}")
    print(f"Intensity: {intensity_path}")

    if args.json:
        json_file = summary_path.parent / f"{summary_path.stem}.json"
        with open(json_file, "w") as f:
            json.dump(analyzer.stats, f, indent=2)
        print(f"JSON:      {json_file}")

    if not args.no_text:
        _analyze_text(analyzer, events_path, summary_path.parent)

    return 0


def _analyze_text(analyzer, events_path, out_dir):
    """Reconstruct typed text and run local lexical analysis (default; privacy-gated)."""
    from interlog.analyzer import base_prefix
    from interlog.text_analysis import is_redacted, lexical_stats, reconstruct_text

    if is_redacted(analyzer.events):
        print("\n[text analysis skipped] this session was recorded in privacy mode, "
              "so key identities were not logged.")
        return

    text = reconstruct_text(analyzer.events)
    if not text.strip():
        return  # nothing typed - don't clutter the folder with empty files

    prefix = base_prefix(events_path)
    transcript_path = out_dir / f"{prefix}transcript.txt"
    transcript_path.write_text(text, encoding="utf-8")

    stats = lexical_stats(text)
    stats_path = out_dir / f"{prefix}text.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print("\n--- Text (reconstructed, approximate) ---")
    if stats["word_count"] == 0:
        print("(no typed text captured)")
    else:
        print(f"Words: {stats['word_count']:,} | Unique: {stats['unique_words']:,} "
              f"| Chars: {stats['char_count']:,} | Avg word: {stats['avg_word_length']}")
        if stats["top_keywords"]:
            kws = ", ".join(f"{w} ({c})" for w, c in stats["top_keywords"][:10])
            print(f"Top keywords: {kws}")
    print(f"Transcript: {transcript_path}")
    print(f"Text stats: {stats_path}")


def _resolve_events_path(arg):
    """Accept either an events CSV or a session folder (which contains events.csv)."""
    path = Path(arg)
    if path.is_dir():
        return path / "events.csv"
    return path


def _cmd_view(args):
    from interlog.viewer import build_viewer

    if args.bucket_size <= 0:
        print("Error: --bucket-size must be greater than 0.")
        return 1

    events_path = _resolve_events_path(args.events_file)
    if not events_path.exists():
        print(f"Error: events file not found: {events_path}")
        return 1

    try:
        output = build_viewer(
            events_path,
            output=args.output,
            bucket_size=args.bucket_size,
            open_browser=not args.no_open,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Viewer written to: {output}")
    if args.no_open:
        print("Open it in a browser, then load your screen recording to sync.")
    else:
        print("Opening in your browser - load your screen recording to sync.")
    return 0


def _cmd_doctor(args):
    from interlog.doctor import run_doctor

    return run_doctor(live=args.live)


def main(argv=None):
    """Entry point for the ``interlog`` console script."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        from interlog.branding import print_banner

        print_banner()
        print(f"\n  v{__version__} - local, private, MIT-licensed\n")
        print("  Commands:")
        print("    record    Capture mouse + keyboard   (add --screen to record video too)")
        print("    view      Open the synced timeline viewer")
        print("    analyze   Compute session statistics")
        print("    doctor    Check your environment")
        print("\n  Run 'interlog <command> --help' for details.\n")
        return 0

    return args.func(args)
