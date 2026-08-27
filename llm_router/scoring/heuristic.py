"""Heuristic route scoring."""
from __future__ import annotations

import re
from typing import Any

from llm_router.catalog import (
    EASY_PATTERNS,
    EASY_PHRASES,
    FABLE_HARD_PHRASES,
    HARD_PATTERNS,
    HARD_PHRASES,
    MEDIUM_PHRASES,
    MEDIUM_STACK,
    MEDIUM_VERBS,
    OPUS_HARD_PHRASES,
    OPT_IN_FABLE,
    OPT_IN_OPUS,
)
from llm_router.models import RouteDecision
from llm_router.text import normalize_prompt, phrase_hits, structural_signals


class HeuristicScorer:
    """Score prompts using regex/phrase heuristics only."""

    def score(self, user_text: str, data: dict[str, Any]) -> RouteDecision:
        decision, _ = self.score_with_meta(user_text, data)
        return decision

    def score_with_meta(
        self, user_text: str, data: dict[str, Any]
    ) -> tuple[RouteDecision, dict[str, Any]]:
        score = 0
        reasons: list[str] = []
        lower = user_text.lower()
        norm = normalize_prompt(user_text)

        if not user_text:
            return RouteDecision("local", "empty-user-sticky-candidate", 0, None, "off")

        hard_hit = False
        for pat in HARD_PATTERNS:
            if re.search(pat, lower, re.I):
                hard_hit = True
                score += 2
                reasons.append(f"hard:{pat}")

        medium_hit = False
        for pat in MEDIUM_VERBS:
            if re.search(pat, lower, re.I):
                medium_hit = True
                reasons.append(f"medium:{pat}")
        if medium_hit:
            score += 1
            for pat in MEDIUM_STACK:
                if re.search(pat, lower, re.I):
                    reasons.append(f"stack:{pat}")

        easy_hits = 0
        for pat in EASY_PATTERNS:
            if re.search(pat, lower, re.I):
                easy_hits += 1
                reasons.append(f"easy:{pat}")
        score -= min(easy_hits, 2)

        hard_phrases = phrase_hits(norm, HARD_PHRASES, "hard-phrase")
        if hard_phrases:
            hard_hit = True
            score += 2
            reasons.extend(hard_phrases)

        medium_phrases = phrase_hits(norm, MEDIUM_PHRASES, "medium-phrase")
        if medium_phrases:
            medium_hit = True
            score += 1
            reasons.extend(medium_phrases)

        easy_phrases = phrase_hits(norm, EASY_PHRASES, "easy-phrase")
        if easy_phrases:
            easy_hits += len(easy_phrases)
            score -= min(len(easy_phrases), 1)
            reasons.extend(easy_phrases)

        delta, struct_reasons, hardish, mediumish, easyish = structural_signals(user_text, norm)
        score += delta
        reasons.extend(struct_reasons)
        hard_hit = hard_hit or hardish
        medium_hit = medium_hit or mediumish
        if easyish:
            easy_hits += 1

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

        if re.search(r"reasoning[_\s-]?effort\s*[:=]\s*(high|xhigh|extra|max)", lower):
            score += 2
            reasons.append("effort-high")

        opus_hard = phrase_hits(norm, OPUS_HARD_PHRASES, "opus-hard")
        fable_hard = phrase_hits(norm, FABLE_HARD_PHRASES, "fable-hard")
        if opus_hard:
            reasons.extend(opus_hard)
            score = max(score, 4)
            hard_hit = True
        if fable_hard:
            reasons.extend(fable_hard)
            score = max(score, 6)
            hard_hit = True

        opt_opus = phrase_hits(norm, OPT_IN_OPUS, "opt-in-opus")
        opt_fable = phrase_hits(norm, OPT_IN_FABLE, "opt-in-fable")
        if opt_opus:
            reasons.extend(opt_opus)
        if opt_fable:
            reasons.extend(opt_fable)

        # Auto ladder: local / haiku / sonnet only.
        if hard_hit:
            lane = "sonnet"
            score = max(score, 2)
            confident = True
        elif medium_hit:
            lane = "haiku"
            score = max(score, 1)
            confident = True
        elif easy_hits > 0 and score <= 0:
            lane = "local"
            confident = True
        elif score <= 0:
            lane = "local"
            confident = False
        elif score == 1:
            lane = "haiku"
            confident = True
        else:
            lane = "sonnet"
            score = max(score, 2)
            confident = True

        meta = {
            "confident": confident,
            "hard_hit": hard_hit,
            "medium_hit": medium_hit,
            "easy_hits": easy_hits,
            "reasons": reasons,
            "opus_hard": bool(opus_hard),
            "fable_hard": bool(fable_hard),
            "opt_opus": opt_opus,
            "opt_fable": opt_fable,
            "norm": norm,
            "lower": lower,
            "lane": lane,
            "score": score,
        }
        decision = RouteDecision(
            lane,
            ",".join(reasons) if reasons else "default-local",
            score,
            None,
            "off",
        )
        return decision, meta
