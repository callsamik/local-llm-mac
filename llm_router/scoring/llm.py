"""Local LLM scoring via Ollama."""
from __future__ import annotations

import http.client
import json
import re
import sys
from typing import Any
from urllib.parse import urlparse

from llm_router.config import Cfg
from llm_router.scoring.effort import normalize_effort


def needs_llm_score(
    *,
    confident: bool,
    hard_hit: bool,
    medium_hit: bool,
    easy_hits: int,
    score: int,
    reasons: list[str],
    opus_hard: bool,
    fable_hard: bool,
) -> bool:
    """When True, ask local Qwen to refine lane + numeric score + effort."""
    mode = Cfg.llm_classify
    if mode in {"0", "never", "off", "false", "no"}:
        return False
    if mode in {"always", "1", "true", "yes", "on"}:
        return True
    # auto (default): call local model when heuristics are weak or conflict.
    if not confident:
        return True
    if hard_hit and easy_hits > 0:
        return True
    if medium_hit and easy_hits > 0:
        return True
    if hard_hit and medium_hit and score <= 3 and not opus_hard and not fable_hard:
        return True
    # Only structural / length cues — no catalog phrase match.
    catalogish = any(
        r.startswith(
            (
                "hard:",
                "medium:",
                "easy:",
                "hard-phrase:",
                "medium-phrase:",
                "easy-phrase:",
                "opus-hard:",
                "fable-hard:",
                "stack:",
            )
        )
        for r in reasons
    )
    if reasons and not catalogish:
        return True
    # Borderline severity: light hard without strong opus/fable cues → refine effort.
    if hard_hit and score in {2, 3} and not opus_hard and not fable_hard:
        return True
    return False


def _parse_llm_score_payload(content: str) -> dict[str, Any] | None:
    """Extract {lane, score, effort?} from model text (JSON preferred)."""
    text = (content or "").strip()
    if not text:
        return None
    # Prefer fenced or raw JSON object.
    blob = text
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if m:
        blob = m.group(0)
    try:
        data = json.loads(blob)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Fallback: bare lane word (+ optional score/effort tokens).
    lower = text.lower()
    lane = None
    for name in ("sonnet", "haiku", "local", "frontier", "cheap", "opus", "fable"):
        if re.search(rf"\b{name}\b", lower):
            lane = {"frontier": "sonnet", "cheap": "haiku"}.get(name, name)
            break
    if not lane:
        return None
    score = None
    sm = re.search(r"\bscore\s*[:=]\s*(-?\d+)\b", lower)
    if sm:
        score = int(sm.group(1))
    effort = None
    em = re.search(r"\beffort\s*[:=]\s*(low|medium|high|xhigh|extra|max)\b", lower)
    if em:
        effort = normalize_effort(em.group(1))
    out: dict[str, Any] = {"lane": lane}
    if score is not None:
        out["score"] = score
    if effort:
        out["effort"] = effort
    return out


class OllamaLlmScorer:
    """Ask local Ollama for lane + numeric score (+ optional effort)."""

    def score_route(self, user_text: str) -> dict[str, Any] | None:
        if Cfg.llm_classify in {"0", "never", "off", "false", "no"}:
            return None
        payload = {
            "model": Cfg.local_model,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 64},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You score coding tasks for a router. Reply with ONLY compact JSON:\n"
                        '{"lane":"local|haiku|sonnet","score":<int>,"effort":"low|medium|high|xhigh|max"|null}\n'
                        "Rules:\n"
                        "- lane local: lookup/rename/typo/explain (score <= 0, effort null)\n"
                        "- lane haiku: normal implement/fix/test/refactor (score 1, effort low)\n"
                        "- lane sonnet: harder bugs/architecture/security/incidents "
                        "(score 2 medium, 3-4 high, 5-6 xhigh)\n"
                        "- Never choose opus or fable.\n"
                        "- score is an integer from -2 to 6 reflecting difficulty.\n"
                        "- No markdown, no prose."
                    ),
                },
                {"role": "user", "content": user_text[:4000]},
            ],
        }
        try:
            parsed = urlparse(Cfg.local_upstream)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 11434
            body = json.dumps(payload).encode()
            timeout = max(3.0, float(Cfg.llm_classify_timeout))
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
            conn.request(
                "POST",
                "/api/chat",
                body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
            if resp.status >= 400:
                if Cfg.log_routes:
                    sys.stderr.write(
                        f"[llm-router] llm-score http-{resp.status} model={Cfg.local_model}\n"
                    )
                return None
            data = json.loads(raw)
            content = ""
            msg = data.get("message") or {}
            if isinstance(msg, dict):
                content = str(msg.get("content") or "")
            parsed_score = _parse_llm_score_payload(content)
            if not parsed_score:
                if Cfg.log_routes:
                    sys.stderr.write(
                        f"[llm-router] llm-score parse-miss raw={content[:120]!r}\n"
                    )
                return None
            return parsed_score
        except Exception as exc:  # noqa: BLE001
            if Cfg.log_routes:
                sys.stderr.write(f"[llm-router] llm-score error={exc}\n")
            return None


def ollama_score_route(user_text: str) -> dict[str, Any] | None:
    """Module-level wrapper using default Ollama scorer."""
    return OllamaLlmScorer().score_route(user_text)


def ollama_classify_lane(user_text: str) -> str | None:
    """Back-compat: lane-only wrapper around ollama_score_route."""
    result = ollama_score_route(user_text)
    if not result:
        return None
    lane = str(result.get("lane") or "").strip().lower()
    return lane or None
