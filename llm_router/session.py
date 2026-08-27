"""Sticky per-conversation route cache."""
from __future__ import annotations

from llm_router.models import RouteDecision


class InMemorySessionStore:
    """Sticky route per conversation fingerprint so tool loops stay on one backend."""

    def __init__(self, max_size: int = 256) -> None:
        self._routes: dict[str, RouteDecision] = {}
        self._max_size = max_size

    def get(self, key: str) -> RouteDecision | None:
        return self._routes.get(key)

    def put(self, key: str, decision: RouteDecision) -> None:
        self._routes[key] = decision
        if len(self._routes) > self._max_size:
            self._routes.pop(next(iter(self._routes)))
