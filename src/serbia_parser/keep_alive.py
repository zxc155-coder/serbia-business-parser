"""Tiny HTTP server that exists only so Render keeps the worker alive.

Render's free-tier Web Service idles a process when no HTTP request hits it
for 15 minutes. The Telegram bot uses long polling, so it never receives
inbound HTTP on its own — without this server Render would put it to sleep
and updates would stop arriving until the next ping.

Bind to `0.0.0.0:$PORT` (Render injects PORT), expose `/` and `/health` that
return 200 OK, and let an external pinger (cron-job.org, UptimeRobot, etc.)
hit the public URL every few minutes to keep the service warm.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)

_started_at = time.time()


class _Handler(BaseHTTPRequestHandler):
    server_version = "serbia-parser-keepalive/1.0"

    def do_GET(self) -> None:  # noqa: N802 — stdlib API name
        try:
            if self.path in ("/health", "/healthz", "/", "/ping"):
                payload = {
                    "status": "ok",
                    "service": "serbia-business-parser-bot",
                    "uptime_s": round(time.time() - _started_at, 1),
                }
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            # Health-check clients (Render's prober, browsers, curl) sometimes
            # disconnect before we finish writing. That's fine and not worth
            # the multi-line traceback BaseHTTPRequestHandler would otherwise
            # dump on stderr.
            return

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 — stdlib name
        log.debug("keep_alive: " + fmt, *args)

    def log_error(self, fmt: str, *args) -> None:
        # Same reason as above — keep socketserver's chatter out of the logs.
        log.debug("keep_alive error: " + fmt, *args)


def start(port: int | None = None) -> ThreadingHTTPServer:
    """Start the keep-alive server in a background thread.

    Returns the running server so callers can `shutdown()` it on exit.
    Idempotent across multiple calls: a second invocation reuses the first.
    """
    if port is None:
        port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="keep-alive",
        daemon=True,
    )
    thread.start()
    log.info("keep_alive server listening on 0.0.0.0:%s", port)
    return server


__all__ = ["start"]
