"""Screen recording via ffmpeg.

Wraps an ffmpeg subprocess that captures the screen. To survive an unclean exit
(a hard kill never finalizes an MP4's moov atom -> unplayable file), capture goes
to a Matroska (.mkv) container, which tolerates truncation, and is remuxed to
H.264 MP4 (playable by the HTML viewer) on a clean stop. If the remux can't run,
the recoverable .mkv is kept.

Platform support
----------------
- **Windows** — gdigrab (built into ffmpeg)
- **macOS** — avfoundation (built into ffmpeg)
- **Linux X11** — x11grab (built into ffmpeg)
- **Linux Wayland** — xdg-desktop-portal + PipeWire via jeepney (installed
  automatically on Linux). Shows a native screen-picker dialog. Falls back to
  XWayland (x11grab) if jeepney is absent and ``$DISPLAY`` is set.

ffmpeg is an external runtime dependency — only ``interlog record --screen`` needs it.
"""

import collections
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from interlog.security import lock_down


def ffmpeg_path():
    """Return the path to the ffmpeg executable, or None if not on PATH."""
    return shutil.which("ffmpeg")


def _macos_main_display():
    """Return (logical_w, logical_h, dpi_scale) for the main display, or None.

    pynput reports mouse coordinates in logical points, while avfoundation
    captures in physical pixels, so dpi_scale = pixels / points (2.0 on a
    Retina display). Read straight from CoreGraphics via ctypes — no extra deps.
    """
    import ctypes

    try:
        cg = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
    except OSError:
        return None

    cg.CGMainDisplayID.restype = ctypes.c_uint32
    cg.CGDisplayCopyDisplayMode.restype = ctypes.c_void_p
    cg.CGDisplayCopyDisplayMode.argtypes = [ctypes.c_uint32]
    for fn in ("CGDisplayModeGetWidth", "CGDisplayModeGetHeight",
               "CGDisplayModeGetPixelWidth"):
        getattr(cg, fn).restype = ctypes.c_size_t
        getattr(cg, fn).argtypes = [ctypes.c_void_p]
    cg.CGDisplayModeRelease.argtypes = [ctypes.c_void_p]

    mode = cg.CGDisplayCopyDisplayMode(cg.CGMainDisplayID())
    if not mode:
        return None
    try:
        w_pts = cg.CGDisplayModeGetWidth(mode)
        h_pts = cg.CGDisplayModeGetHeight(mode)
        w_px = cg.CGDisplayModeGetPixelWidth(mode)
    finally:
        cg.CGDisplayModeRelease(mode)

    if not w_pts:
        return None
    return w_pts, h_pts, round(w_px / w_pts, 4)


def _capture_geometry_macos():
    """Primary-display geometry on macOS.

    width/height are in logical points (the coordinate space pynput reports
    events in); dpi_scale is the device-pixel ratio, so physical capture pixels
    = points * dpi_scale.
    """
    cg = _macos_main_display()
    if cg is not None:
        w_pts, h_pts, scale = cg
        return {"x": 0, "y": 0, "width": w_pts, "height": h_pts, "dpi_scale": scale}

    # Fallback: Finder bounds (logical points); device-pixel ratio unknown.
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "Finder" to get bounds of window of desktop'],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            parts = [int(p.strip()) for p in result.stdout.strip().split(",")]
            if len(parts) == 4:
                # osascript returns {left, top, right, bottom}
                return {"x": 0, "y": 0, "width": parts[2], "height": parts[3],
                        "dpi_scale": 1.0}
    except Exception:
        pass
    return None


def _capture_geometry_linux():
    """Get primary screen bounds on Linux X11 using xrandr."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return None  # geometry not reliably detectable without portal interaction
    display = os.environ.get("DISPLAY", "")
    if not display:
        return None
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        # Prefer the monitor tagged as "primary"
        m = re.search(r"connected primary (\d+)x(\d+)\+(\d+)\+(\d+)", result.stdout)
        if not m:
            m = re.search(r"connected (\d+)x(\d+)\+(\d+)\+(\d+)", result.stdout)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            x, y = int(m.group(3)), int(m.group(4))
            # On X11 the pointer and x11grab share one pixel space, so the
            # device-pixel ratio is 1.0. (Fractional desktop scaling is not
            # reliably detectable from xrandr and is not handled here.)
            return {"x": x, "y": y, "width": w, "height": h, "dpi_scale": 1.0}
    except Exception:
        pass
    return None


def capture_geometry(monitor="primary"):
    """Return the capture region as {x, y, width, height, dpi_scale}.

    ``monitor`` is "primary" (the primary display) or "all" (the full virtual
    desktop on Windows). Returns None where geometry can't be determined — the
    capture falls back to the OS default and coordinates stay in global space.

    The returned dict carries a ``dpi_scale`` (device-pixel ratio of the
    capture). width/height are in the same coordinate space the pointer events
    use, so downstream code can relate the two without guessing.
    """
    if sys.platform == "win32":
        import ctypes

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
        # The process is per-monitor DPI-aware (above), so metrics and pointer
        # events are both in physical pixels; report the system scale factor for
        # reference (GetDpiForSystem is Windows 10+; default to 1.0 if absent).
        try:
            dpi_scale = round(u.GetDpiForSystem() / 96.0, 4)
        except Exception:
            dpi_scale = 1.0
        return {"x": x, "y": y, "width": w, "height": h, "dpi_scale": dpi_scale}

    elif sys.platform == "darwin":
        return _capture_geometry_macos()

    else:
        return _capture_geometry_linux()


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
        self._portal_conn = None     # jeepney connection, kept alive during recording
        self._portal_session = None  # xdg-desktop-portal session handle

    def _negotiate_portal(self):
        """Negotiate an xdg-desktop-portal ScreenCast session.

        Shows a native screen-picker dialog (one user interaction required).
        Stores the D-Bus connection on self._portal_conn so the portal session
        stays alive for the duration of the recording.

        Returns the PipeWire node ID (int) for the chosen stream.
        Requires the ``jeepney`` package.
        """
        try:
            from jeepney import DBusAddress, HeaderFields, MessageType, new_method_call
            from jeepney.io.blocking import open_dbus_connection
        except ImportError:
            raise ImportError(
                "Wayland screen capture requires jeepney.\n"
                "Install with: pip install jeepney"
            )

        conn = open_dbus_connection("SESSION")
        self._portal_conn = conn  # keep alive until stop()
        tok = f"il{os.getpid()}"

        portal = DBusAddress(
            "/org/freedesktop/portal/desktop",
            bus_name="org.freedesktop.portal.Desktop",
            interface="org.freedesktop.portal.ScreenCast",
        )

        def call(method, sig, *body):
            msg = new_method_call(portal, method, sig, body)
            return conn.send_and_get_reply(msg).body

        def wait_response(request_path, timeout=120):
            """Receive D-Bus messages until we get the Response signal on request_path."""
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        "Portal timed out — did you dismiss the screen-picker dialog?"
                    )
                try:
                    msg = conn.receive(timeout=min(2.0, remaining))
                except Exception:
                    continue
                h = msg.header
                if (h.message_type == MessageType.signal
                        and h.fields.get(HeaderFields.path) == request_path
                        and h.fields.get(HeaderFields.interface)
                            == "org.freedesktop.portal.Request"
                        and h.fields.get(HeaderFields.member) == "Response"):
                    return msg.body  # (response_code: int, results: dict)

        # Step 1: CreateSession
        (req_path,) = call("CreateSession", "a{sv}", {
            "handle_token": ("s", tok + "a"),
            "session_handle_token": ("s", tok + "s"),
        })
        code, results = wait_response(req_path)
        if code != 0:
            raise RuntimeError(f"Portal CreateSession failed (code {code})")
        session_handle = results["session_handle"][1]
        self._portal_session = session_handle

        # Step 2: SelectSources — configure what the picker presents
        (req_path,) = call("SelectSources", "oa{sv}", session_handle, {
            "handle_token": ("s", tok + "b"),
            "types": ("u", 1),         # MONITOR = 1
            "multiple": ("b", False),
            "cursor_mode": ("u", 2),   # EMBEDDED = 2
        })
        code, _ = wait_response(req_path)
        if code != 0:
            raise RuntimeError(f"Portal SelectSources failed (code {code})")

        # Step 3: Start — shows the native picker dialog to the user
        (req_path,) = call("Start", "osa{sv}", session_handle, "", {
            "handle_token": ("s", tok + "c"),
        })
        code, results = wait_response(req_path, timeout=300)  # give user time to pick
        if code != 0:
            raise RuntimeError(
                "Screen selection cancelled — no screen was selected in the dialog."
            )

        streams = results.get("streams", ("a(ua{sv})", []))[1]
        if not streams:
            raise RuntimeError("Portal returned no streams — try selecting a screen again.")
        return streams[0][0]  # PipeWire node ID of the first (chosen) stream

    def _close_portal_session(self):
        """Close the xdg-desktop-portal session and release the D-Bus connection."""
        if not self._portal_conn or not self._portal_session:
            return
        try:
            from jeepney import DBusAddress, new_method_call
            session_addr = DBusAddress(
                self._portal_session,
                bus_name="org.freedesktop.portal.Desktop",
                interface="org.freedesktop.portal.Session",
            )
            msg = new_method_call(session_addr, "Close", "", ())
            self._portal_conn.send_and_get_reply(msg)
        except Exception:
            pass
        finally:
            self._portal_conn = None
            self._portal_session = None

    def _linux_grab_args(self):
        """Build ffmpeg input arguments for Linux, handling X11 and Wayland."""
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        display = os.environ.get("DISPLAY", "")

        if session_type == "wayland":
            try:
                node_id = self._negotiate_portal()
                return ["-f", "pipewire", "-i", str(node_id)]
            except ImportError:
                # jeepney absent — try XWayland as a degraded fallback
                if display:
                    import warnings
                    warnings.warn(
                        "jeepney not installed; falling back to XWayland capture — "
                        "native Wayland windows may not be captured. "
                        "For full Wayland support: pip install jeepney",
                        stacklevel=4,
                    )
                    return ["-f", "x11grab", "-i", display]
                raise RuntimeError(
                    "Wayland screen capture requires jeepney.\n"
                    "Install with: pip install jeepney\n"
                    "(or run under an X11 session with $DISPLAY set)"
                )
        else:
            if not display:
                raise RuntimeError(
                    "No DISPLAY environment variable set. "
                    "Ensure you are running in an X11 session."
                )
            return ["-f", "x11grab", "-i", display]

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
            grab = self._linux_grab_args()

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
                # The recording holds whatever is on screen; keep it owner-only
                # for the whole capture, not just after the final remux.
                lock_down(self.capture_file)
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
        self._close_portal_session()

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
                lock_down(self.output_file)
                try:
                    self.capture_file.unlink()
                except OSError:
                    pass
            else:
                import warnings
                warnings.warn(
                    f"could not remux to MP4; recording kept as {self.capture_file.name}",
                    stacklevel=2,
                )
        except Exception as e:
            import warnings
            warnings.warn(
                f"remux failed ({e}); recording kept as {self.capture_file.name}",
                stacklevel=2,
            )
