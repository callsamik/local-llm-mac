"""Core routing data models and lane constants."""
from __future__ import annotations

from dataclasses import dataclass

# Highest → lowest. Failover walks downward; local is last resort.
LANE_ORDER = ["fable", "opus", "sonnet", "haiku", "local"]
AUTO_LANES = {"local", "haiku", "sonnet"}
HOSTED_LANES = {"haiku", "sonnet", "opus", "fable"}
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


@dataclass
class RouteDecision:
    lane: str
    reason: str
    score: int
    effort: str | None = None  # low|medium|high|xhigh|max
    thinking: str = "off"  # off|adaptive
