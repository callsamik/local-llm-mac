"""Protocol interfaces for dependency injection."""
from __future__ import annotations

from typing import Any, Protocol

from llm_router.models import RouteDecision


class RouteScorer(Protocol):
    def score(self, user_text: str, data: dict[str, Any]) -> RouteDecision: ...


class LlmScorerBackend(Protocol):
    def score_route(self, user_text: str) -> dict[str, Any] | None: ...


class AuthProvider(Protocol):
    def cloud_api_key(self, headers: dict[str, str]) -> str: ...

    def load_claude_cli_oauth_token(self) -> str: ...

    def inbound_bearer_token(self, headers: dict[str, str]) -> str: ...

    def cloud_auth_ready(self, headers: dict[str, str]) -> bool: ...

    def auth_headers_local(self, headers: dict[str, str]) -> dict[str, str]: ...

    def auth_headers_cloud(self, headers: dict[str, str]) -> dict[str, str]: ...


class SessionStore(Protocol):
    def get(self, key: str) -> RouteDecision | None: ...

    def put(self, key: str, decision: RouteDecision) -> None: ...


class RouteDeciderPort(Protocol):
    def decide(self, headers: dict[str, str], data: dict[str, Any]) -> RouteDecision: ...


class UpstreamClient(Protocol):
    def exchange(
        self,
        upstream: str,
        path: str,
        data: dict[str, Any],
        extra_headers: dict[str, str],
        request_headers: dict[str, str],
    ) -> tuple[int, bytes | None, str | None, Exception | None]: ...
