"""Tests for interlog.serve: Range parsing and the HTTP file server."""

import http.client
import threading

import pytest

from interlog.serve import _parse_range, serve_viewer


def test_parse_range_full():
    assert _parse_range("bytes=0-99", 200) == (0, 99)


def test_parse_range_suffix():
    assert _parse_range("bytes=-100", 200) == (100, 199)


def test_parse_range_open_end():
    assert _parse_range("bytes=50-", 200) == (50, 199)


def test_parse_range_unsatisfiable():
    with pytest.raises(ValueError, match="unsatisfiable"):
        _parse_range("bytes=200-300", 100)


def test_parse_range_bad_prefix():
    with pytest.raises(ValueError, match="bytes range"):
        _parse_range("chunks=0-10", 100)


def test_parse_range_suffix_longer_than_file_serves_whole():
    # bytes=-500 on a 10-byte file => the whole file, not 416.
    assert _parse_range("bytes=-500", 10) == (0, 9)


def test_serve_viewer_starts_and_stops(tmp_path):
    html = tmp_path / "viewer.html"
    html.write_text("<html></html>")
    httpd, url = serve_viewer(tmp_path, "viewer.html")
    assert url.startswith("http://127.0.0.1:")
    assert "viewer.html" in url
    httpd.server_close()


def _serve(tmp_path, body=b"0123456789"):
    """Start a real server in a thread; return (conn, httpd) and the file name."""
    (tmp_path / "viewer.html").write_text("<html></html>")
    (tmp_path / "rec.bin").write_bytes(body)
    httpd, url = serve_viewer(tmp_path, "viewer.html")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address
    return http.client.HTTPConnection(host, port), httpd


def test_serve_full_get_returns_200(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/rec.bin")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.read() == b"0123456789"
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()


def test_serve_range_returns_206(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/rec.bin", headers={"Range": "bytes=2-5"})
        resp = conn.getresponse()
        assert resp.status == 206
        assert resp.getheader("Content-Range") == "bytes 2-5/10"
        assert resp.getheader("Content-Length") == "4"
        assert resp.read() == b"2345"
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()


def test_serve_unsatisfiable_range_returns_416(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/rec.bin", headers={"Range": "bytes=100-200"})
        assert conn.getresponse().status == 416
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()


def test_serve_missing_file_with_range_returns_404(tmp_path):
    conn, httpd = _serve(tmp_path)
    try:
        conn.request("GET", "/nope.bin", headers={"Range": "bytes=0-1"})
        assert conn.getresponse().status == 404
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()
