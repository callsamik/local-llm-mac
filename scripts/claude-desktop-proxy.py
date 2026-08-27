#!/usr/bin/env python3
"""Claude Desktop → local Ollama rewrite proxy.

Claude Desktop insists on Anthropic model ids such as claude-sonnet-4-6.
Ollama's Claude sidecar on :11435 catalogs real Claude slots and returns:

    unknown Claude model "claude-sonnet-4-6"

This proxy listens on :11436, advertises those Claude ids, rewrites them to
qwen-code, and forwards Anthropic /v1/messages to Ollama on :11434.

Do not point Desktop at 11435. Turn Ollama → Apps → Claude Off, then use:

    Gateway base URL: http://127.0.0.1:11436
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

class Settings:
    upstream = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
    listen_host = os.environ.get("CLAUDE_DESKTOP_PROXY_HOST", "127.0.0.1")
    listen_port = int(os.environ.get("CLAUDE_DESKTOP_PROXY_PORT", "11436"))
    local_model = os.environ.get("CLAUDE_LOCAL_MODEL", "qwen-code")


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

# Ids Desktop has been seen to send or probe. All rewrite to Settings.local_model.
ADVERTISED = [
    {
        "id": "claude-sonnet-4-6",
        "display_name": "Qwen 3.8 27B (local)",
        "anthropic_family_tier": "sonnet",
        "is_family_default": True,
    },
    {
        "id": "claude-sonnet-4-5",
        "display_name": "Qwen 3.8 27B (local)",
        "anthropic_family_tier": "sonnet",
        "is_family_default": False,
    },
    {
        "id": "claude-sonnet-4-5-20250929",
        "display_name": "Qwen 3.8 27B (local)",
        "anthropic_family_tier": "sonnet",
        "is_family_default": False,
    },
    {
        "id": "claude-haiku-4-5",
        "display_name": "Qwen 3.8 27B (local, haiku slot)",
        "anthropic_family_tier": "haiku",
        "is_family_default": True,
    },
]

REWRITE_EXACT = {
    "sonnet",
    "opus",
    "haiku",
    "fable",
    "mythos",
    *(item["id"] for item in ADVERTISED),
}


def model_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "object": "model",
        "owned_by": "ollama",
        "display_name": item["display_name"],
        "anthropic_family_tier": item["anthropic_family_tier"],
        "is_family_default": item["is_family_default"],
        "context_length": 32768,
        "max_tokens": 8192,
        "type": "claude",
    }


def should_rewrite(model: str) -> bool:
    if model in REWRITE_EXACT:
        return True
    if model.startswith("claude-") or model.startswith("anthropic/"):
        return True
    return False


def rewrite_model(raw: bytes) -> tuple[bytes, str | None]:
    if not raw:
        return raw, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, None
    model = data.get("model")
    if isinstance(model, str) and should_rewrite(model):
        original = model
        data["model"] = Settings.local_model
        return json.dumps(data).encode(), original
    return raw, model if isinstance(model, str) else None


def restore_model(raw: bytes, original: str | None) -> bytes:
    if not original or not raw or original == Settings.local_model:
        return raw
    local = Settings.local_model
    # Compact and spaced JSON both show up (dumps vs streaming SSE).
    for needle, repl in (
        (f'"model":"{local}"', f'"model":"{original}"'),
        (f'"model": "{local}"', f'"model": "{original}"'),
    ):
        raw = raw.replace(needle.encode(), repl.encode())
    return raw


def sidecar_warning() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        sock.connect(("127.0.0.1", 11435))
    except OSError:
        return
    finally:
        sock.close()
    sys.stderr.write(
        "\n"
        "!!  Port 11435 is in use (Ollama's Claude sidecar).\n"
        "!!  That sidecar returns: unknown Claude model \"claude-sonnet-4-6\"\n"
        "!!  Turn Ollama → Apps → Claude  Off, then in Desktop set:\n"
        f"!!    Gateway base URL  http://{Settings.listen_host}:{Settings.listen_port}\n"
        "!!  Do not leave Desktop pointed at 11435.\n"
        "\n"
    )


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
                    "error": {"type": "not_found_error", "message": f'model "{model_id}" not found'},
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
            incoming, original = rewrite_model(incoming)
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

    def _forward(self, incoming: bytes, original: str | None) -> None:
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        headers["Content-Length"] = str(len(incoming))
        if "x-api-key" not in {k.lower() for k in headers} and "authorization" not in {
            k.lower() for k in headers
        }:
            headers["x-api-key"] = "ollama"
        req = urllib.request.Request(
            Settings.upstream + self.path,
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
                    self.wfile.write(restore_model(chunk, original))
                    self.wfile.flush()
        except urllib.error.HTTPError as exc:
            err_body = restore_model(exc.read(), original)
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as exc:  # noqa: BLE001
            msg = json.dumps(
                {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"{exc}. Is Ollama running on {Settings.upstream}?",
                    },
                }
            ).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[claude-desktop-proxy] " + (fmt % args) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite Claude Desktop model ids to local Ollama.")
    parser.add_argument("--host", default=Settings.listen_host)
    parser.add_argument("--port", type=int, default=Settings.listen_port)
    parser.add_argument("--upstream", default=Settings.upstream)
    parser.add_argument("--model", default=Settings.local_model)
    args = parser.parse_args()

    Settings.listen_host = args.host
    Settings.listen_port = args.port
    Settings.upstream = args.upstream.rstrip("/")
    Settings.local_model = args.model

    sidecar_warning()
    print(
        f"Claude Desktop proxy  http://{Settings.listen_host}:{Settings.listen_port}  ->  {Settings.upstream} ({Settings.local_model})",
        flush=True,
    )
    print(
        "Desktop gateway URL must be this address, not :11435. Ollama → Apps → Claude = Off.",
        flush=True,
    )
    try:
        ThreadingHTTPServer((Settings.listen_host, Settings.listen_port), Handler).serve_forever()
    except OSError as exc:
        sys.stderr.write(
            f"error: could not bind {Settings.listen_host}:{Settings.listen_port}: {exc}\n"
            "If something else is already serving that port, stop it or pass --port.\n"
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
