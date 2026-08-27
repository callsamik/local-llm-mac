"""Route decision orchestration."""
from __future__ import annotations

from typing import Any

from llm_router.cascade import lane_allowed, normalize_lane
from llm_router.config import Cfg
from llm_router.models import HOSTED_LANES, RouteDecision
from llm_router.protocols import AuthProvider, RouteScorer, SessionStore
from llm_router.scoring.effort import effort_thinking_for, merge_client_effort_thinking
from llm_router.text import last_user_text, session_key


class RouteDecider:
    """Decide routing for an inbound request."""

    def __init__(
        self,
        scorer: RouteScorer,
        sessions: SessionStore,
        auth: AuthProvider,
    ) -> None:
        self._scorer = scorer
        self._sessions = sessions
        self._auth = auth

    def decide(self, headers: dict[str, str], data: dict[str, Any]) -> RouteDecision:
        override = normalize_lane(headers.get("x-route") or Cfg.force or "")
        if override in {"local", "haiku", "sonnet", "opus", "fable"}:
            if not lane_allowed(override):
                fallback = "sonnet"
                effort, thinking = effort_thinking_for(fallback, 4)
                effort, thinking = merge_client_effort_thinking(data, effort, thinking)
                return RouteDecision(
                    fallback,
                    f"{override}-disabled→{fallback}",
                    4,
                    effort,
                    thinking,
                )
            if override in HOSTED_LANES and not self._auth.cloud_auth_ready(headers):
                return RouteDecision(
                    "local",
                    f"cloud-unavailable→local (override:{override})",
                    0,
                    None,
                    "off",
                )
            score = {"local": 0, "haiku": 1, "sonnet": 2, "opus": 4, "fable": 6}[override]
            effort, thinking = effort_thinking_for(override, score)
            effort, thinking = merge_client_effort_thinking(data, effort, thinking)
            return RouteDecision(override, f"override:{override}", score, effort, thinking)

        key = session_key(data)
        sticky = self._sessions.get(key)
        if sticky is not None:
            return RouteDecision(
                sticky.lane,
                f"sticky:{sticky.lane}",
                sticky.score,
                sticky.effort,
                sticky.thinking,
            )

        user_text = last_user_text(data.get("messages") or [])
        decision = self._scorer.score(user_text, data)
        decision.lane = normalize_lane(decision.lane) or decision.lane

        if decision.lane in HOSTED_LANES and not self._auth.cloud_auth_ready(headers):
            return RouteDecision(
                "local",
                f"cloud-unavailable→local ({decision.reason})",
                decision.score,
                None,
                "off",
            )

        self._sessions.put(key, decision)
        return decision


def decide_route(headers: dict[str, str], data: dict[str, Any]) -> RouteDecision:
    """Module-level wrapper using default decider from composition."""
    from llm_router.composition import default_route_decider

    return default_route_decider().decide(headers, data)