"""Health check HTTP server."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthState:
    """Thread-safe health state container."""

    def __init__(self):
        self._lock = threading.Lock()
        self._healthy = False
        self._reason = "Starting up"
        self._gluetun_ok = False
        self._qbittorrent_ok = False

    def set_healthy(self, healthy: bool, reason: str = "") -> None:
        """Update health state."""
        with self._lock:
            self._healthy = healthy
            self._reason = reason

    def set_service_status(self, gluetun_ok: bool, qbittorrent_ok: bool) -> None:
        """Update individual service status."""
        with self._lock:
            self._gluetun_ok = gluetun_ok
            self._qbittorrent_ok = qbittorrent_ok
            if gluetun_ok and qbittorrent_ok:
                self._healthy = True
                self._reason = ""
            else:
                self._healthy = False
                reasons = []
                if not gluetun_ok:
                    reasons.append("Gluetun unreachable")
                if not qbittorrent_ok:
                    reasons.append("qBittorrent unreachable")
                self._reason = ", ".join(reasons)

    def get_status(self) -> tuple[bool, str]:
        """Get current health status."""
        with self._lock:
            return self._healthy, self._reason


def create_health_handler(state: HealthState, logger: logging.Logger):
    """Create a request handler class with access to health state."""

    class HealthHandler(BaseHTTPRequestHandler):
        """HTTP request handler for health checks."""

        def log_message(self, format: str, *args) -> None:
            """Override to use our logger."""
            logger.debug(f"Health check: {args[0]}")

        def do_GET(self) -> None:
            """Handle GET requests."""
            if self.path == "/health":
                healthy, reason = state.get_status()

                if healthy:
                    self.send_response(200)
                    response = {"status": "healthy"}
                else:
                    self.send_response(503)
                    response = {"status": "unhealthy", "reason": reason}

                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(404)
                self.end_headers()

    return HealthHandler


class HealthServer:
    """Health check HTTP server running in a background thread."""

    def __init__(self, port: int, state: HealthState, logger: logging.Logger):
        self.port = port
        self.state = state
        self.logger = logger
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the health server in a background thread."""
        handler = create_health_handler(self.state, self.logger)
        self._server = HTTPServer(("0.0.0.0", self.port), handler)

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

        self.logger.info(f"Health server started on port {self.port}")

    def _serve(self) -> None:
        """Serve requests until shutdown."""
        if self._server:
            self._server.serve_forever()

    def stop(self) -> None:
        """Stop the health server."""
        if self._server:
            self._server.shutdown()
            self.logger.debug("Health server stopped")
