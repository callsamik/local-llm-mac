"""Unload an Ollama model after it has been idle for a while."""
from __future__ import annotations

import http.client
import json
import sys
import threading
from typing import Callable
from urllib.parse import urlparse

from llm_router.config import Cfg


def ollama_unload(model: str) -> None:
    """Ask Ollama to evict `model` now (keep_alive=0)."""
    parsed = urlparse(Cfg.local_upstream)
    body = json.dumps({"model": model, "keep_alive": 0}).encode()
    try:
        conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 11434, timeout=30)
        conn.request(
            "POST",
            "/api/generate",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        if Cfg.log_routes:
            sys.stderr.write(f"[llm-router] idle-unload model={model} status={resp.status}\n")
    except Exception as exc:  # noqa: BLE001
        if Cfg.log_routes:
            sys.stderr.write(f"[llm-router] idle-unload model={model} error={exc}\n")


class IdleUnloader:
    """Track in-flight requests per model; unload once idle for `idle_seconds`.

    `hold()` before a request, `release()` after. The timer only starts when the
    last in-flight request for that model finishes.
    """

    def __init__(
        self,
        idle_seconds: float,
        unload: Callable[[str], None] = ollama_unload,
    ) -> None:
        self._idle_seconds = idle_seconds
        self._unload = unload
        self._lock = threading.Lock()
        self._active: dict[str, int] = {}
        self._timers: dict[str, threading.Timer] = {}

    @property
    def enabled(self) -> bool:
        return self._idle_seconds > 0

    def hold(self, model: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            timer = self._timers.pop(model, None)
            if timer is not None:
                timer.cancel()
            self._active[model] = self._active.get(model, 0) + 1

    def release(self, model: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            count = max(0, self._active.get(model, 0) - 1)
            self._active[model] = count
            if count:
                return
            timer = threading.Timer(self._idle_seconds, self._fire, args=(model,))
            timer.daemon = True
            self._timers[model] = timer
            timer.start()

    def _fire(self, model: str) -> None:
        with self._lock:
            if self._active.get(model, 0) or model not in self._timers:
                return
            self._timers.pop(model, None)
        self._unload(model)
