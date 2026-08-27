"""Rewrite Claude model ids to the local Ollama model."""
from __future__ import annotations

import json

from claude_desktop_proxy.catalog import REWRITE_EXACT
from claude_desktop_proxy.config import Settings


def should_rewrite(model: str) -> bool:
    if model in REWRITE_EXACT:
        return True
    if model.startswith("claude-") or model.startswith("anthropic/"):
        return True
    return False


class LocalModelRewriter:
    """Single responsibility: map Anthropic-looking model ids ↔ local model."""

    def __init__(self, local_model: str | None = None) -> None:
        self._local_model = local_model or Settings.local_model

    @property
    def local_model(self) -> str:
        return self._local_model or Settings.local_model

    def rewrite_request(self, raw: bytes) -> tuple[bytes, str | None]:
        if not raw:
            return raw, None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw, None
        model = data.get("model")
        if isinstance(model, str) and should_rewrite(model):
            original = model
            data["model"] = self.local_model
            return json.dumps(data).encode(), original
        return raw, model if isinstance(model, str) else None

    def restore_response(self, raw: bytes, original: str | None) -> bytes:
        if not original or not raw or original == self.local_model:
            return raw
        local = self.local_model
        for needle, repl in (
            (f'"model":"{local}"', f'"model":"{original}"'),
            (f'"model": "{local}"', f'"model": "{original}"'),
        ):
            raw = raw.replace(needle.encode(), repl.encode())
        return raw
