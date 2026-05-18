from __future__ import annotations

import http.client
import socket

from serbia_parser import keep_alive


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(port: int, path: str) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        return resp.status, body
    finally:
        conn.close()


def test_keep_alive_responds_on_root_and_health() -> None:
    port = _free_port()
    server = keep_alive.start(port=port)
    try:
        for path in ("/", "/health", "/healthz", "/ping"):
            status, body = _get(port, path)
            assert status == 200, f"{path} returned {status}"
            assert b"ok" in body
        status, _ = _get(port, "/does-not-exist")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
