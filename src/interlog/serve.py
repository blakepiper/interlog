"""Local HTTP server for InterLog's synced viewer.

Serves the session folder over HTTP with Range-request support so the
browser can seek the recording without downloading the entire file first.
Python's built-in SimpleHTTPRequestHandler doesn't handle Range headers,
so we subclass it with minimal range logic.
"""

import functools
import http.server
import os
from pathlib import Path


def _parse_range(header, total):
    """Parse a 'bytes=X-Y' Range header into (start, end) inclusive.

    Handles both 'bytes=0-1023' and suffix form 'bytes=-512'.
    Raises ValueError on any invalid or unsatisfiable range.
    """
    if not header.startswith("bytes="):
        raise ValueError("not a bytes range")
    spec = header[6:]
    if spec.startswith("-"):
        n = int(spec)           # negative → suffix range
        start, end = total + n, total - 1
    else:
        lo, _, hi = spec.partition("-")
        start = int(lo)
        end = int(hi) if hi else total - 1
    if not (0 <= start <= end < total):
        raise ValueError(f"unsatisfiable range {start}-{end}/{total}")
    return start, end


class _RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with HTTP 206 Partial Content support."""

    def do_GET(self):
        if "Range" in self.headers:
            self._range_get()
        else:
            super().do_GET()

    def _range_get(self):
        path = self.translate_path(self.path)
        try:
            f = open(path, "rb")  # noqa: SIM115 — must open before the with to handle 404 separately
        except OSError:
            self.send_error(404, "File not found")
            return

        with f:
            stat = os.fstat(f.fileno())
            total = stat.st_size
            try:
                start, end = _parse_range(self.headers.get("Range", ""), total)
            except ValueError:
                self.send_error(416, "Range Not Satisfiable")
                return

            length = end - start + 1
            f.seek(start)

            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()

            remaining = length
            while remaining > 0:
                chunk = f.read(min(remaining, 64 * 1024))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def log_message(self, format, *args):
        pass  # keep terminal output clean during serve


def serve_viewer(session_dir, viewer_name, host="127.0.0.1", port=0):
    """Start a threaded HTTP server rooted at session_dir.

    Args:
        session_dir: Directory to serve (the session folder).
        viewer_name: Filename of the viewer HTML within that directory.
        host: Bind address (default: loopback only).
        port: Port number; 0 lets the OS pick an available one.

    Returns:
        (httpd, url) — the running ThreadingHTTPServer and the viewer URL.
    """
    handler = functools.partial(
        _RangeHTTPRequestHandler, directory=str(Path(session_dir).resolve())
    )
    httpd = http.server.ThreadingHTTPServer((host, port), handler)
    actual_port = httpd.server_address[1]
    url = f"http://{host}:{actual_port}/{viewer_name}"
    return httpd, url
