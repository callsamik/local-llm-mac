"""Text normalization and message extraction helpers."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def normalize_prompt(text: str) -> str:
    """Lowercase, expand light slang, collapse punctuation for phrase matching."""
    t = text.lower()
    replacements = {
        "what's": "what is",
        "whats": "what is",
        "where's": "where is",
        "wheres": "where is",
        "how's": "how is",
        "hows": "how is",
        "can't": "cannot",
        "wont": "will not",
        "won't": "will not",
        " i'm ": " i am ",
        " pls ": " please ",
        " plz ": " please ",
        " u ": " you ",
        " ur ": " your ",
        " n ": " and ",
        " w/ ": " with ",
        " w/o ": " without ",
    }
    for a, b in replacements.items():
        t = t.replace(a, b)
    t = re.sub(r"[^\w\s.+#-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def structural_signals(user_text: str, norm: str) -> tuple[int, list[str], bool, bool, bool]:
    """Return (score_delta, reasons, hardish, mediumish, easyish) from shape of the prompt."""
    delta = 0
    reasons: list[str] = []
    hardish = mediumish = easyish = False

    # Code fences / many paths → coding work (usually cheap unless also hard words).
    fence_count = user_text.count("```")
    path_hits = len(re.findall(r"[\w.-]+/(?:[\w.-]+/)+[\w.-]+", user_text))
    if fence_count >= 2 or path_hits >= 3:
        mediumish = True
        delta += 1
        reasons.append("struct:code-or-paths")

    # Short interrogative lookups.
    if re.match(r"^(what|where|which|who|whom)\b", norm) and len(norm.split()) <= 14:
        easyish = True
        delta -= 1
        reasons.append("struct:short-wh-question")

    # "why/how is this broken" without needing exact hard regex.
    if re.search(r"\b(why|how)\b.+\b(break|broke|broken|fail|fails|failing|wrong|bug)\b", norm):
        hardish = True
        delta += 2
        reasons.append("struct:why-how-failure")

    # Imperative coding without polite fluff.
    if re.match(
        r"^(add|fix|implement|create|write|update|refactor|wire|build|patch|remove|delete|rename)\b",
        norm,
    ):
        if re.match(r"^(rename|remove|delete)\b", norm) and re.search(
            r"\b(typo|comment|log|print|whitespace|nit)\b", norm
        ):
            easyish = True
            reasons.append("struct:trivial-imperative")
        elif re.match(r"^(rename)\b", norm) and len(norm.split()) <= 10:
            easyish = True
            reasons.append("struct:short-rename")
        else:
            mediumish = True
            delta += 1
            reasons.append("struct:coding-imperative")

    return delta, reasons, hardish, mediumish, easyish


def phrase_hits(norm: str, phrases: list[str], tag: str) -> list[str]:
    return [f"{tag}:{p}" for p in phrases if p in norm]


def last_user_text(messages: list[Any]) -> str:
    text_parts: list[str] = []
    for msg in reversed(messages or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text_parts.append(content)
            break
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(str(block.get("text") or ""))
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    # Mid tool-loop: do not reclassify from tool blobs.
                    return ""
            break
    return "\n".join(text_parts).strip()


def session_key(data: dict[str, Any]) -> str:
    msgs = data.get("messages") or []
    bits: list[str] = []
    for msg in msgs[:4]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role == "user" and isinstance(content, str):
            bits.append(content[:500])
        elif role == "user" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    bits.append(str(block.get("text") or "")[:500])
    raw = "||".join(bits) or json.dumps(data.get("system", ""))[:200]
    return hashlib.sha1(raw.encode()).hexdigest()[:16]
