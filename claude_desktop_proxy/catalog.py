"""Advertised Claude model catalog for Desktop."""
from __future__ import annotations

from typing import Any

ADVERTISED: list[dict[str, Any]] = [
    {
        "id": "claude-sonnet-4-6",
        "display_name": "Qwen 3.8 27B (local)",
        "anthropic_family_tier": "sonnet",
        "is_family_default": True,
    },
    {
        "id": "claude-sonnet-4-5",
        "display_name": "Qwen 3.8 27B (local)",
        "anthropic_family_tier": "sonnet",
        "is_family_default": False,
    },
    {
        "id": "claude-sonnet-4-5-20250929",
        "display_name": "Qwen 3.8 27B (local)",
        "anthropic_family_tier": "sonnet",
        "is_family_default": False,
    },
    {
        "id": "claude-haiku-4-5",
        "display_name": "Qwen 3.8 27B (local, haiku slot)",
        "anthropic_family_tier": "haiku",
        "is_family_default": True,
    },
]

REWRITE_EXACT = {
    "sonnet",
    "opus",
    "haiku",
    "fable",
    "mythos",
    *(item["id"] for item in ADVERTISED),
}


def model_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "object": "model",
        "owned_by": "ollama",
        "display_name": item["display_name"],
        "anthropic_family_tier": item["anthropic_family_tier"],
        "is_family_default": item["is_family_default"],
        "context_length": 32768,
        "max_tokens": 8192,
        "type": "claude",
    }
