"""Effort and thinking level helpers."""
from __future__ import annotations

import re
from typing import Any

from llm_router.config import Cfg
from llm_router.models import EFFORT_LEVELS


def apply_opt_in_lane(
    wanted: str, current: str, reasons: list[str]
) -> tuple[str, list[str]]:
    if wanted == "opus" and Cfg.disable_opus:
        reasons.append("opus-disabled→sonnet")
        return "sonnet", reasons
    if wanted == "fable" and Cfg.disable_fable:
        reasons.append("fable-disabled→sonnet")
        return "sonnet", reasons
    reasons.append(f"opt-in→{wanted}")
    return wanted, reasons


def effort_ask_flags(norm: str, lower: str) -> tuple[bool, bool]:
    asked_max = bool(
        re.search(r"\b(effort\s*[:=]?\s*max|maximum\s+effort|max\s+effort)\b", lower)
        or "effort max" in norm
    )
    asked_xhigh = bool(
        re.search(
            r"\b(effort\s*[:=]?\s*(xhigh|extra)|extra\s+effort|xhigh\s+effort)\b",
            lower,
        )
        or "effort extra" in norm
        or "effort xhigh" in norm
    )
    return asked_max, asked_xhigh


def normalize_effort(value: str) -> str | None:
    v = value.strip().lower()
    aliases = {
        "extra": "xhigh",
        "x-high": "xhigh",
        "med": "medium",
        "mid": "medium",
    }
    v = aliases.get(v, v)
    return v if v in EFFORT_LEVELS else None


def effort_thinking_for(
    lane: str, score: int, asked_max: bool = False, asked_xhigh: bool = False
) -> tuple[str | None, str]:
    """Defaults for a lane given severity score and optional ask flags."""
    if lane == "local":
        return None, "off"
    if lane == "haiku":
        return "low", "off"
    if lane == "sonnet":
        if score >= 5 or asked_max:
            return ("max" if asked_max else "xhigh"), "adaptive"
        if score >= 3 or asked_xhigh:
            return "xhigh" if asked_xhigh and score < 5 else "high", "adaptive"
        if asked_xhigh:
            return "xhigh", "adaptive"
        return "medium", "adaptive"
    if lane == "opus":
        if asked_max:
            return "max", "adaptive"
        if asked_xhigh:
            return "xhigh", "adaptive"
        return "high", "adaptive"
    if lane == "fable":
        if asked_max:
            return "max", "adaptive"
        return "xhigh", "adaptive"
    return "medium", "adaptive"


def merge_client_effort_thinking(
    data: dict[str, Any], effort: str | None, thinking_mode: str
) -> tuple[str | None, str]:
    """Honor client output_config.effort / thinking when already set."""
    oc = data.get("output_config")
    if isinstance(oc, dict) and oc.get("effort"):
        norm = normalize_effort(str(oc.get("effort")))
        if norm:
            effort = norm
    th = data.get("thinking")
    if isinstance(th, dict):
        ttype = str(th.get("type") or "").lower()
        if ttype == "disabled":
            thinking_mode = "off"
        elif ttype in {"enabled", "adaptive"}:
            thinking_mode = "adaptive"
    # API rejects thinking disabled at xhigh/max.
    if effort in {"xhigh", "max"} and thinking_mode == "off":
        thinking_mode = "adaptive"
    return effort, thinking_mode


def defaults_for_failover_lane(lane: str, severity: int) -> tuple[str | None, str]:
    """Recompute effort/thinking when cascading to a lower lane."""
    return effort_thinking_for(lane, severity if lane == "sonnet" else min(severity, 2))
