#!/usr/bin/env python3
"""Serve one resumable human blind test on the local loopback interface only."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from human_blind_test import BlindTestRun


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "human-blind-test"
PUBLIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def make_handler(run: BlindTestRun) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler closed over exactly one local blind-test run."""

    class BlindTestHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_asset(self, filename: str, content_type: str) -> None:
            try:
                body = (ASSET_ROOT / filename).read_bytes()
            except OSError:
                self._send_json(404, {"error": "not found"})
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as error:
                raise ValueError("invalid Content-Length") from error
            if length < 0 or length > 20_000:
                raise ValueError("request body is too large")
            if length == 0:
                return {}
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("request body must be UTF-8 JSON") from error
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _active_origin(self) -> tuple[str, str]:
            host, port = self.server.server_address[:2]
            authority = str(host) if port == 80 else f"{host}:{port}"
            return authority, f"http://{authority}"

        def _validate_mutation_request(self) -> bool:
            authority, origin = self._active_origin()
            if self.headers.get("Host", "").strip().lower() != authority.lower():
                self._send_json(403, {"error": "request Host does not match the active loopback server"})
                return False
            request_origin = self.headers.get("Origin")
            if request_origin is not None and request_origin.strip().lower() != origin.lower():
                self._send_json(403, {"error": "cross-origin mutation is forbidden"})
                return False
            if self.headers.get_content_type().lower() != "application/json":
                self._send_json(415, {"error": "Content-Type must be application/json"})
                return False
            return True

        @staticmethod
        def _progress_payload() -> dict:
            snapshot = run.snapshot()
            answers = {
                item["item_id"]: item["answer"]
                for item in snapshot["items"]
                if "answer" in item
            }
            return {
                "item_count": snapshot["item_count"],
                "answered_count": snapshot["answered_count"],
                "finalized": snapshot["finalized"],
                "answers": answers,
            }

        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP callback name
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if self.path in PUBLIC_ASSETS:
                self._send_asset(*PUBLIC_ASSETS[self.path])
                return
            if self.path == "/api/test":
                self._send_json(200, run.snapshot())
                return
            if self.path == "/api/progress":
                self._send_json(200, self._progress_payload())
                return
            if self.path == "/api/results":
                try:
                    result = run.finalized_result()
                except RuntimeError as error:
                    self._send_json(409, {"error": str(error)})
                else:
                    self._send_json(200, result)
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP callback name
            if self.path not in {"/api/answer", "/api/finalize"}:
                self._send_json(404, {"error": "not found"})
                return
            if not self._validate_mutation_request():
                return
            try:
                payload = self._read_json()
                if self.path == "/api/answer":
                    snapshot = run.save_answer(**payload)
                    self._send_json(200, snapshot)
                else:
                    self._send_json(200, run.finalize())
            except RuntimeError as error:
                self._send_json(409, {"error": str(error)})
            except (TypeError, ValueError) as error:
                self._send_json(400, {"error": str(error)})

    return BlindTestHandler


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, required=True, help="public-test.json path")
    parser.add_argument("--private", type=Path, required=True, help="private-human-key.json path")
    parser.add_argument("--manifest", type=Path, required=True, help="human-test-manifest.json path")
    parser.add_argument("--progress", type=Path, required=True, help="resumable progress output path")
    parser.add_argument("--result", type=Path, required=True, help="immutable unblinded result output path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="loopback port; 0 selects an available port")
    args = parser.parse_args(argv)
    if args.host != "127.0.0.1":
        parser.error("--host must be 127.0.0.1")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run = BlindTestRun(
        _load_json(args.public), _load_json(args.private), _load_json(args.manifest),
        args.progress, args.result,
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(run))
    print(json.dumps({"host": "127.0.0.1", "port": server.server_port}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
