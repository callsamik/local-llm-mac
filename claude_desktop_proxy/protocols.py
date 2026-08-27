"""Protocols for the desktop rewrite proxy."""
from __future__ import annotations

from typing import Protocol


class ModelRewriter(Protocol):
    def rewrite_request(self, raw: bytes) -> tuple[bytes, str | None]: ...

    def restore_response(self, raw: bytes, original: str | None) -> bytes: ...


class UpstreamForwarder(Protocol):
    def forward(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
        stream: bool,
        restore_original: str | None,
        write_chunk,
        send_response,
    ) -> None: ...
