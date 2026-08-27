"""HTTP handler for Claude Desktop rewrite proxy."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any

from claude_desktop_proxy.catalog import ADVERTISED, model_payload
from claude_desktop_proxy.config import Settings
from claude_desktop_proxy.protocols import ModelRewriter
from claude_desktop_proxy.rewrite import should_rewrite
from claude_desktop_proxy.upstream import OllamaForwarder


@dataclass
class ProxyDeps:
    rewriter: ModelRewriter
    forwarder: OllamaForwarder


def make_handler_class(deps: ProxyDeps) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in {"/", "/health", "/health/"}:
                self._json(
                    200,
                    {
                        "ok": True,
                        "proxy": "claude-desktop-proxy",
                        "upstream": Settings.upstream,
                        "local_model": Settings.local_model,
                        "listen": f"http://{Settings.listen_host}:{Settings.listen_port}",
                        "advertised": [item["id"] for item in ADVERTISED],
                    },
                )
                return
            if path in {"/v1/models", "/v1/models/"}:
                self._json(200, {"object": "list", "data": [model_payload(item) for item in ADVERTISED]})
                return
            if path.startswith("/v1/models/"):
                model_id = path[len("/v1/models/") :].strip("/")
                for item in ADVERTISED:
                    if item["id"] == model_id:
                        self._json(200, model_payload(item))
                        return
                if should_rewrite(model_id):
                    self._json(
                        200,
                        model_payload(
                            {
                                "id": model_id,
                                "display_name": "Qwen 3.8 27B (local)",
                                "anthropic_family_tier": "sonnet",
                                "is_family_default": False,
                            }
                        ),
                    )
                    return
                self._json(
                    404,
                    {
                        "type": "error",
                        "error": {
                            "type": "not_found_error",
                            "message": f'model "{model_id}" not found',
                        },
                    },
                )
                return
            self._forward(b"", None)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            incoming = self.rfile.read(length) if length else b""
            original = None
            path = self.path.split("?", 1)[0]
            if path.startswith("/v1/messages"):
                incoming, original = deps.rewriter.rewrite_request(incoming)
            self._forward(incoming, original)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_forward_response(
            self, status: int, headers: dict[str, str], body: bytes | None
        ) -> None:
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            if body is not None:
                self.wfile.write(body)
                self.wfile.flush()

        def _forward(self, incoming: bytes, original: str | None) -> None:
            self.close_connection = True
            headers = deps.forwarder.filter_headers(self.headers.items())
            wants_stream = False
            try:
                wants_stream = bool(json.loads(incoming or b"{}").get("stream"))
            except json.JSONDecodeError:
                pass

            def write_chunk(chunk: bytes) -> None:
                self.wfile.write(chunk)
                self.wfile.flush()

            deps.forwarder.forward(
                self.command,
                self.path,
                incoming if self.command != "GET" else None,
                headers,
                wants_stream,
                original,
                write_chunk,
                self._send_forward_response,
            )

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("[claude-desktop-proxy] " + (fmt % args) + "\n")

    return Handler
