"""Anthropic /v1/messages router across local and hosted Claude lanes."""
from __future__ import annotations

from llm_router.auth import (
    auth_headers_cloud,
    auth_headers_local,
    cloud_api_key,
    cloud_auth_ready,
    inbound_bearer_token,
    load_claude_cli_oauth_token,
)
from llm_router.cascade import (
    cascade_from,
    lane_allowed,
    model_for_lane,
    normalize_lane,
    should_failover_status,
)
from llm_router.catalog import (
    EASY_PATTERNS,
    EASY_PHRASES,
    FABLE_HARD_PHRASES,
    FABLE_PHRASES,
    HARD_PATTERNS,
    HARD_PHRASES,
    MEDIUM_PHRASES,
    MEDIUM_STACK,
    MEDIUM_VERBS,
    OPUS_HARD_PHRASES,
    OPUS_PHRASES,
    OPT_IN_FABLE,
    OPT_IN_OPUS,
)
from llm_router.config import Cfg
from llm_router.models import AUTO_LANES, EFFORT_LEVELS, HOSTED_LANES, LANE_ORDER, RouteDecision
from llm_router.rewrite import rewrite_for_hosted, rewrite_for_local
from llm_router.routing import decide_route
from llm_router.scoring import score_route
from llm_router.scoring.effort import (
    defaults_for_failover_lane,
    effort_thinking_for,
    merge_client_effort_thinking,
    normalize_effort,
)
from llm_router.scoring.llm import (
    _parse_llm_score_payload,
    needs_llm_score,
    ollama_classify_lane,
    ollama_score_route,
)
from llm_router.text import last_user_text, normalize_prompt, session_key

__all__ = [
    "Cfg",
    "RouteDecision",
    "LANE_ORDER",
    "AUTO_LANES",
    "HOSTED_LANES",
    "EFFORT_LEVELS",
    "HARD_PATTERNS",
    "MEDIUM_VERBS",
    "MEDIUM_STACK",
    "EASY_PATTERNS",
    "OPUS_HARD_PHRASES",
    "FABLE_HARD_PHRASES",
    "OPUS_PHRASES",
    "FABLE_PHRASES",
    "OPT_IN_OPUS",
    "OPT_IN_FABLE",
    "HARD_PHRASES",
    "MEDIUM_PHRASES",
    "EASY_PHRASES",
    "normalize_prompt",
    "last_user_text",
    "session_key",
    "score_route",
    "decide_route",
    "normalize_effort",
    "effort_thinking_for",
    "merge_client_effort_thinking",
    "defaults_for_failover_lane",
    "normalize_lane",
    "model_for_lane",
    "lane_allowed",
    "cascade_from",
    "should_failover_status",
    "rewrite_for_local",
    "rewrite_for_hosted",
    "cloud_api_key",
    "load_claude_cli_oauth_token",
    "inbound_bearer_token",
    "cloud_auth_ready",
    "auth_headers_local",
    "auth_headers_cloud",
    "needs_llm_score",
    "_parse_llm_score_payload",
    "ollama_score_route",
    "ollama_classify_lane",
]
