"""Composition root for Claude Desktop proxy."""
from __future__ import annotations

from http.server import ThreadingHTTPServer

from claude_desktop_proxy.config import Settings
from claude_desktop_proxy.handler import ProxyDeps, make_handler_class
from claude_desktop_proxy.rewrite import LocalModelRewriter
from claude_desktop_proxy.upstream import OllamaForwarder


def build_deps() -> ProxyDeps:
    rewriter = LocalModelRewriter(Settings.local_model)
    return ProxyDeps(
        rewriter=rewriter,
        forwarder=OllamaForwarder(Settings.upstream, rewriter),
    )


def build_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    handler = make_handler_class(build_deps())
    return ThreadingHTTPServer(
        (host or Settings.listen_host, port or Settings.listen_port),
        handler,
    )
