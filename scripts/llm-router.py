#!/usr/bin/env python3
"""Route Anthropic /v1/messages across local / cheap / frontier.

local    → Ollama qwen-fast (easy/medium happy path)
cheap    → Anthropic Haiku
frontier → Anthropic Sonnet

Overrides:
  x-route / ROUTER_FORCE = local|cheap|frontier|cloud|auto
  (cloud is a legacy alias for frontier)

Claude Code: point ANTHROPIC_BASE_URL at this proxy (default :11437).
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


class Cfg:
    local_upstream = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
    cloud_upstream = os.environ.get("ANTHROPIC_UPSTREAM", "https://api.anthropic.com").rstrip("/")
    local_model = os.environ.get("ROUTER_LOCAL_MODEL", "qwen-fast")
    cheap_model = os.environ.get("ROUTER_CHEAP_MODEL", "claude-haiku-4-5")
    frontier_model = os.environ.get(
        "ROUTER_FRONTIER_MODEL",
        os.environ.get("ROUTER_CLOUD_MODEL", "claude-sonnet-4-6"),
    )
    # Back-compat alias
    cloud_model = frontier_model
    listen_host = os.environ.get("ROUTER_HOST", "127.0.0.1")
    listen_port = int(os.environ.get("ROUTER_PORT", "11437"))
    force = os.environ.get("ROUTER_FORCE", "").strip().lower()
    log_routes = os.environ.get("ROUTER_LOG", "1") != "0"
    # auto = local LLM only when heuristic is uncertain; always|never also supported
    llm_classify = os.environ.get("ROUTER_LLM_CLASSIFY", "auto").strip().lower()


# Sticky route per conversation fingerprint so tool loops stay on one backend.
_SESSION_ROUTE: dict[str, str] = {}

HARD_PATTERNS = [
    # Architecture / system design
    r"\barchitect(ure|ing)?\b",
    r"\bsystem\s+design\b",
    r"\bhigh[- ]level\s+design\b",
    r"\bhld\b",
    r"\bdesign\s+doc\b",
    r"\badr\b",
    r"\btechnical\s+design\b",
    r"\bdomain\s+model\b",
    r"\bbounded\s+context\b",
    r"\bevent[- ]driven\b",
    r"\bmicroservice(s)?\b",
    r"\bmulti[- ]service\b",
    r"\bcross[- ]cutting\b",
    r"\bdistributed\s+system\b",
    r"\bcap\s+theorem\b",
    r"\bconsistency\s+model\b",
    r"\bsaga\s+pattern\b",
    r"\bcqrs\b",
    r"\bevent\s+sourcing\b",
    # Large refactors / migrations
    r"\brefactors?\b.*\b(entire|whole|across|system|codebase|monolith)\b",
    r"\b(entire|whole)\s+(codebase|module|service)\b.*\brefactor",
    r"\bmigrat(e|ion)\b",
    r"\bbackfill\b",
    r"\bschema\s+migration\b",
    r"\bzero[- ]downtime\b",
    r"\brolling\s+(deploy|upgrade)\b",
    r"\bstrangler\b",
    r"\blegacy\s+rewrite\b",
    # Concurrency / reliability
    r"\brace\s*condition\b",
    r"\bdeadlock\b",
    r"\blivelock\b",
    r"\bheisenbug\b",
    r"\bflaky\b",
    r"\bintermittent\s+(fail|failure|bug|test)\b",
    r"\bnon[- ]deterministic\b",
    r"\bthread[- ]safe(ty)?\b",
    r"\bconcurrency\s+bug\b",
    r"\bmemory\s+leak\b",
    r"\bgoroutine\s+leak\b",
    r"\bresource\s+leak\b",
    # Incidents / production
    r"\bproduction\s+(outage|incident|sev|down|p0|p1)\b",
    r"\bsev[- ]?[0-2]\b",
    r"\bp[01]\b",
    r"\bpostmortem\b",
    r"\broot\s+cause\b",
    r"\brca\b",
    r"\bincident\s+response\b",
    r"\bon[- ]call\b",
    r"\bpager(duty)?\b",
    # Security
    r"\bsecurity\s+audit\b",
    r"\bthreat\s+model\b",
    r"\bpen(etration)?\s+test\b",
    r"\bvulnerabilit(y|ies)\b",
    r"\bcve[- ]?\d",
    r"\bauth(entication|orization)?\s+(bypass|flaw|hole)\b",
    r"\binjection\s+attack\b",
    r"\bxss\b",
    r"\bcsrf\b",
    r"\bssrf\b",
    r"\brce\b",
    r"\bprivilege\s+escalat",
    r"\bsecrets?\s+leak\b",
    r"\bcompromised\s+(key|token|credential)\b",
    # Performance / deep analysis
    r"\bdeep\s+dive\b",
    r"\bperformance\s+profil",
    r"\bhot\s+path\b",
    r"\blatency\s+(regress|spike|p99|p95)\b",
    r"\bthroughput\b",
    r"\bflame\s*graph\b",
    r"\bo(ut)?\s*of\s*memory\b",
    r"\boom\b",
    r"\bcpu\s+bound\b",
    r"\bgc\s+pause\b",
    # Hard reasoning asks
    r"\breasoning_effort\b.*\b(high|xhigh)\b",
    r"\bthink\s+hard\b",
    r"\bthink\s+step[- ]by[- ]step\b",
    r"\bcomplex\s+bug\b",
    r"\bsubtle\s+bug\b",
    r"\bhard\s+(problem|bug|issue)\b",
    r"\bnon[- ]trivial\b",
    r"\binvestigate\s+(why|how|the)\b",
    r"\bwhy\s+does\s+this\s+(fail|break|flake)\b",
    r"\bcompare\s+trade[- ]?offs?\b",
    r"\btrade[- ]?off\s+analysis\b",
    r"\bprove\s+(correctness|safety)\b",
    r"\bformal\s+verif",
    r"\bconsensus\s+algorithm\b",
    r"\bpaxos\b",
    r"\braft\b",
]

MEDIUM_VERBS = [
    r"\bimplement\b",
    r"\bscaffold\b",
    r"\bwire\s+up\b",
    r"\badd\s+(?:an?\s+)?(?:[\w.-]+\s+){0,4}(feature|test|tests|endpoint|handler|component|route|api|hook|middleware|guard|dto|schema|migration|button|page|screen|form|modal|dialog)\b",
    r"\badd\s+(?:an?\s+)?(?:[\w.-]+\s+){0,4}unit\s+test\b",
    r"\bwrite\s+(?:an?\s+)?(?:[\w.-]+\s+){0,3}(test|tests|spec|specs|function|method|class|module|script)\b",
    r"\bgenerate\s+(?:an?\s+)?(?:[\w.-]+\s+){0,3}(test|boilerplate|stub|mock)\b",
    r"\bbuild\s+(?:an?\s+)?(?:[\w.-]+\s+){0,3}(feature|component|endpoint|page|api|service|module)\b",
    r"\bcreate\s+(?:an?\s+)?(?:[\w.-]+\s+){0,3}(feature|component|endpoint|page|api|service|module|test|tests|class|function|pytest|jest|vitest)\b",
    r"\bfix\s+(the\s+)?(bug|issue|error|failure|failing\s+test|npe|null\s*pointer|type\s*error|crash)\b",
    r"\bpatch\s+(the\s+)?(bug|issue|error|handler|endpoint)\b",
    r"\baddress\s+(the\s+)?(bug|issue|todo|failing)\b",
    r"\bupdate\s+(the\s+)?(code|logic|handler|endpoint|component|schema|deps|dependencies)\b",
    r"\bchange\s+(the\s+)?(behavior|logic|api|schema|implementation)\b",
    r"\bmodify\s+(the\s+)?(code|handler|component|function|method)\b",
    r"\bedit\s+(the\s+)?(file|component|function|handler)\b",
    r"\breplace\s+(the\s+)?(implementation|handler|component)\b",
    r"\bconvert\s+(to|into)\b",
    r"\bport\s+(to|from)\b",
    r"\bunit\s+test\b",
    r"\bintegration\s+test\b",
    r"\be2e\b",
    r"\bend[- ]to[- ]end\b",
    r"\bsnapshot\s+test\b",
    r"\brefactor\b",
    r"\bextract\b",
    r"\binline\b",
    r"\bclean\s+up\b",
    r"\boptimize\b",
    r"\bspeed\s+up\b",
    r"\benhance\b",
    r"\bintegrate\b",
    r"\bhook\s+into\b",
    r"\bset\s+up\b",
    r"\bsetup\b",
    r"\bconfig(ure)?\b",
    r"\bdeploy\b",
    r"\brollback\b",
    r"\bvalidate\b",
    r"\bsanitize\b",
    r"\bserialize\b",
    r"\bdeserialize\b",
]

# Stack/tech cues only count when a medium verb also matched.
MEDIUM_STACK = [
    r"\bcoverage\b",
    r"\bjest\b",
    r"\bpytest\b",
    r"\bvitest\b",
    r"\bplaywright\b",
    r"\bcypress\b",
    r"\bdry\b",
    r"\bapi\s+client\b",
    r"\bcrud\b",
    r"\bendpoint\b",
    r"\bcontroller\b",
    r"\bservice\s+layer\b",
    r"\brepository\b",
    r"\bprisma\b",
    r"\btypeorm\b",
    r"\bsqlalchemy\b",
    r"\bdjango\b",
    r"\bflask\b",
    r"\bfastapi\b",
    r"\bexpress\b",
    r"\bnext\.?js\b",
    r"\bsvelte\b",
    r"\btypescript\b",
    r"\beslint\b",
    r"\bprettier\b",
    r"\bgithub\s+actions?\b",
    r"\bdocker(file)?\b",
    r"\bkubernetes\b",
    r"\bk8s\b",
    r"\bhelm\b",
    r"\bterraform\b",
    r"\bgraphql\b",
    r"\brest\s+api\b",
    r"\bwebsocket\b",
    r"\boauth\b",
    r"\bjwt\b",
    r"\brbac\b",
    r"\bi18n\b",
    r"\blocalization\b",
    r"\ba11y\b",
    r"\baccessib(le|ility)\b",
    r"\bresponsiv(e|eness)\b",
    r"\btailwind\b",
    r"\bstyling\b",
    r"\bfrontend\b",
    r"\bbackend\b",
    r"\bfull[- ]?stack\b",
]

EASY_PATTERNS = [
    # Lookups / navigation
    r"\brename\b",
    r"\btypo\b",
    r"\bspelling\b",
    r"\bexplain\b",
    r"\bwhat\s+(is|does|are|was|were)\b",
    r"\bwhere\s+(is|are|was|were)\b",
    r"\bwhich\s+file\b",
    r"\bwho\s+(owns|wrote|calls)\b",
    r"\bhow\s+do\s+i\s+run\b",
    r"\bshow\s+me\b",
    r"\bfind\s+(the\s+)?(file|function|class|symbol|definition)\b",
    r"\bgo\s+to\b",
    r"\bopen\s+(the\s+)?file\b",
    r"\blist\s+(the\s+)?(files?|dirs?|directories|endpoints|routes|scripts)\b",
    r"\bls\b",
    r"\btree\b",
    r"\bpwd\b",
    r"\bprint\s+(the\s+)?(path|env|version)\b",
    # Light docs / formatting
    r"\bsummarize\b",
    r"\btldr\b",
    r"\beli5\b",
    r"\bformat\b",
    r"\bindent\b",
    r"\bwhitespace\b",
    r"\bcomment\b",
    r"\bdocstring\b",
    r"\bjsdoc\b",
    r"\bjavadoc\b",
    r"\breadme\b",
    r"\bchangelog\b",
    r"\btranslate\b",
    # Trivial / greeting / tiny edits
    r"\bsimple\b",
    r"\btrivial\b",
    r"\bquick\b",
    r"\bminor\b",
    r"\btiny\b",
    r"\bsmall\s+(change|edit|tweak)\b",
    r"\bping\b",
    r"\bhello\b",
    r"\bhi\b",
    r"\bthanks\b",
    r"\bthank\s+you\b",
    r"\bboilerplate\b",
    r"\bstub\b",
    r"\bnoop\b",
    r"\badd\s+a\s+(log|print|comment|todo|note)\b",
    r"\bremove\s+a\s+(log|print|comment|todo|note)\b",
    r"\bdelete\s+(the\s+)?(comment|log|print)\b",
    r"\bcapitalize\b",
    r"\blowercase\b",
    r"\buppercase\b",
    r"\btrim\b",
    r"\bsort\s+(the\s+)?(imports?|keys?)\b",
    r"\balphabetize\b",
    r"\bwrap\s+in\s+try\b",
    r"\badd\s+type\s+hint\b",
    r"\badd\s+types?\b",
    r"\bexport\s+(the\s+)?(type|interface|const)\b",
    r"\bimport\s+(path|statement)\b",
    r"\bfix\s+(the\s+)?(import|typo|indent|spacing|lint)\b",
]



# Informal / paraphrased phrases (substring match on normalized text).
HARD_PHRASES = [
    "figure out why", "dig into why", "dig into how", "get to the bottom",
    "whats going wrong", "what's going wrong", "what is going wrong",
    "keeps failing intermittently", "fails randomly", "only fails sometimes",
    "make it scale", "needs to scale", "under load", "p99 latency",
    "security review", "lock down auth", "is this secure", "can this be exploited",
    "redesign the system", "rethink the architecture", "split into services",
    "data consistency", "eventual consistency", "exactly once", "at least once",
    "production is down", "site is down", "customers are blocked", "urgent outage",
    "racey", "heisenbug", "flakes in ci", "flake in ci", "ci is flaky",
    "memory keeps growing", "leaking memory", "oom killer",
    "tradeoffs between", "trade offs between", "pros and cons of adopting",
]

MEDIUM_PHRASES = [
    "can you add", "could you add", "please add", "pls add",
    "can you make", "could you make", "please make", "pls make",
    "can you fix", "could you fix", "please fix", "pls fix",
    "can you write", "could you write", "please write",
    "can you implement", "could you implement", "please implement",
    "whip up", "knock out a", "put together a", "throw together",
    "hook this up", "hook it up", "plug this in", "plug it in",
    "make a page", "make a form", "make a component", "make an endpoint",
    "make a test", "add tests for", "cover this with tests",
    "ship a", "land a pr for", "open a pr for",
    "update the logic", "tweak the behavior", "adjust the handler",
    "get this working", "make it work", "make this work",
    "drop in a", "slot in a",
]

EASY_PHRASES = [
    "what does this do", "whats this", "what's this", "what is this",
    "where does this live", "where is this defined", "point me to",
    "just wondering", "quick question", "one liner", "one-liner",
    "remind me", "refresh my memory", "in plain english", "in plain english",
    "too long didnt read", "too long didn't read",
    "say hi", "you there", "are you there",
    "fix spelling", "spelling mistake", "naming nit", "nit:",
]


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


def ollama_classify_lane(user_text: str) -> str | None:
    """Ask local Ollama for a one-word lane when heuristics are uncertain."""
    if Cfg.llm_classify in {"0", "never", "off", "false", "no"}:
        return None
    payload = {
        "model": Cfg.local_model,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 8},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify the coding task difficulty for a router. "
                    "Reply with exactly one word: local, cheap, or frontier. "
                    "local=lookup/rename/typo/explain. "
                    "cheap=normal implement/fix/test/refactor. "
                    "frontier=architecture/security/incident/race/deep reasoning."
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
        conn = http.client.HTTPConnection(host, port, timeout=8)
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
            return None
        data = json.loads(raw)
        content = ""
        msg = data.get("message") or {}
        if isinstance(msg, dict):
            content = str(msg.get("content") or "")
        content = content.strip().lower()
        for lane in ("frontier", "cheap", "local"):
            if re.search(rf"\b{lane}\b", content):
                return lane
    except Exception:  # noqa: BLE001
        return None
    return None



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


def score_route(user_text: str, data: dict[str, Any]) -> tuple[str, str, int]:
    """Return (lane, reason, score).

    Layers: regex catalogs → informal phrases → structural cues → optional local LLM.
    """
    score = 0
    reasons: list[str] = []
    lower = user_text.lower()
    norm = normalize_prompt(user_text)

    if not user_text:
        return "local", "empty-user-sticky-candidate", 0

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

    if re.search(r"reasoning[_\s-]?effort\s*[:=]\s*(high|xhigh)", lower):
        score += 2
        reasons.append("effort-high")

    if hard_hit:
        lane = "frontier"
        score = max(score, 2)
        confident = True
    elif medium_hit:
        lane = "cheap"
        score = max(score, 1)
        confident = True
    elif easy_hits > 0 and score <= 0:
        lane = "local"
        confident = True
    elif score <= 0:
        lane = "local"
        confident = False  # no catalog hit — ambiguous
    elif score == 1:
        lane = "cheap"
        confident = True
    else:
        lane = "frontier"
        confident = True

    # Optional local LLM tie-break for paraphrases regex/phrases missed.
    want_llm = Cfg.llm_classify in {"always", "1", "true", "yes", "on"} or (
        Cfg.llm_classify in {"auto", ""} and not confident
    )
    # --classify unit tests stay offline unless explicitly always.
    if want_llm and not os.environ.get("ROUTER_CLASSIFY_OFFLINE"):
        llm_lane = ollama_classify_lane(user_text)
        if llm_lane in {"local", "cheap", "frontier"}:
            reasons.append(f"llm-classify:{llm_lane}")
            lane = llm_lane
            if llm_lane == "local":
                score = min(score, 0)
            elif llm_lane == "cheap":
                score = 1 if score < 1 else score
            else:
                score = max(score, 2)

    reason = ",".join(reasons) if reasons else "default-local"
    return lane, reason, score



def normalize_lane(value: str) -> str:
    v = value.strip().lower()
    if v == "cloud":
        return "frontier"
    return v


def _is_placeholder_secret(value: str) -> bool:
    return value.strip().lower() in {"", "ollama", "proxy-managed", "placeholder", "unused"}


def cloud_api_key(headers: dict[str, str]) -> str:
    """Real Anthropic API key if present (not Claude Code subscription)."""
    key = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ROUTER_ANTHROPIC_API_KEY")
        or headers.get("x-api-key")
        or ""
    ).strip()
    if _is_placeholder_secret(key):
        return ""
    return key


def load_claude_cli_oauth_token() -> str:
    """Load Claude Code CLI subscription OAuth access token if available.

    Sources (first hit wins):
      CLAUDE_ACCESS_TOKEN
      ~/.claude/.credentials.json (Linux/file fallback)
      macOS Keychain service "Claude Code-credentials"
    """
    env_token = (os.environ.get("CLAUDE_ACCESS_TOKEN") or "").strip()
    if env_token and not _is_placeholder_secret(env_token):
        return env_token

    cred_path = os.path.expanduser(
        os.environ.get("CLAUDE_CREDENTIALS_FILE", "~/.claude/.credentials.json")
    )
    try:
        with open(cred_path, encoding="utf-8") as fh:
            data = json.load(fh)
        # Common shapes used by Claude Code credential stores.
        for key in ("accessToken", "access_token", "claudeAiOauth"):
            val = data.get(key)
            if isinstance(val, str) and val.strip() and not _is_placeholder_secret(val):
                return val.strip()
            if isinstance(val, dict):
                nested = val.get("accessToken") or val.get("access_token") or ""
                if isinstance(nested, str) and nested.strip() and not _is_placeholder_secret(nested):
                    return nested.strip()
        oauth = data.get("oauth")
        if isinstance(oauth, dict):
            nested = oauth.get("accessToken") or oauth.get("access_token") or ""
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    except (OSError, json.JSONDecodeError, TypeError):
        pass

    if sys.platform == "darwin":
        import subprocess

        try:
            out = subprocess.check_output(
                ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            out = ""
        if out:
            if out.startswith("{"):
                try:
                    payload = json.loads(out)
                    nested = payload.get("accessToken") or payload.get("access_token") or ""
                    oauth = payload.get("claudeAiOauth")
                    if isinstance(oauth, dict):
                        nested = nested or oauth.get("accessToken") or oauth.get("access_token") or ""
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
                except (json.JSONDecodeError, TypeError):
                    pass
            if not _is_placeholder_secret(out):
                return out
    return ""


def inbound_bearer_token(headers: dict[str, str]) -> str:
    auth = (headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token and not _is_placeholder_secret(token):
            return token
    return ""


def cloud_auth_ready(headers: dict[str, str]) -> bool:
    """True if cheap/frontier can call Anthropic (API key or Claude Code OAuth)."""
    return bool(
        cloud_api_key(headers)
        or inbound_bearer_token(headers)
        or load_claude_cli_oauth_token()
    )


def decide_route(headers: dict[str, str], data: dict[str, Any]) -> tuple[str, str]:
    override = normalize_lane(headers.get("x-route") or Cfg.force or "")
    if override in {"local", "cheap", "frontier"}:
        if override in {"cheap", "frontier"} and not cloud_auth_ready(headers):
            return "local", f"cloud-unavailable→local (override:{override})"
        return override, f"override:{override}"

    key = session_key(data)
    if key in _SESSION_ROUTE:
        return _SESSION_ROUTE[key], f"sticky:{_SESSION_ROUTE[key]}"

    user_text = last_user_text(data.get("messages") or [])
    lane, reason, _score = score_route(user_text, data)

    if lane in {"cheap", "frontier"} and not cloud_auth_ready(headers):
        return "local", f"cloud-unavailable→local ({reason})"

    _SESSION_ROUTE[key] = lane
    if len(_SESSION_ROUTE) > 256:
        _SESSION_ROUTE.pop(next(iter(_SESSION_ROUTE)))
    return lane, reason


def rewrite_for_local(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out["model"] = Cfg.local_model
    thinking = out.get("thinking")
    if isinstance(thinking, dict):
        out["thinking"] = {"type": "disabled"}
    return out


def rewrite_for_hosted(data: dict[str, Any], model: str) -> dict[str, Any]:
    out = dict(data)
    out["model"] = model
    return out


def auth_headers_local(_headers: dict[str, str]) -> dict[str, str]:
    return {"x-api-key": "ollama"}


def auth_headers_cloud(headers: dict[str, str]) -> dict[str, str]:
    """Auth for api.anthropic.com: prefer API key, else Claude Code OAuth bearer."""
    api_key = cloud_api_key(headers)
    out: dict[str, str] = {
        "anthropic-version": headers.get("anthropic-version") or "2023-06-01",
    }
    for k, v in headers.items():
        if k.startswith("anthropic-") and k != "anthropic-version":
            out[k] = v

    if api_key:
        out["x-api-key"] = api_key
        return out

    token = inbound_bearer_token(headers) or load_claude_cli_oauth_token()
    if not token:
        return out

    out["Authorization"] = f"Bearer {token}"
    # Anthropic rejects Claude Code OAuth without this beta flag.
    beta = out.get("anthropic-beta", "")
    flag = "oauth-2025-04-20"
    if flag not in beta:
        out["anthropic-beta"] = f"{beta},{flag}" if beta else flag
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/", "/health", "/health/"}:
            self._json(
                200,
                {
                    "ok": True,
                    "proxy": "llm-router",
                    "lanes": ["local", "cheap", "frontier"],
                    "local_upstream": Cfg.local_upstream,
                    "cloud_upstream": Cfg.cloud_upstream,
                    "local_model": Cfg.local_model,
                    "cheap_model": Cfg.cheap_model,
                    "frontier_model": Cfg.frontier_model,
                    "cloud_model": Cfg.frontier_model,
                    "listen": f"http://{Cfg.listen_host}:{Cfg.listen_port}",
                    "cloud_key_configured": bool(cloud_api_key({})),
                    "claude_cli_oauth_configured": bool(load_claude_cli_oauth_token()),
                    "cloud_auth_ready": cloud_auth_ready({}),
                    "llm_classify": Cfg.llm_classify,
                },
            )
            return
        if path in {"/v1/models", "/v1/models/"}:
            self._json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "claude-sonnet-4-6",
                            "object": "model",
                            "owned_by": "router",
                            "display_name": (
                                f"Router → {Cfg.local_model} / "
                                f"{Cfg.cheap_model} / {Cfg.frontier_model}"
                            ),
                        },
                        {"id": Cfg.local_model, "object": "model", "owned_by": "ollama"},
                        {"id": Cfg.cheap_model, "object": "model", "owned_by": "anthropic"},
                        {"id": Cfg.frontier_model, "object": "model", "owned_by": "anthropic"},
                    ],
                },
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        path = self.path.split("?", 1)[0]
        if not path.startswith("/v1/messages"):
            self.send_error(404)
            return
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._json(400, {"type": "error", "error": {"message": "invalid json"}})
            return

        headers = {k.lower(): v for k, v in self.headers.items()}
        route, reason = decide_route(headers, data)
        if Cfg.log_routes:
            sys.stderr.write(f"[llm-router] route={route} reason={reason}\n")

        if route == "local":
            self._forward(Cfg.local_upstream, rewrite_for_local(data), auth_headers_local(headers))
            return

        if not cloud_auth_ready(headers):
            if Cfg.log_routes:
                sys.stderr.write("[llm-router] route=local reason=cloud-auth-missing-late\n")
            self._forward(Cfg.local_upstream, rewrite_for_local(data), auth_headers_local(headers))
            return

        model = Cfg.cheap_model if route == "cheap" else Cfg.frontier_model
        self._forward(
            Cfg.cloud_upstream,
            rewrite_for_hosted(data, model),
            auth_headers_cloud(headers),
        )

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _forward(self, upstream: str, data: dict[str, Any], extra_headers: dict[str, str]) -> None:
        self.close_connection = True
        body = json.dumps(data).encode()
        parsed = urlparse(upstream)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "anthropic-version": self.headers.get("anthropic-version") or "2023-06-01",
        }
        headers.update(extra_headers)
        wants_stream = bool(data.get("stream"))
        try:
            if parsed.scheme == "https":
                conn: http.client.HTTPConnection = http.client.HTTPSConnection(host, port, timeout=600)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=600)
            conn.request("POST", self.path, body=body, headers=headers)
            resp = conn.getresponse()
            content_type = resp.getheader("Content-Type") or "application/json"
            if wants_stream:
                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = resp.read(256)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            else:
                out = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(out)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(out)
            conn.close()
        except Exception as exc:  # noqa: BLE001
            msg = json.dumps(
                {
                    "type": "error",
                    "error": {"type": "api_error", "message": f"{exc} (upstream {upstream})"},
                }
            ).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[llm-router] " + (fmt % args) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Route Claude Code across local Qwen, Haiku, and Sonnet."
    )
    parser.add_argument("--host", default=Cfg.listen_host)
    parser.add_argument("--port", type=int, default=Cfg.listen_port)
    parser.add_argument("--local-model", default=Cfg.local_model)
    parser.add_argument("--cheap-model", default=Cfg.cheap_model)
    parser.add_argument("--frontier-model", default=Cfg.frontier_model)
    parser.add_argument(
        "--cloud-model",
        default=None,
        help="Legacy alias for --frontier-model",
    )
    parser.add_argument("--classify", metavar="TEXT", help="Print route decision for TEXT and exit")
    args = parser.parse_args()

    Cfg.listen_host = args.host
    Cfg.listen_port = args.port
    Cfg.local_model = args.local_model
    Cfg.cheap_model = args.cheap_model
    Cfg.frontier_model = args.cloud_model or args.frontier_model
    Cfg.cloud_model = Cfg.frontier_model

    if args.classify is not None:
        # Deterministic classify for tests/docs unless user forces LLM.
        if Cfg.llm_classify in {"auto", ""}:
            os.environ["ROUTER_CLASSIFY_OFFLINE"] = "1"
        route, reason, score = score_route(
            args.classify, {"messages": [{"role": "user", "content": args.classify}]}
        )
        print(json.dumps({"route": route, "reason": reason, "score": score}))
        return

    print(
        f"llm-router  http://{Cfg.listen_host}:{Cfg.listen_port}  "
        f"local={Cfg.local_model}  cheap={Cfg.cheap_model}  "
        f"frontier={Cfg.frontier_model}@{Cfg.cloud_upstream}",
        flush=True,
    )
    if cloud_api_key({}):
        print("auth: Anthropic API key available for cheap/frontier", flush=True)
    elif load_claude_cli_oauth_token():
        print("auth: Claude Code CLI OAuth available for cheap/frontier (no API key needed)", flush=True)
    else:
        print(
            "warning: no API key and no Claude Code OAuth — cheap/frontier fall back to local\n"
            "         Log in with: claude  (once), then restart llm-router",
            flush=True,
        )
    try:
        ThreadingHTTPServer((Cfg.listen_host, Cfg.listen_port), Handler).serve_forever()
    except OSError as exc:
        sys.stderr.write(f"error: bind {Cfg.listen_host}:{Cfg.listen_port}: {exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
