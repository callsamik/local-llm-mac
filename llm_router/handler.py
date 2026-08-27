"""HTTP request handler with injected dependencies."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any

from llm_router.cascade import cascade_from, model_for_lane, should_failover_status
from llm_router.config import Cfg
from llm_router.models import AUTO_LANES, LANE_ORDER
from llm_router.protocols import AuthProvider, RouteDeciderPort, UpstreamClient
from llm_router.rewrite import rewrite_for_hosted, rewrite_for_local
from llm_router.scoring.effort import defaults_for_failover_lane


@dataclass
class HandlerDeps:
    route_decider: RouteDeciderPort
    auth: AuthProvider
    upstream: UpstreamClient


def make_handler_class(deps: HandlerDeps) -> type[BaseHTTPRequestHandler]:
    """Build a Handler class with injected dependencies."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in {"/", "/health", "/health/"}:
                self._json(
                    200,
                    {
                        "ok": True,
                        "proxy": "llm-router",
                        "lanes": LANE_ORDER,
                        "auto_lanes": sorted(AUTO_LANES),
                        "cascade": Cfg.cascade,
                        "disable_opus": Cfg.disable_opus,
                        "disable_fable": Cfg.disable_fable,
                        "enable_opus": Cfg.enable_opus,
                        "enable_fable": Cfg.enable_fable,
                        "local_upstream": Cfg.local_upstream,
                        "cloud_upstream": Cfg.cloud_upstream,
                        "local_model": Cfg.local_model,
                        "haiku_model": Cfg.haiku_model,
                        "sonnet_model": Cfg.sonnet_model,
                        "opus_model": Cfg.opus_model,
                        "fable_model": Cfg.fable_model,
                        "cheap_model": Cfg.haiku_model,
                        "frontier_model": Cfg.sonnet_model,
                        "cloud_model": Cfg.sonnet_model,
                        "listen": f"http://{Cfg.listen_host}:{Cfg.listen_port}",
                        "cloud_key_configured": bool(deps.auth.cloud_api_key({})),
                        "claude_cli_oauth_configured": bool(deps.auth.load_claude_cli_oauth_token()),
                        "cloud_auth_ready": deps.auth.cloud_auth_ready({}),
                        "llm_classify": Cfg.llm_classify,
                        "llm_classify_timeout": Cfg.llm_classify_timeout,
                        "llm_score_model": Cfg.local_model,
                        "local_think": Cfg.local_think,
                    },
                )
                return
            if path in {"/v1/models", "/v1/models/"}:
                self._json(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": "claude-sonnet-4-6",
                                "object": "model",
                                "owned_by": "router",
                                "display_name": (
                                    f"Router → {Cfg.local_model}/{Cfg.haiku_model}/"
                                    f"{Cfg.sonnet_model}/{Cfg.opus_model}/{Cfg.fable_model}"
                                ),
                            },
                            {"id": Cfg.local_model, "object": "model", "owned_by": "ollama"},
                            {"id": Cfg.haiku_model, "object": "model", "owned_by": "anthropic"},
                            {"id": Cfg.sonnet_model, "object": "model", "owned_by": "anthropic"},
                            {"id": Cfg.opus_model, "object": "model", "owned_by": "anthropic"},
                            {"id": Cfg.fable_model, "object": "model", "owned_by": "anthropic"},
                        ],
                    },
                )
                return
            self.send_error(404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            path = self.path.split("?", 1)[0]
            if not path.startswith("/v1/messages"):
                self.send_error(404)
                return
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._json(400, {"type": "error", "error": {"message": "invalid json"}})
                return

            headers = {k.lower(): v for k, v in self.headers.items()}
            decision = deps.route_decider.decide(headers, data)
            route = decision.lane
            if Cfg.log_routes:
                sys.stderr.write(
                    f"[llm-router] route={route} effort={decision.effort} "
                    f"thinking={decision.thinking} reason={decision.reason}\n"
                )

            chain = cascade_from(route) if Cfg.cascade else [route]
            # If no cloud auth, hosted steps collapse to local.
            if not deps.auth.cloud_auth_ready(headers):
                chain = ["local"]
                if Cfg.log_routes and route != "local":
                    sys.stderr.write("[llm-router] cascade→local reason=cloud-auth-missing\n")

            last_error: bytes | None = None
            last_status = 502
            for i, lane in enumerate(chain):
                if lane == "local":
                    payload = rewrite_for_local(data)
                    upstream = Cfg.local_upstream
                    auth = deps.auth.auth_headers_local(headers)
                else:
                    effort, thinking = defaults_for_failover_lane(lane, decision.score)
                    if lane == decision.lane:
                        effort, thinking = decision.effort, decision.thinking
                    payload = rewrite_for_hosted(
                        data, model_for_lane(lane), effort, thinking
                    )
                    upstream = Cfg.cloud_upstream
                    auth = deps.auth.auth_headers_cloud(headers)
                if Cfg.log_routes:
                    oc = payload.get("output_config") if isinstance(payload, dict) else None
                    eff = oc.get("effort") if isinstance(oc, dict) else None
                    th = (payload.get("thinking") or {}).get("type") if isinstance(payload.get("thinking"), dict) else None
                    sys.stderr.write(
                        f"[llm-router] try lane={lane} model={payload.get('model')} "
                        f"effort={eff} thinking={th} upstream={upstream}\n"
                    )
                status, body, content_type, exc = deps.upstream.exchange(
                    upstream,
                    self.path,
                    payload,
                    auth,
                    {k.lower(): v for k, v in self.headers.items()},
                )
                if exc is not None:
                    last_error = json.dumps(
                        {
                            "type": "error",
                            "error": {
                                "type": "api_error",
                                "message": f"{exc} (upstream {upstream} lane={lane})",
                            },
                        }
                    ).encode()
                    last_status = 502
                    if i < len(chain) - 1:
                        if Cfg.log_routes:
                            sys.stderr.write(
                                f"[llm-router] failover {lane}→{chain[i+1]} reason=connect-error\n"
                            )
                        continue
                    self._raw(last_status, last_error, "application/json")
                    return
                assert body is not None
                if should_failover_status(status, body) and i < len(chain) - 1:
                    last_error = body
                    last_status = status
                    if Cfg.log_routes:
                        sys.stderr.write(
                            f"[llm-router] failover {lane}→{chain[i+1]} reason=http-{status}\n"
                        )
                    continue
                degraded = lane != route
                self._write_upstream_response(status, body, content_type or "application/json", degraded, lane)
                return

            self._raw(
                last_status,
                last_error
                or json.dumps(
                    {"type": "error", "error": {"message": "cascade exhausted"}}
                ).encode(),
                "application/json",
            )

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
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def _raw(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def _write_upstream_response(
            self,
            status: int,
            body: bytes,
            content_type: str,
            degraded: bool,
            lane: str,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            if degraded:
                self.send_header("x-router-degraded", "true")
                self.send_header("x-router-lane", lane)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("[llm-router] " + (fmt % args) + "\n")

    return Handler
