"""Screen recording via ffmpeg.

Wraps an ffmpeg subprocess that captures the screen. To survive an unclean exit
(a hard kill never finalizes an MP4's moov atom -> unplayable file), capture goes
to a Matroska (.mkv) container, which tolerates truncation, and is remuxed to
H.264 MP4 (playable by the HTML viewer) on a clean stop. If the remux can't run,
the recoverable .mkv is kept.

ffmpeg is an optional, external dependency - only `interlog record --screen`
needs it.
"""

import collections
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def ffmpeg_path():
    """Return the path to the ffmpeg executable, or None if not on PATH."""
    return shutil.which("ffmpeg")


def capture_geometry(monitor="primary"):
    """Return the capture region as {x, y, width, height, dpi_scale}.

    ``monitor`` is "primary" (the primary display) or "all" (the full virtual
    desktop). Returns None where we can't determine geometry (non-Windows): the
    capture falls back to the OS default and coordinates stay in global space.
    """
    if sys.platform != "win32":
        return None

    import ctypes

    # Become DPI-aware so metrics are physical pixels matching gdigrab's capture.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    u = ctypes.windll.user32
    if monitor == "all":
        # SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77, SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
        x, y = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        w, h = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
    else:
        x, y = 0, 0  # the primary monitor is the origin of the virtual desktop
        w, h = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    return {"x": x, "y": y, "width": w, "height": h, "dpi_scale": 1.0}


class ScreenRecorder:
    """Records the screen to an MP4 (via a crash-resilient MKV) using ffmpeg."""

    def __init__(self, output_file, fps=15, monitor="primary"):
        self.output_file = Path(output_file)              # final .mp4
        self.capture_file = self.output_file.with_suffix(".mkv")  # during capture
        self.fps = fps
        self.monitor = monitor
        self.geometry = capture_geometry(monitor)
        self.proc = None
        self._live = threading.Event()
        self._stderr_tail = collections.deque(maxlen=40)
        self._readers = []

    def _command(self):
        ff = ffmpeg_path()
        if not ff:
            raise RuntimeError(
                "ffmpeg not found on PATH. Install it (https://ffmpeg.org/download.html) "
                "or record without --screen."
            )

        pre = [ff, "-y", "-progress", "pipe:1", "-nostats",
               "-loglevel", "error", "-framerate", str(self.fps)]
        post = [
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(self.capture_file),
        ]

        if sys.platform == "win32":
            grab = ["-f", "gdigrab"]
            g = self.geometry
            if g:
                grab += ["-offset_x", str(g["x"]), "-offset_y", str(g["y"]),
                         "-video_size", f"{g['width']}x{g['height']}"]
            grab += ["-i", "desktop"]
        elif sys.platform == "darwin":
            grab = ["-f", "avfoundation", "-i", "Capture screen 0:none"]
        else:
            import os
            display = os.environ.get("DISPLAY", ":0.0")
            grab = ["-f", "x11grab", "-i", display]

        return pre + grab + post

    def start_and_wait_until_live(self, timeout=15.0):
        """Start ffmpeg and block until the first frame is captured.

        Returns the monotonic time of the first frame, used as the video's t=0
        for syncing the interaction log.
        """
        cmd = self._command()
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self._spawn_reader(self.proc.stdout, self._on_stdout)
        self._spawn_reader(self.proc.stderr, self._on_stderr)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._live.is_set():
                return time.monotonic()
            if self.proc.poll() is not None:
                raise RuntimeError(self._error_message())
            time.sleep(0.05)

        self.stop()
        raise RuntimeError(
            f"ffmpeg did not start capturing within {timeout:.0f}s.\n{self._error_message()}"
        )

    def _spawn_reader(self, stream, handler):
        t = threading.Thread(target=self._read_stream, args=(stream, handler), daemon=True)
        t.start()
        self._readers.append(t)

    def _read_stream(self, stream, handler):
        for line in stream:
            handler(line.rstrip("\r\n"))

    def _on_stdout(self, line):
        # Progress lines look like "frame=12"; the first frame means capture is live.
        if line.startswith("frame="):
            try:
                if int(line.split("=", 1)[1].strip()) >= 1:
                    self._live.set()
            except ValueError:
                pass

    def _on_stderr(self, line):
        if line:
            self._stderr_tail.append(line)

    def _error_message(self):
        tail = "\n".join(self._stderr_tail)
        return f"ffmpeg failed.\n{tail}" if tail else "ffmpeg exited unexpectedly."

    def stop(self, timeout=10.0):
        """Stop ffmpeg gracefully, then remux the .mkv to a playable .mp4."""
        if self.proc and self.proc.poll() is None:
            try:
                # 'q' tells ffmpeg to finish encoding and write the file trailer.
                self.proc.stdin.write("q")
                self.proc.stdin.flush()
            except Exception:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._remux()

    def _remux(self):
        """Losslessly remux the captured .mkv into an MP4 the viewer can play."""
        if not self.capture_file.exists():
            return
        ff = ffmpeg_path()
        if not ff:
            return
        try:
            result = subprocess.run(
                [ff, "-y", "-i", str(self.capture_file),
                 "-c", "copy", "-movflags", "+faststart", str(self.output_file)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=120,
            )
            if result.returncode == 0 and self.output_file.exists():
                try:
                    self.capture_file.unlink()
                except OSError:
                    pass
            else:
                import warnings
                warnings.warn(f"could not remux to MP4; recording kept as {self.capture_file.name}")
        except Exception as e:
            import warnings
            warnings.warn(f"remux failed ({e}); recording kept as {self.capture_file.name}")
