from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from urllib.error import URLError
from urllib.request import urlopen


VERSION = "card-01-scaffold"


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path in {"/", "/health"}:
            api_url = os.environ.get("DATALAKE_API_URL", "http://api:8000")
            try:
                with urlopen(f"{api_url}/health", timeout=3) as response:
                    api_health = json.loads(response.read().decode("utf-8"))
            except URLError:
                self._write_json(
                    503,
                    {
                        "service": "mcp",
                        "status": "degraded",
                        "version": VERSION,
                        "api_reachable": False,
                    },
                )
                return

            self._write_json(
                200,
                {
                    "service": "mcp",
                    "status": "running",
                    "version": VERSION,
                    "api_reachable": True,
                    "api_status": api_health.get("status", "unknown"),
                },
            )
            return

        self._write_json(404, {"error": "not_found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - Base API
        return


def main() -> None:
    port = int(os.environ.get("MCP_PORT", "8001"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
