#!/usr/bin/env python3
"""Route Anthropic /v1/messages across local / cheap / frontier.

local    → Ollama qwen-fast (easy/medium happy path)
cheap    → Anthropic Haiku
frontier → Anthropic Sonnet

Overrides:
  x-route / ROUTER_FORCE = local|cheap|frontier|cloud|auto
  (cloud is a legacy alias for frontier)

Claude Code: point ANTHROPIC_BASE_URL at this proxy (default :11437).
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


class Cfg:
    local_upstream = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
    cloud_upstream = os.environ.get("ANTHROPIC_UPSTREAM", "https://api.anthropic.com").rstrip("/")
    local_model = os.environ.get("ROUTER_LOCAL_MODEL", "qwen-fast")
    cheap_model = os.environ.get("ROUTER_CHEAP_MODEL", "claude-haiku-4-5")
    frontier_model = os.environ.get(
        "ROUTER_FRONTIER_MODEL",
        os.environ.get("ROUTER_CLOUD_MODEL", "claude-sonnet-4-6"),
    )
    # Back-compat alias
    cloud_model = frontier_model
    listen_host = os.environ.get("ROUTER_HOST", "127.0.0.1")
    listen_port = int(os.environ.get("ROUTER_PORT", "11437"))
    force = os.environ.get("ROUTER_FORCE", "").strip().lower()
    log_routes = os.environ.get("ROUTER_LOG", "1") != "0"


# Sticky route per conversation fingerprint so tool loops stay on one backend.
_SESSION_ROUTE: dict[str, str] = {}

HARD_PATTERNS = [
    r"\barchitect(ure|ing)?\b",
    r"\brefactors?\b.*\b(entire|whole|across|system)\b",
    r"\bmigrat(e|ion)\b",
    r"\brace\s*condition\b",
    r"\bdeadlock\b",
    r"\bflaky\b",
    r"\bproduction\s+(outage|incident|sev)\b",
    r"\bsecurity\s+audit\b",
    r"\bdesign\s+doc\b",
    r"\bmulti[- ]service\b",
    r"\bcross[- ]cutting\b",
    r"\bdeep\s+dive\b",
    r"\broot\s+cause\b",
    r"\bperformance\s+profil",
    r"\breasoning_effort\b.*\b(high|xhigh)\b",
    r"\bthink\s+hard\b",
    r"\bcomplex\s+bug\b",
]

MEDIUM_PATTERNS = [
    r"\bimplement\b",
    r"\badd\s+(a\s+)?(feature|test|endpoint|handler|component)\b",
    r"\bwrite\s+(a\s+)?(test|tests)\b",
    r"\badd\s+a\s+unit\s+test\b",
    r"\bfix\s+(the\s+)?bug\b",
    r"\bfix\b",
    r"\bunit\s+test\b",
    r"\brefactor\b",
]

EASY_PATTERNS = [
    r"\brename\b",
    r"\btypo\b",
    r"\bexplain\b",
    r"\bwhat\s+(is|does|are)\b",
    r"\bwhere\s+(is|are)\b",
    r"\blist\s+(the\s+)?files?\b",
    r"\bsummarize\b",
    r"\bformat\b",
    r"\bcomment\b",
    r"\bdocstring\b",
    r"\bsimple\b",
    r"\bquick\b",
    r"\bping\b",
    r"\bhello\b",
    r"\bboilerplate\b",
    r"\badd\s+a\s+(log|print|comment)\b",
]


def last_user_text(messages: list[Any]) -> str:
    text_parts: list[str] = []
    for msg in reversed(messages or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text_parts.append(content)
            break
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(str(block.get("text") or ""))
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    # Mid tool-loop: do not reclassify from tool blobs.
                    return ""
            break
    return "\n".join(text_parts).strip()


def session_key(data: dict[str, Any]) -> str:
    msgs = data.get("messages") or []
    bits: list[str] = []
    for msg in msgs[:4]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role == "user" and isinstance(content, str):
            bits.append(content[:500])
        elif role == "user" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    bits.append(str(block.get("text") or "")[:500])
    raw = "||".join(bits) or json.dumps(data.get("system", ""))[:200]
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def score_route(user_text: str, data: dict[str, Any]) -> tuple[str, str, int]:
    """Return (lane, reason, score). <=0 local, 1 cheap, >=2 frontier."""
    score = 0
    reasons: list[str] = []
    lower = user_text.lower()

    if not user_text:
        return "local", "empty-user-sticky-candidate", 0

    for pat in HARD_PATTERNS:
        if re.search(pat, lower, re.I):
            score += 2
            reasons.append(f"hard:{pat}")
    medium_hit = False
    for pat in MEDIUM_PATTERNS:
        if re.search(pat, lower, re.I):
            medium_hit = True
            reasons.append(f"medium:{pat}")
    if medium_hit:
        score += 1
    for pat in EASY_PATTERNS:
        if re.search(pat, lower, re.I):
            score -= 1
            reasons.append(f"easy:{pat}")

    if len(user_text) > 6000:
        score += 2
        reasons.append("long-user-text")
    elif len(user_text) > 2500:
        score += 1
        reasons.append("medium-user-text")

    thinking = data.get("thinking")
    if isinstance(thinking, dict):
        ttype = str(thinking.get("type") or "")
        if ttype in {"enabled", "adaptive"}:
            score += 2
            reasons.append("thinking-enabled")
        budget = thinking.get("budget_tokens") or 0
        try:
            if int(budget) >= 8000:
                score += 1
                reasons.append("thinking-budget")
        except (TypeError, ValueError):
            pass

    if re.search(r"reasoning[_\s-]?effort\s*[:=]\s*(high|xhigh)", lower):
        score += 2
        reasons.append("effort-high")

    if score <= 0:
        lane = "local"
    elif score == 1:
        lane = "cheap"
    else:
        lane = "frontier"
    reason = ",".join(reasons) if reasons else "default-local"
    return lane, reason, score


def normalize_lane(value: str) -> str:
    v = value.strip().lower()
    if v == "cloud":
        return "frontier"
    return v


def decide_route(headers: dict[str, str], data: dict[str, Any]) -> tuple[str, str]:
    override = normalize_lane(headers.get("x-route") or Cfg.force or "")
    if override in {"local", "cheap", "frontier"}:
        if override in {"cheap", "frontier"} and not cloud_api_key(headers):
            return "local", f"cloud-unavailable→local (override:{override})"
        return override, f"override:{override}"

    key = session_key(data)
    if key in _SESSION_ROUTE:
        return _SESSION_ROUTE[key], f"sticky:{_SESSION_ROUTE[key]}"

    user_text = last_user_text(data.get("messages") or [])
    lane, reason, _score = score_route(user_text, data)

    if lane in {"cheap", "frontier"} and not cloud_api_key(headers):
        return "local", f"cloud-unavailable→local ({reason})"

    _SESSION_ROUTE[key] = lane
    if len(_SESSION_ROUTE) > 256:
        _SESSION_ROUTE.pop(next(iter(_SESSION_ROUTE)))
    return lane, reason


def cloud_api_key(headers: dict[str, str]) -> str:
    key = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ROUTER_ANTHROPIC_API_KEY")
        or headers.get("x-api-key")
        or ""
    ).strip()
    if not key or key.lower() == "ollama":
        return ""
    return key


def rewrite_for_local(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out["model"] = Cfg.local_model
    thinking = out.get("thinking")
    if isinstance(thinking, dict):
        out["thinking"] = {"type": "disabled"}
    return out


def rewrite_for_hosted(data: dict[str, Any], model: str) -> dict[str, Any]:
    out = dict(data)
    out["model"] = model
    return out


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
                    "lanes": ["local", "cheap", "frontier"],
                    "local_upstream": Cfg.local_upstream,
                    "cloud_upstream": Cfg.cloud_upstream,
                    "local_model": Cfg.local_model,
                    "cheap_model": Cfg.cheap_model,
                    "frontier_model": Cfg.frontier_model,
                    "cloud_model": Cfg.frontier_model,
                    "listen": f"http://{Cfg.listen_host}:{Cfg.listen_port}",
                    "cloud_key_configured": bool(cloud_api_key({})),
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
                                f"Router → {Cfg.local_model} / "
                                f"{Cfg.cheap_model} / {Cfg.frontier_model}"
                            ),
                        },
                        {"id": Cfg.local_model, "object": "model", "owned_by": "ollama"},
                        {"id": Cfg.cheap_model, "object": "model", "owned_by": "anthropic"},
                        {"id": Cfg.frontier_model, "object": "model", "owned_by": "anthropic"},
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
        route, reason = decide_route(headers, data)
        if Cfg.log_routes:
            sys.stderr.write(f"[llm-router] route={route} reason={reason}\n")

        if route == "local":
            self._forward(Cfg.local_upstream, rewrite_for_local(data), auth_headers_local(headers))
            return

        key = cloud_api_key(headers)
        if not key:
            if Cfg.log_routes:
                sys.stderr.write("[llm-router] route=local reason=cloud-key-missing-late\n")
            self._forward(Cfg.local_upstream, rewrite_for_local(data), auth_headers_local(headers))
            return

        model = Cfg.cheap_model if route == "cheap" else Cfg.frontier_model
        self._forward(
            Cfg.cloud_upstream,
            rewrite_for_hosted(data, model),
            auth_headers_cloud(headers, key),
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

    def _forward(self, upstream: str, data: dict[str, Any], extra_headers: dict[str, str]) -> None:
        self.close_connection = True
        body = json.dumps(data).encode()
        parsed = urlparse(upstream)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "anthropic-version": self.headers.get("anthropic-version") or "2023-06-01",
        }
        headers.update(extra_headers)
        wants_stream = bool(data.get("stream"))
        try:
            if parsed.scheme == "https":
                conn: http.client.HTTPConnection = http.client.HTTPSConnection(host, port, timeout=600)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=600)
            conn.request("POST", self.path, body=body, headers=headers)
            resp = conn.getresponse()
            content_type = resp.getheader("Content-Type") or "application/json"
            if wants_stream:
                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            else:
                out = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(out)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(out)
            conn.close()
        except Exception as exc:  # noqa: BLE001
            msg = json.dumps(
                {
                    "type": "error",
                    "error": {"type": "api_error", "message": f"{exc} (upstream {upstream})"},
                }
            ).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[llm-router] " + (fmt % args) + "\n")


def auth_headers_local(_headers: dict[str, str]) -> dict[str, str]:
    return {"x-api-key": "ollama"}


def auth_headers_cloud(headers: dict[str, str], key: str) -> dict[str, str]:
    out = {"x-api-key": key, "anthropic-version": headers.get("anthropic-version") or "2023-06-01"}
    for k, v in headers.items():
        if k.startswith("anthropic-"):
            out[k] = v
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Route Claude Code across local Qwen, Haiku, and Sonnet."
    )
    parser.add_argument("--host", default=Cfg.listen_host)
    parser.add_argument("--port", type=int, default=Cfg.listen_port)
    parser.add_argument("--local-model", default=Cfg.local_model)
    parser.add_argument("--cheap-model", default=Cfg.cheap_model)
    parser.add_argument("--frontier-model", default=Cfg.frontier_model)
    parser.add_argument(
        "--cloud-model",
        default=None,
        help="Legacy alias for --frontier-model",
    )
    parser.add_argument("--classify", metavar="TEXT", help="Print route decision for TEXT and exit")
    args = parser.parse_args()

    Cfg.listen_host = args.host
    Cfg.listen_port = args.port
    Cfg.local_model = args.local_model
    Cfg.cheap_model = args.cheap_model
    Cfg.frontier_model = args.cloud_model or args.frontier_model
    Cfg.cloud_model = Cfg.frontier_model

    if args.classify is not None:
        route, reason, score = score_route(
            args.classify, {"messages": [{"role": "user", "content": args.classify}]}
        )
        print(json.dumps({"route": route, "reason": reason, "score": score}))
        return

    print(
        f"llm-router  http://{Cfg.listen_host}:{Cfg.listen_port}  "
        f"local={Cfg.local_model}  cheap={Cfg.cheap_model}  "
        f"frontier={Cfg.frontier_model}@{Cfg.cloud_upstream}",
        flush=True,
    )
    if not cloud_api_key({}):
        print("warning: no ANTHROPIC_API_KEY — cheap/frontier fall back to local", flush=True)
    try:
        ThreadingHTTPServer((Cfg.listen_host, Cfg.listen_port), Handler).serve_forever()
    except OSError as exc:
        sys.stderr.write(f"error: bind {Cfg.listen_host}:{Cfg.listen_port}: {exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
