"""Request payload rewriting for local and hosted upstreams."""
from __future__ import annotations

from typing import Any

from llm_router.config import Cfg
from llm_router.scoring.effort import merge_client_effort_thinking


def rewrite_for_local(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out["model"] = Cfg.local_model
    # Drop Anthropic-style thinking blocks — Ollama uses its own `think` flag.
    # Do not force think off for 14B (that workaround was for 27B quirks).
    out.pop("thinking", None)
    mode = Cfg.local_think
    if mode in {"0", "false", "off", "never", "no"}:
        out["think"] = False
    elif mode in {"1", "true", "on", "always", "yes"}:
        out["think"] = True
    # auto / unset: leave model default (no think field)
    # Local Ollama path does not use Anthropic effort.
    if "output_config" in out:
        oc = dict(out["output_config"]) if isinstance(out["output_config"], dict) else {}
        oc.pop("effort", None)
        if oc:
            out["output_config"] = oc
        else:
            out.pop("output_config", None)
    return out


def rewrite_for_hosted(
    data: dict[str, Any],
    model: str,
    effort: str | None = None,
    thinking_mode: str = "adaptive",
) -> dict[str, Any]:
    out = dict(data)
    out["model"] = model
    effort, thinking_mode = merge_client_effort_thinking(out, effort, thinking_mode)

    if effort:
        oc = dict(out["output_config"]) if isinstance(out.get("output_config"), dict) else {}
        if "effort" not in oc:
            oc["effort"] = effort
        out["output_config"] = oc

    existing = out.get("thinking")
    if not (isinstance(existing, dict) and existing.get("type")):
        if thinking_mode == "off":
            out["thinking"] = {"type": "disabled"}
        else:
            out["thinking"] = {"type": "adaptive"}
    elif (
        isinstance(existing, dict)
        and str(existing.get("type")).lower() == "disabled"
        and effort in {"xhigh", "max"}
    ):
        out["thinking"] = {"type": "adaptive"}
    return out
