"""HTTP upstream forwarder to Ollama."""
from __future__ import annotations

import http.client
import json
from typing import Callable
from urllib.parse import urlparse

from claude_desktop_proxy.config import Settings
from claude_desktop_proxy.rewrite import LocalModelRewriter

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


class OllamaForwarder:
    """Forwards Desktop requests to Ollama; restores model ids in responses."""

    def __init__(
        self,
        upstream: str | None = None,
        rewriter: LocalModelRewriter | None = None,
    ) -> None:
        self._upstream = (upstream or Settings.upstream).rstrip("/")
        self._rewriter = rewriter or LocalModelRewriter()

    def filter_headers(self, headers_items) -> dict[str, str]:
        headers = {k: v for k, v in headers_items if k.lower() not in HOP_BY_HOP}
        header_names = {k.lower() for k in headers}
        if "x-api-key" not in header_names and "authorization" not in header_names:
            headers["x-api-key"] = "ollama"
        return headers

    def forward(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
        stream: bool,
        restore_original: str | None,
        write_chunk: Callable[[bytes], None],
        send_response: Callable[..., None],
    ) -> None:
        payload = body or b""
        headers = dict(headers)
        headers["Content-Length"] = str(len(payload))
        parsed = urlparse(self._upstream)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            conn = http.client.HTTPConnection(host, port, timeout=600)
            conn.request(
                method,
                path,
                body=payload if method != "GET" else None,
                headers=headers,
            )
            resp = conn.getresponse()
            content_type = resp.getheader("Content-Type") or "application/json"
            if stream:
                send_response(
                    resp.status,
                    headers={
                        "Content-Type": content_type,
                        "Cache-Control": "no-cache",
                        "Connection": "close",
                    },
                    body=None,
                )
                while True:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    write_chunk(self._rewriter.restore_response(chunk, restore_original))
            else:
                out = self._rewriter.restore_response(resp.read(), restore_original)
                send_response(
                    resp.status,
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(len(out)),
                        "Connection": "close",
                        "Cache-Control": "no-store",
                    },
                    body=out,
                )
            conn.close()
        except Exception as exc:  # noqa: BLE001
            msg = json.dumps(
                {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": (
                            f"{exc}. Is Ollama running on {self._upstream}? "
                            f"Load the model first: ollama run {self._rewriter.local_model} pong"
                        ),
                    },
                }
            ).encode()
            send_response(
                502,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(msg)),
                    "Connection": "close",
                },
                body=msg,
            )
