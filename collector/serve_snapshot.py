from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


SNAPSHOT = Path(
    os.getenv(
        "TOSS_SNAPSHOT_PATH",
        "/var/lib/stock-autoresearch/toss/latest.json",
    )
)
TOKEN = os.getenv("TOSS_SNAPSHOT_EXPORT_TOKEN", "")
HOST = os.getenv("TOSS_SNAPSHOT_HOST", "127.0.0.1")
PORT = int(os.getenv("TOSS_SNAPSHOT_PORT", "8765"))


class Handler(BaseHTTPRequestHandler):
    server_version = "StockAutoResearchSnapshot/1.0"

    def _authorized(self) -> bool:
        if not TOKEN:
            return False
        value = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not value.startswith(prefix):
            return False
        supplied = value[len(prefix):]
        return hmac.compare_digest(supplied, TOKEN)

    def _json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._json(
                200,
                {
                    "ok": SNAPSHOT.exists(),
                    "snapshot_exists": SNAPSHOT.exists(),
                },
            )
            return

        if path != "/latest.json":
            self._json(404, {"error": "not-found"})
            return

        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return

        try:
            raw = SNAPSHOT.read_bytes()
            json.loads(raw.decode("utf-8"))
        except FileNotFoundError:
            self._json(404, {"error": "snapshot-not-found"})
            return
        except (OSError, json.JSONDecodeError):
            self._json(500, {"error": "invalid-snapshot"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "TOSS_SNAPSHOT_EXPORT_TOKEN이 없어서 서버를 시작하지 않습니다."
        )
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
