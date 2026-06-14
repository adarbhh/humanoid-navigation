"""
Tiny SSE (Server-Sent Events) dashboard server — stdlib only.

Usage
-----
    srv = DashboardServer(port=7654)
    url = srv.start()          # starts daemon thread, returns "http://127.0.0.1:7654/"
    srv.push(stats_dict)       # broadcast JSON to all connected browsers
    srv.stop()                 # clean shutdown
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_DEFAULT_HTML = Path(__file__).parent / "dashboard" / "index.html"


class DashboardServer:
    def __init__(self, port: int = 7654,
                 html_path: "str | Path | None" = None) -> None:
        self._port    = port
        self._html    = Path(html_path).read_bytes() if html_path else _DEFAULT_HTML.read_bytes()
        self._clients: list[queue.Queue] = []
        self._lock    = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread:  threading.Thread  | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> str:
        """Start the HTTP/SSE server in a daemon thread. Returns the dashboard URL."""
        self._server = ThreadingHTTPServer(("127.0.0.1", self._port),
                                           self._make_handler())
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True, name="DashboardServer")
        self._thread.start()
        return f"http://127.0.0.1:{self._port}/"

    def push(self, stats: dict) -> None:
        """Broadcast a stats dict to every connected SSE client."""
        payload = ("data: " + json.dumps(stats) + "\n\n").encode()
        with self._lock:
            dead: list[queue.Queue] = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._clients.remove(q)

    def stop(self) -> None:
        """Shutdown the server (blocks until the server thread exits)."""
        if self._server:
            self._server.shutdown()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_handler(self) -> type:
        server = self          # captured by Handler

        html = self._html  # capture per-instance HTML bytes

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_) -> None:
                pass           # silence access log

            def do_GET(self) -> None:
                if self.path.startswith("/events"):
                    self._sse()
                else:
                    self._page()

            def _page(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(html)

            def _sse(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                q: queue.Queue = queue.Queue(maxsize=30)
                with server._lock:
                    server._clients.append(q)

                try:
                    while True:
                        # 25s timeout doubles as a keepalive comment
                        try:
                            msg = q.get(timeout=25)
                            self.wfile.write(msg)
                            self.wfile.flush()
                        except queue.Empty:
                            # send SSE comment to keep connection alive
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with server._lock:
                        try:
                            server._clients.remove(q)
                        except ValueError:
                            pass

        return Handler
