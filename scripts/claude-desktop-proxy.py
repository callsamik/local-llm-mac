#!/usr/bin/env python3
"""Sit between Claude Desktop and Ollama.

Desktop insists on Anthropic model ids (claude-sonnet-4-6) and Ollama's
Claude sidecar on :11435 rejects anything it does not catalog. This proxy
advertises claude-sonnet-4-6, rewrites it to qwen-code, and forwards to
Ollama on :11434.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "http://127.0.0.1:11434"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 11436
LOCAL_MODEL = "qwen-code"

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}


def rewrite_model(raw: bytes) -> bytes:
    if not raw:
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    model = data.get("model")
    if isinstance(model, str) and (
        model.startswith("claude-") or model in {"sonnet", "opus", "haiku", "fable", "mythos"}
    ):
        data["model"] = LOCAL_MODEL
        return json.dumps(data).encode()
    return raw


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] in {"/v1/models", "/v1/models/"}:
            payload = {
                "object": "list",
                "data": [
                    {
                        "id": "claude-sonnet-4-6",
                        "object": "model",
                        "owned_by": "ollama",
                        "display_name": "Qwen 3.8 27B (local)",
                        "anthropic_family_tier": "sonnet",
                        "is_family_default": True,
                        "context_length": 32768,
                    }
                ],
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        incoming = self.rfile.read(length) if length else b""
        if self.command == "POST" and self.path.startswith("/v1/messages"):
            incoming = rewrite_model(incoming)
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in HOP_BY_HOP
        }
        headers["Content-Length"] = str(len(incoming))
        req = urllib.request.Request(
            UPSTREAM + self.path,
            data=incoming if self.command != "GET" else None,
            method=self.command,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() not in HOP_BY_HOP:
                        self.send_header(key, value)
                self.end_headers()
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urllib.error.HTTPError as exc:
            err_body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as exc:  # noqa: BLE001
            msg = json.dumps(
                {"type": "error", "error": {"type": "api_error", "message": str(exc)}}
            ).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[claude-desktop-proxy] " + (fmt % args) + "\n")


def main() -> None:
    print(
        f"Claude Desktop proxy  http://{LISTEN_HOST}:{LISTEN_PORT}  ->  {UPSTREAM} ({LOCAL_MODEL})",
        flush=True,
    )
    print("In Desktop, set Gateway base URL to that address. Leave Ollama Claude toggle OFF.", flush=True)
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
