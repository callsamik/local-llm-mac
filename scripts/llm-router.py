#!/usr/bin/env python3
"""Thin shim — delegates to llm_router package."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# SourceFileLoader("llm_router", shim) names this module llm_router and shadows the
# real package. Drop the in-flight shim entry so `import llm_router` resolves to
# the package under _ROOT/llm_router/.
_shim = sys.modules.get(__name__)
if __name__ == "llm_router" and str(_ROOT / "scripts" / "llm-router.py") == str(Path(__file__).resolve()):
    del sys.modules["llm_router"]

from llm_router import (  # noqa: E402
    AUTO_LANES,
    Cfg,
    EFFORT_LEVELS,
    HOSTED_LANES,
    LANE_ORDER,
    RouteDecision,
    _parse_llm_score_payload,
    auth_headers_cloud,
    auth_headers_local,
    cascade_from,
    cloud_api_key,
    cloud_auth_ready,
    decide_route,
    effort_thinking_for,
    inbound_bearer_token,
    lane_allowed,
    load_claude_cli_oauth_token,
    model_for_lane,
    needs_llm_score,
    normalize_effort,
    normalize_lane,
    rewrite_for_hosted,
    rewrite_for_local,
    score_route,
    should_failover_status,
)
from llm_router.cli import main  # noqa: E402

__all__ = [
    "Cfg",
    "RouteDecision",
    "LANE_ORDER",
    "AUTO_LANES",
    "HOSTED_LANES",
    "EFFORT_LEVELS",
    "cascade_from",
    "should_failover_status",
    "normalize_effort",
    "effort_thinking_for",
    "score_route",
    "rewrite_for_hosted",
    "needs_llm_score",
    "_parse_llm_score_payload",
    "decide_route",
    "normalize_lane",
    "model_for_lane",
    "lane_allowed",
    "rewrite_for_local",
    "cloud_api_key",
    "load_claude_cli_oauth_token",
    "inbound_bearer_token",
    "cloud_auth_ready",
    "auth_headers_local",
    "auth_headers_cloud",
    "main",
]

if _shim is not None and __name__ == "llm_router":
    for _name in __all__:
        setattr(_shim, _name, globals()[_name])
    sys.modules["llm_router"] = _shim

if __name__ == "__main__":
    main()
