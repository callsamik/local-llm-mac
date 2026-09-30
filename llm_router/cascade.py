"""Cascade failover and lane normalization."""
from __future__ import annotations

import json

from llm_router.config import Cfg
from llm_router.models import LANE_ORDER, LOCAL_LANES


def normalize_lane(value: str) -> str:
    v = value.strip().lower()
    aliases = {
        "cloud": "sonnet",
        "frontier": "sonnet",
        "cheap": "haiku",
        "r1": "reason",
        "deepseek": "reason",
        "local-reason": "reason",
        "auto": "",
    }
    return aliases.get(v, v)


def model_for_lane(lane: str) -> str:
    return {
        "local": Cfg.local_model,
        "reason": Cfg.reason_model,
        "haiku": Cfg.haiku_model,
        "sonnet": Cfg.sonnet_model,
        "opus": Cfg.opus_model,
        "fable": Cfg.fable_model,
        # legacy
        "cheap": Cfg.haiku_model,
        "frontier": Cfg.sonnet_model,
        "cloud": Cfg.sonnet_model,
    }.get(lane, Cfg.sonnet_model)


def lane_allowed(lane: str) -> bool:
    if lane == "opus" and not Cfg.enable_opus:
        return False
    if lane == "fable" and not Cfg.enable_fable:
        return False
    return True


def cascade_from(lane: str) -> list[str]:
    """Lanes to try, starting at selected tier down to local (skip disabled)."""
    lane = normalize_lane(lane) or "sonnet"
    if lane not in LANE_ORDER:
        lane = "sonnet"
    idx = LANE_ORDER.index(lane)
    out: list[str] = []
    for candidate in LANE_ORDER[idx:]:
        if not lane_allowed(candidate):
            continue
        out.append(candidate)
    return out or ["local"]


def local_fallback_lane(lane: str) -> str:
    """Local lane to use when hosted Claude is unavailable.

    Hard prompts (sonnet and above) go to the reason lane; haiku work to qwen-fast.
    """
    lane = normalize_lane(lane) or "local"
    if lane in LOCAL_LANES:
        return lane
    return "local" if lane == "haiku" else "reason"


def should_failover_status(status: int, body: bytes) -> bool:
    if status in {404, 429, 500, 502, 503, 529}:
        return True
    if status == 400:
        try:
            err = json.loads(body)
            msg = str((err.get("error") or {}).get("message") or "").lower()
            typ = str((err.get("error") or {}).get("type") or "").lower()
            if "not_found" in typ or (
                "model" in msg and ("not found" in msg or "invalid" in msg)
            ):
                return True
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    return False
