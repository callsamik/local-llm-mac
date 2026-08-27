"""Router configuration from environment variables."""
from __future__ import annotations

import os


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Cfg:
    local_upstream = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
    cloud_upstream = os.environ.get("ANTHROPIC_UPSTREAM", "https://api.anthropic.com").rstrip("/")
    local_model = os.environ.get("ROUTER_LOCAL_MODEL", "qwen-fast")
    haiku_model = os.environ.get(
        "ROUTER_HAIKU_MODEL",
        os.environ.get("ROUTER_CHEAP_MODEL", "claude-haiku-4-5"),
    )
    sonnet_model = os.environ.get(
        "ROUTER_SONNET_MODEL",
        os.environ.get(
            "ROUTER_FRONTIER_MODEL",
            os.environ.get("ROUTER_CLOUD_MODEL", "claude-sonnet-4-6"),
        ),
    )
    opus_model = os.environ.get("ROUTER_OPUS_MODEL", "claude-opus-5")
    fable_model = os.environ.get("ROUTER_FABLE_MODEL", "claude-fable-5")
    # Back-compat aliases
    cheap_model = haiku_model
    frontier_model = sonnet_model
    cloud_model = sonnet_model
    listen_host = os.environ.get("ROUTER_HOST", "127.0.0.1")
    listen_port = int(os.environ.get("ROUTER_PORT", "11437"))
    force = os.environ.get("ROUTER_FORCE", "").strip().lower()
    log_routes = os.environ.get("ROUTER_LOG", "1") != "0"
    # auto = local LLM only when heuristic is uncertain; always|never also supported
    llm_classify = os.environ.get("ROUTER_LLM_CLASSIFY", "auto").strip().lower()
    # Cascade on upstream failure (model missing / 429 / 5xx / connect)
    cascade = os.environ.get("ROUTER_CASCADE", "1") != "0"
    # Costly frontier lanes: off by default. When on, auto-scoring may assign them.
    enable_opus = _env_flag("ROUTER_ENABLE_OPUS", False) and not _env_flag(
        "ROUTER_DISABLE_OPUS", False
    )
    enable_fable = _env_flag("ROUTER_ENABLE_FABLE", False) and not _env_flag(
        "ROUTER_DISABLE_FABLE", False
    )
    # Back-compat aliases used by older checks / docs
    disable_opus = not enable_opus
    disable_fable = not enable_fable
    # Local LLM scorer timeout (seconds) when heuristics need help
    llm_classify_timeout = float(os.environ.get("ROUTER_LLM_CLASSIFY_TIMEOUT", "12"))
