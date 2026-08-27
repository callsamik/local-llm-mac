"""Composite route scorer combining heuristics and optional LLM refinement."""
from __future__ import annotations

import os
from typing import Any

from llm_router.config import Cfg
from llm_router.models import AUTO_LANES, RouteDecision
from llm_router.protocols import LlmScorerBackend, RouteScorer
from llm_router.scoring.effort import (
    apply_frontier_gates,
    apply_opt_in_lane,
    effort_ask_flags,
    effort_thinking_for,
    merge_client_effort_thinking,
    normalize_effort,
)
from llm_router.scoring.heuristic import HeuristicScorer
from llm_router.scoring.llm import OllamaLlmScorer, needs_llm_score


class CompositeScorer:
    """Heuristic scoring with optional local LLM refinement."""

    def __init__(
        self,
        heuristic: RouteScorer | None = None,
        llm: LlmScorerBackend | None = None,
    ) -> None:
        self._heuristic = heuristic or _HeuristicAdapter()
        self._llm = llm or OllamaLlmScorer()

    def score(self, user_text: str, data: dict[str, Any]) -> RouteDecision:
        _base, meta = self._heuristic.score_with_meta(user_text, data)

        lane = meta["lane"]
        score = meta["score"]
        reasons = list(meta["reasons"])
        opt_opus = meta["opt_opus"]
        opt_fable = meta["opt_fable"]
        norm = meta["norm"]
        lower = meta["lower"]
        opus_hard = meta["opus_hard"]
        fable_hard = meta["fable_hard"]

        want_llm = (not opt_opus and not opt_fable) and needs_llm_score(
            confident=meta["confident"],
            hard_hit=meta["hard_hit"],
            medium_hit=meta["medium_hit"],
            easy_hits=meta["easy_hits"],
            score=score,
            reasons=reasons,
            opus_hard=opus_hard,
            fable_hard=fable_hard,
        )
        if want_llm and not os.environ.get("ROUTER_CLASSIFY_OFFLINE"):
            reasons.append("llm-score:needed")
            llm = self._llm.score_route(user_text)
            if llm:
                llm_lane = str(llm.get("lane") or "").strip().lower()
                llm_lane = {"frontier": "sonnet", "cheap": "haiku"}.get(llm_lane, llm_lane)
                raw_score = llm.get("score")
                llm_score: int | None = None
                try:
                    if raw_score is not None:
                        llm_score = int(raw_score)
                except (TypeError, ValueError):
                    llm_score = None
                llm_effort = None
                if llm.get("effort") is not None:
                    llm_effort = normalize_effort(str(llm.get("effort")))

                allowed_llm = set(AUTO_LANES)
                if Cfg.enable_opus:
                    allowed_llm.add("opus")
                if Cfg.enable_fable:
                    allowed_llm.add("fable")

                if llm_lane in allowed_llm:
                    reasons.append(f"llm-score:lane={llm_lane}")
                    lane = llm_lane
                    if llm_score is not None:
                        score = max(-2, min(6, llm_score))
                        reasons.append(f"llm-score:score={score}")
                    else:
                        score = {
                            "local": 0,
                            "haiku": 1,
                            "sonnet": 2,
                            "opus": 4,
                            "fable": 6,
                        }[llm_lane]
                elif llm_lane in {"opus", "fable"}:
                    reasons.append(f"llm-score:clamped:{llm_lane}→sonnet")
                    lane = "sonnet"
                    score = max(score, 4 if llm_lane == "opus" else 6)
                    if llm_score is not None:
                        score = max(score, max(-2, min(6, llm_score)))
                else:
                    reasons.append("llm-score:bad-lane")

                if llm_effort:
                    reasons.append(f"llm-score:effort={llm_effort}")
                    data = dict(data)
                    oc = dict(data["output_config"]) if isinstance(data.get("output_config"), dict) else {}
                    if "effort" not in oc:
                        oc["effort"] = llm_effort
                        data["output_config"] = oc
            else:
                reasons.append("llm-score:fallback-heuristic")

        # Explicit ask phrases (still gated by enable flags).
        if opt_fable:
            lane, reasons = apply_opt_in_lane("fable", lane, reasons)
        elif opt_opus:
            lane, reasons = apply_opt_in_lane("opus", lane, reasons)
        else:
            # Category scores/phrases → opus/fable only when flags are on.
            lane, reasons = apply_frontier_gates(
                lane,
                score,
                opus_hard=opus_hard,
                fable_hard=fable_hard,
                reasons=reasons,
            )

        asked_max, asked_xhigh = effort_ask_flags(norm, lower)
        effort, thinking_mode = effort_thinking_for(lane, score, asked_max, asked_xhigh)
        effort, thinking_mode = merge_client_effort_thinking(data, effort, thinking_mode)

        reason = ",".join(reasons) if reasons else "default-local"
        return RouteDecision(lane, reason, score, effort, thinking_mode)


class _HeuristicAdapter:
    """Adapter exposing score_with_meta for CompositeScorer."""

    def __init__(self) -> None:
        self._inner = HeuristicScorer()

    def score(self, user_text: str, data: dict[str, Any]) -> RouteDecision:
        decision, _ = self._inner.score_with_meta(user_text, data)
        return decision

    def score_with_meta(self, user_text: str, data: dict[str, Any]) -> tuple[RouteDecision, dict[str, Any]]:
        return self._inner.score_with_meta(user_text, data)


_default_scorer: CompositeScorer | None = None


def _default_composite_scorer() -> CompositeScorer:
    global _default_scorer
    if _default_scorer is None:
        _default_scorer = CompositeScorer()
    return _default_scorer


def score_route(user_text: str, data: dict[str, Any]) -> RouteDecision:
    """Score into lanes + effort/thinking.

    Opus/fable are assigned from dedicated score/phrase categories only when
    ROUTER_ENABLE_OPUS / ROUTER_ENABLE_FABLE are on (default off).
    """
    return _default_composite_scorer().score(user_text, data)
