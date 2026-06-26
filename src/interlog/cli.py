"""Command-line interface for InterLog.

Exposes a single ``interlog`` command with subcommands:

    interlog record    Capture mouse/keyboard interactions to CSV.
    interlog analyze   Generate statistics from a recorded session.
    interlog view      Open the synced HTML timeline viewer.
    interlog list      List all recorded sessions.
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
  interlog list                                List all sessions in ./interlog-data/
  interlog list -o ./sessions                  List sessions from a custom directory
  interlog analyze p01                         Generate statistics for a session
  interlog analyze p01 -b 10 --json            Custom bucket size, also emit JSON
  interlog view p01                            Open the timeline viewer for a session
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

    # heatmap
    p_heatmap = sub.add_parser(
        "heatmap", help="Generate a mouse movement and click heatmap PNG."
    )
    p_heatmap.add_argument(
        "session", help="Session folder or events CSV."
    )
    p_heatmap.add_argument(
        "-o", "--output", default=None,
        help="Output PNG path (default: <session>/heatmap.png).",
    )
    p_heatmap.add_argument(
        "--sigma", type=float, default=25,
        help="Gaussian blur radius in pixels (default: 25).",
    )
    p_heatmap.add_argument(
        "--no-open", action="store_true",
        help="Save the PNG without opening it.",
    )
    p_heatmap.set_defaults(func=_cmd_heatmap)

    # list
    p_list = sub.add_parser(
        "list", help="List all recorded sessions."
    )
    p_list.add_argument(
        "-o", "--output", default="interlog-data", metavar="DIR",
        help="Data directory to list sessions from (default: ./interlog-data).",
    )
    p_list.set_defaults(func=_cmd_list)

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
        "--serve", action="store_true",
        help="Serve the session folder over HTTP so the recording loads automatically "
             "(recommended when the session has a --screen recording). Blocks until Ctrl+C.",
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


def _cmd_heatmap(args):
    import sys
    from rich.console import Console
    from interlog.heatmap import build_heatmap

    console = Console(highlight=False)
    session_path = Path(args.session)
    if not session_path.exists():
        console.print(f"[red]Error:[/red] not found: {session_path}")
        return 1

    with console.status("[cyan]Building heatmap…[/cyan]", spinner="dots"):
        try:
            output = build_heatmap(
                session_path,
                output=args.output,
                sigma=args.sigma,
            )
        except ImportError:
            console.print("[red]Error:[/red] heatmap requires optional dependencies.")
            console.print("  [dim]Install with: pip install 'interlog[heatmap]'[/dim]")
            return 1
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            return 1

    console.print(f"  [green]✓[/green]  Heatmap → [white]{output}[/white]")

    if not args.no_open:
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(output)])
            elif sys.platform == "win32":
                import os
                os.startfile(str(output))
            else:
                subprocess.Popen(["xdg-open", str(output)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    return 0


def _cmd_list(args):
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from datetime import timedelta

    console = Console(highlight=False)
    data_dir = Path(args.output)

    console.print()
    console.rule(
        f"[bold]Sessions[/bold]  [dim]{data_dir}/[/dim]",
        style="cyan dim",
    )

    if not data_dir.exists():
        console.print()
        console.print(f"  [yellow]No data directory found:[/yellow] {data_dir}")
        console.print("  [dim]Run 'interlog record' to create your first session.[/dim]")
        console.print()
        return 0

    sessions = []
    for session_dir in sorted(data_dir.iterdir(), reverse=True):
        if not session_dir.is_dir():
            continue
        meta_file = session_dir / "metadata.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        sessions.append({
            "name": session_dir.name,
            "date": (meta.get("start_time") or "")[:10],
            "duration": meta.get("duration_seconds") or 0,
            "events": meta.get("total_events") or 0,
            "privacy": meta.get("privacy_mode", False),
            "has_video": (session_dir / "recording.mp4").exists(),
            "has_summary": (session_dir / "summary.csv").exists(),
        })

    if not sessions:
        console.print()
        console.print(f"  [yellow]No sessions found in[/yellow] {data_dir}")
        console.print("  [dim]Run 'interlog record' to create your first session.[/dim]")
        console.print()
        return 0

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        pad_edge=True,
        show_edge=False,
    )
    table.add_column("Session", min_width=20, style="white")
    table.add_column("Date", min_width=10, style="dim")
    table.add_column("Duration", min_width=8, justify="right")
    table.add_column("Events", min_width=7, justify="right", style="cyan")
    table.add_column("Screen", min_width=6, justify="center")
    table.add_column("Analyzed", min_width=8, justify="center")
    table.add_column("Privacy", min_width=7, justify="center")

    for s in sessions:
        dur = str(timedelta(seconds=int(s["duration"])))
        table.add_row(
            s["name"],
            s["date"],
            dur,
            f"{s['events']:,}",
            "[green]✓[/green]" if s["has_video"] else "[dim]–[/dim]",
            "[green]✓[/green]" if s["has_summary"] else "[dim]–[/dim]",
            "[yellow]on[/yellow]" if s["privacy"] else "[dim]–[/dim]",
        )

    console.print()
    console.print(table)
    n = len(sessions)
    console.print(f"  [dim]{n} session{'s' if n != 1 else ''} · "
                  f"'interlog analyze <session>' to compute statistics[/dim]")
    console.print()
    return 0


def _cmd_analyze(args):
    from rich.console import Console
    from interlog.analyzer import InteractionAnalyzer, base_prefix

    console = Console(highlight=False)

    if args.bucket_size <= 0:
        console.print("[red]Error:[/red] --bucket-size must be greater than 0.")
        return 1

    events_path = _resolve_events_path(args.events_file)
    if not events_path.exists():
        console.print(f"[red]Error:[/red] events file not found: {events_path}")
        return 1

    analyzer = InteractionAnalyzer(events_path)

    with console.status("[cyan]Analyzing session…[/cyan]", spinner="dots"):
        analyzer.load_events()
        analyzer.calculate_statistics()

    if not analyzer.events:
        console.print("[yellow]No events found in file.[/yellow]")
        return 1

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

    with console.status("[dim]Writing output files…[/dim]", spinner="dots"):
        summary_path = analyzer.save_summary(summary_file)
        intensity_path = analyzer.save_intensity(intensity_file, args.bucket_size)

        json_path = None
        if args.json:
            json_path = summary_path.parent / f"{summary_path.stem}.json"
            with open(json_path, "w") as f:
                json.dump(analyzer.stats, f, indent=2)

    console.rule("[dim]Output files[/dim]", style="dim")
    console.print(f"  [dim]Summary    [/dim]{summary_path}")
    console.print(f"  [dim]Intensity  [/dim]{intensity_path}")
    if json_path:
        console.print(f"  [dim]JSON       [/dim]{json_path}")

    if not args.no_text:
        _analyze_text(analyzer, events_path, summary_path.parent, console)
    else:
        console.print()

    return 0


def _analyze_text(analyzer, events_path, out_dir, console=None):
    """Reconstruct typed text and run local lexical analysis (default; privacy-gated)."""
    from interlog.analyzer import base_prefix
    from interlog.text_analysis import is_redacted, lexical_stats, reconstruct_text

    if console is None:
        from rich.console import Console
        console = Console(highlight=False)

    if is_redacted(analyzer.events):
        console.print()
        console.print("  [dim]Text analysis skipped — privacy mode session.[/dim]")
        console.print()
        return

    text = reconstruct_text(analyzer.events)
    if not text.strip():
        console.print()
        return

    prefix = base_prefix(events_path)
    transcript_path = out_dir / f"{prefix}transcript.txt"
    transcript_path.write_text(text, encoding="utf-8")

    stats = lexical_stats(text)
    stats_path = out_dir / f"{prefix}text.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    console.print(f"  [dim]Transcript [/dim]{transcript_path}")
    if stats["word_count"] > 0 and stats["top_keywords"]:
        kws = "  ".join(f"{w} ({c})" for w, c in stats["top_keywords"][:8])
        console.print(f"  [dim]Keywords   [/dim][cyan]{kws}[/cyan]")
    console.print()


def _resolve_events_path(arg):
    """Accept either an events CSV or a session folder (which contains events.csv)."""
    path = Path(arg)
    if path.is_dir():
        return path / "events.csv"
    return path


def _cmd_view(args):
    import webbrowser
    from rich.console import Console
    from interlog.viewer import build_viewer

    console = Console(highlight=False)

    if args.bucket_size <= 0:
        console.print("[red]Error:[/red] --bucket-size must be greater than 0.")
        return 1

    events_path = _resolve_events_path(args.events_file)
    if not events_path.exists():
        console.print(f"[red]Error:[/red] events file not found: {events_path}")
        return 1

    session_dir = events_path.parent
    video_file = session_dir / "recording.mp4"

    if args.serve:
        from interlog.serve import serve_viewer

        video_src = "recording.mp4" if video_file.exists() else None

        with console.status("[cyan]Building viewer…[/cyan]", spinner="dots"):
            try:
                output = build_viewer(
                    events_path,
                    output=args.output,
                    bucket_size=args.bucket_size,
                    open_browser=False,
                    video_src=video_src,
                )
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                return 1

        httpd, url = serve_viewer(output.parent, output.name)

        console.print()
        console.rule("[bold cyan]InterLog Viewer[/bold cyan]", style="cyan dim")
        console.print(f"\n  [bold white]{url}[/bold white]\n")
        if video_src:
            console.print(f"  [green]✓[/green]  Recording auto-loaded — seeking works immediately")
        else:
            console.print(f"  [yellow]![/yellow]  No recording found — load it manually in the browser")
        console.print(f"\n  [dim]Press Ctrl+C to stop.[/dim]\n")

        if not args.no_open:
            webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.shutdown()
            console.print("\n  [dim]Server stopped.[/dim]\n")

        return 0

    # Non-serve: write HTML and open directly
    with console.status("[cyan]Building viewer…[/cyan]", spinner="dots"):
        try:
            output = build_viewer(
                events_path,
                output=args.output,
                bucket_size=args.bucket_size,
                open_browser=not args.no_open,
            )
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            return 1

    console.print()
    console.rule("[bold cyan]InterLog Viewer[/bold cyan]", style="cyan dim")
    console.print(f"\n  [bold white]{output}[/bold white]\n")
    if video_file.exists():
        console.print(f"  [yellow]![/yellow]  Recording found — re-run with [bold]--serve[/bold] to auto-load it")
    else:
        console.print(f"  [dim]Load your screen recording via the file picker in the browser.[/dim]")
    console.print()
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
        from rich.console import Console
        from rich.table import Table
        from rich import box

        print_banner()

        console = Console(highlight=False)
        console.print(f"\n  [dim]v{__version__} · local, private, MIT-licensed[/dim]\n")

        table = Table(box=None, show_header=False, pad_edge=False,
                      padding=(0, 2, 0, 2), show_edge=False)
        table.add_column("", style="bold cyan", min_width=10)
        table.add_column("", style="white")
        table.add_row("record", "Capture mouse + keyboard  [dim](add --screen for video)[/dim]")
        table.add_row("list", "List all recorded sessions")
        table.add_row("analyze", "Compute session statistics + activity sparkline")
        table.add_row("heatmap", "Generate a mouse movement and click heatmap PNG")
        table.add_row("view", "Open the synced timeline viewer  [dim](add --serve for auto video loading)[/dim]")
        table.add_row("doctor", "Check your environment")
        console.print(table)
        console.print(f"\n  [dim]Run 'interlog <command> --help' for details.[/dim]\n")
        return 0

    return args.func(args)
