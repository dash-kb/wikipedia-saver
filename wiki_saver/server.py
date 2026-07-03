from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .saver import GitBackedWikiArchive, WikiSaverError, default_repo_path


class SaverRequestHandler(BaseHTTPRequestHandler):
    server_version = "WikipediaSaver/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"ok": True, "repo": str(self.archive.repo_path)})
            return
        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path == "/save":
            self._handle_save()
            return
        if self.path == "/status":
            self._handle_status()
            return
        if self.path == "/settings":
            self._handle_settings()
            return
        if self.path == "/update-all":
            self._handle_update_all()
            return
        self._send_json({"ok": False, "error": "Not found"}, status=404)

    @property
    def archive(self) -> GitBackedWikiArchive:
        return self.server.archive  # type: ignore[attr-defined]

    def _handle_save(self) -> None:
        payload = self._read_json()
        url = str(payload.get("url") or "")
        if not url:
            self._send_json({"ok": False, "error": "Missing url"}, status=400)
            return
        try:
            self._send_json(self.archive.save_url(url))
        except WikiSaverError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _handle_status(self) -> None:
        payload = self._read_json()
        url = str(payload.get("url") or "")
        if not url:
            self._send_json({"ok": False, "error": "Missing url"}, status=400)
            return
        try:
            self._send_json(self.archive.saved_status(url))
        except WikiSaverError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _handle_update_all(self) -> None:
        try:
            payload = self._read_json()
            self._send_json(self.archive.update_all(force=bool(payload.get("force"))))
        except WikiSaverError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _handle_settings(self) -> None:
        payload = self._read_json()
        try:
            if payload:
                self._send_json(self.archive.update_settings(payload))
            else:
                self._send_json(self.archive.get_settings())
        except WikiSaverError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def serve(host: str = "127.0.0.1", port: int = 8765, repo_path: Path | str | None = None) -> None:
    archive = GitBackedWikiArchive(repo_path or default_repo_path())
    archive.ensure_repo()
    httpd = ThreadingHTTPServer((host, port), SaverRequestHandler)
    httpd.archive = archive  # type: ignore[attr-defined]
    print(f"Wikipedia Saver listening on http://{host}:{port}")
    print(f"Saving pages to {archive.repo_path}")
    httpd.serve_forever()
