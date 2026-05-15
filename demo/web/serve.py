"""Minimal HTTP bridge: browser <-> Circex TCP worker.

Browsers can't speak the worker's raw JSON-line TCP protocol, so this is a
~zero-dependency http.server shim:

    GET  /                -> serves index.html
    POST /api/tool        -> forwards {tool, arguments} to the worker, returns
                             the worker's JSON response verbatim
    GET  /api/health      -> {"worker": "up"|"down"}

Run the worker first (`circex serve --port 8765`), then:

    python demo/web/serve.py            # http://127.0.0.1:8080

Binds to 127.0.0.1 only. Serves exactly one static file (index.html) — no
filesystem traversal. The set of callable tools is allow-listed.
"""

from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORKER_HOST = "127.0.0.1"
WORKER_PORT = 8765
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8080

_INDEX = Path(__file__).parent / "index.html"

# Only these tools may be invoked through the browser bridge.
ALLOWED_TOOLS = frozenset(
    {
        "extract_properties",
        "get_redshift",
        "get_photometry",
        "get_classification",
        "find_counterparts",
        "search_gcn_circulars",
        "fetch_gcn_circulars",
    }
)


def call_worker(
    tool: str, arguments: dict[str, object], timeout: float = 30.0
) -> dict[str, object]:
    """Send one JSON-line request to the worker, return the parsed response dict."""
    with socket.create_connection((WORKER_HOST, WORKER_PORT), timeout=timeout) as sock:
        sock.sendall(
            (json.dumps({"tool": tool, "arguments": arguments}) + "\n").encode("utf-8")
        )
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
    line = b"".join(chunks).split(b"\n", 1)[0].decode("utf-8")
    parsed: dict[str, object] = json.loads(line)
    return parsed


def worker_is_up() -> bool:
    try:
        with socket.create_connection((WORKER_HOST, WORKER_PORT), timeout=2):
            return True
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "CircexBridge/0.1"

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            if not _INDEX.exists():
                self._send_json(500, {"error": "index.html missing"})
                return
            body = _INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/health":
            self._send_json(200, {"worker": "up" if worker_is_up() else "down"})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/tool":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            req = json.loads(raw.decode("utf-8"))
            tool = req.get("tool")
            arguments = req.get("arguments") or {}
            if not isinstance(tool, str) or tool not in ALLOWED_TOOLS:
                self._send_json(400, {"error": f"tool not allowed: {tool!r}"})
                return
            if not isinstance(arguments, dict):
                self._send_json(400, {"error": "'arguments' must be an object"})
                return
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"bad request: {exc}"})
            return

        try:
            worker_response = call_worker(tool, arguments)
        except (TimeoutError, OSError) as exc:
            self._send_json(
                502,
                {"error": f"worker unreachable on {WORKER_HOST}:{WORKER_PORT} ({exc}). "
                          f"Start it with: circex serve --port {WORKER_PORT}"},
            )
            return
        except json.JSONDecodeError as exc:
            self._send_json(502, {"error": f"bad worker response: {exc}"})
            return

        self._send_json(200, worker_response)

    def log_message(self, fmt: str, *args: object) -> None:
        # Quieter than the default; one line per request.
        print(f"[bridge] {self.address_string()} {fmt % args}")


def main() -> None:
    httpd = ThreadingHTTPServer((BRIDGE_HOST, BRIDGE_PORT), Handler)
    print(f"Circex web bridge on http://{BRIDGE_HOST}:{BRIDGE_PORT}")
    print(f"Proxying to worker at {WORKER_HOST}:{WORKER_PORT}")
    print("(start the worker with: circex serve --port 8765)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbridge stopped")
        httpd.server_close()


if __name__ == "__main__":
    main()
