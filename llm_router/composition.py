"""Dependency injection composition root."""
from __future__ import annotations

from http.server import ThreadingHTTPServer

from llm_router.auth import AuthService
from llm_router.handler import HandlerDeps, make_handler_class
from llm_router.routing import RouteDecider
from llm_router.scoring.composite import CompositeScorer
from llm_router.scoring.heuristic import HeuristicScorer
from llm_router.scoring.llm import OllamaLlmScorer
from llm_router.session import InMemorySessionStore
from llm_router.upstream import HttpUpstreamClient

_default_deps: HandlerDeps | None = None


def build_handler_deps() -> HandlerDeps:
    """Construct handler dependencies with default implementations."""
    global _default_deps
    if _default_deps is None:
        auth = AuthService()
        scorer = CompositeScorer(HeuristicScorer(), OllamaLlmScorer())
        sessions = InMemorySessionStore()
        _default_deps = HandlerDeps(
            route_decider=RouteDecider(scorer, sessions, auth),
            auth=auth,
            upstream=HttpUpstreamClient(),
        )
    return _default_deps


def default_route_decider() -> RouteDecider:
    return build_handler_deps().route_decider


def build_app() -> type:
    """Return the Handler class wired with default dependencies."""
    return make_handler_class(build_handler_deps())


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    handler_cls = build_app()
    return ThreadingHTTPServer((host, port), handler_cls)
