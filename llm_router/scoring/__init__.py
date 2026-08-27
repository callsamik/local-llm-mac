"""Scoring subpackage."""

from llm_router.scoring.composite import CompositeScorer, score_route
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

__all__ = [
    "CompositeScorer",
    "score_route",
    "defaults_for_failover_lane",
    "effort_thinking_for",
    "merge_client_effort_thinking",
    "normalize_effort",
    "_parse_llm_score_payload",
    "needs_llm_score",
    "ollama_classify_lane",
    "ollama_score_route",
]
