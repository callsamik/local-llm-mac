"""HTTP upstream exchange client."""
from __future__ import annotations

import http.client
import json
from typing import Any
from urllib.parse import urlparse


class HttpUpstreamClient:
    """POST once to an upstream; return (status, body, content_type, error)."""

    def exchange(
        self,
        upstream: str,
        path: str,
        data: dict[str, Any],
        extra_headers: dict[str, str],
        request_headers: dict[str, str],
    ) -> tuple[int, bytes | None, str | None, Exception | None]:
        body = json.dumps(data).encode()
        parsed = urlparse(upstream)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "anthropic-version": request_headers.get("anthropic-version") or "2023-06-01",
        }
        headers.update(extra_headers)
        # Streaming cascade is complex; buffer non-stream for failover decisions.
        data_ns = dict(data)
        data_ns["stream"] = False
        body = json.dumps(data_ns).encode()
        headers["Content-Length"] = str(len(body))
        try:
            if parsed.scheme == "https":
                conn: http.client.HTTPConnection = http.client.HTTPSConnection(host, port, timeout=600)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=600)
            conn.request("POST", path, body=body, headers=headers)
            resp = conn.getresponse()
            out = resp.read()
            content_type = resp.getheader("Content-Type") or "application/json"
            status = resp.status
            conn.close()
            return status, out, content_type, None
        except Exception as exc:  # noqa: BLE001
            return 502, None, None, exc
