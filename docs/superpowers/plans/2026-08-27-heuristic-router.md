# Heuristic Router (local / cheap / frontier) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `scripts/llm-router.py` so Claude Code turns score offline into **local** (Qwen), **cheap** (Haiku), or **frontier** (Sonnet).

**Architecture:** Keep the existing Anthropic `/v1/messages` proxy on `:11437`. Replace the binary local/cloud scorer with three score bands (`≤0` / `==1` / `≥2`), pin three model ids, sticky-session by conversation fingerprint, and fall back hosted→local when no real API key.

**Tech Stack:** Python 3 stdlib HTTP server, Ollama, Anthropic Messages API, bash classify tests, `claude-routed` launcher.

## Global Constraints

- Hosted pair locked: **cheap=Haiku**, **frontier=Sonnet** (not Opus).
- Local happy path: `qwen-fast` (`qwen3:14b`); not failover-only.
- No OmniRoute / multiprovider / Cursor Fable.
- Do not implement feature-pipeline; do not edit `docs/LOCAL-LLM-RESEARCH.md`.
- Placeholder API key `ollama` is not a real key.
- Legacy override `cloud` maps to `frontier`.

---

### Task 1: Failing three-lane classify tests

**Files:**
- Modify: `scripts/test-router-classify.sh`
- Modify: `scripts/llm-router.py` (only if `--classify` JSON `route` field needs to stay stable)

**Interfaces:**
- Consumes: `python3 scripts/llm-router.py --classify TEXT` → JSON `{"route","reason","score"}`
- Produces: shell checks expecting `local` | `cheap` | `frontier`

- [ ] **Step 1: Rewrite classify fixtures**

Replace `scripts/test-router-classify.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/scripts/llm-router.py"

check() {
  local text="$1" expect="$2"
  local got
  got="$(python3 "${PY}" --classify "${text}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["route"])')"
  if [[ "${got}" != "${expect}" ]]; then
    printf 'FAIL: %r → %s (want %s)\n' "${text}" "${got}" "${expect}" >&2
    python3 "${PY}" --classify "${text}" >&2
    exit 1
  fi
  printf 'ok  %s ← %s\n' "${expect}" "${text}"
}

check "rename the helper and fix the typo" local
check "list the files in this folder" local
check "what is UserService?" local
check "implement a login form with validation" cheap
check "add a unit test for parseDate" cheap
check "fix the bug in the save handler" cheap
check "root cause the flaky payment race condition across services" frontier
check "design the architecture for a multi-service migration" frontier
check "security audit of the auth flow" frontier
echo "all classification checks passed"
```

- [ ] **Step 2: Run tests — expect failures on cheap cases**

Run: `bash scripts/test-router-classify.sh`  
Expected: FAIL on `implement a login form…` (still `local` under 2-lane scorer) or hard cases still print `cloud` if not yet renamed.

- [ ] **Step 3: Commit test update**

```bash
git add scripts/test-router-classify.sh
git commit -m "test: expect local/cheap/frontier classify lanes"
```

---

### Task 2: Three-lane scorer + model pins

**Files:**
- Modify: `scripts/llm-router.py`

**Interfaces:**
- Consumes: `HARD_PATTERNS`, `EASY_PATTERNS`, `last_user_text`, request `thinking`
- Produces: `score_route(...) -> (lane, reason, score)` where lane ∈ `{local,cheap,frontier}`
- Produces: `Cfg.cheap_model`, `Cfg.frontier_model` (keep `Cfg.cloud_model` as alias of frontier for compat)
- Produces: `MEDIUM_PATTERNS` (+1 toward cheap)

- [ ] **Step 1: Update Cfg and docstring**

```python
"""Route Anthropic /v1/messages across local / cheap / frontier.

local    → Ollama qwen-fast (easy/medium happy path)
cheap    → Anthropic Haiku
frontier → Anthropic Sonnet

Overrides: x-route / ROUTER_FORCE = local|cheap|frontier|cloud
(cloud is legacy alias for frontier)
"""

class Cfg:
    local_upstream = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
    cloud_upstream = os.environ.get("ANTHROPIC_UPSTREAM", "https://api.anthropic.com").rstrip("/")
    local_model = os.environ.get("ROUTER_LOCAL_MODEL", "qwen-fast")
    cheap_model = os.environ.get("ROUTER_CHEAP_MODEL", "claude-haiku-4-5")
    frontier_model = os.environ.get(
        "ROUTER_FRONTIER_MODEL",
        os.environ.get("ROUTER_CLOUD_MODEL", "claude-sonnet-4-6"),
    )
    # Back-compat alias used by older health callers
    cloud_model = frontier_model
    listen_host = os.environ.get("ROUTER_HOST", "127.0.0.1")
    listen_port = int(os.environ.get("ROUTER_PORT", "11437"))
    force = os.environ.get("ROUTER_FORCE", "").strip().lower()
    log_routes = os.environ.get("ROUTER_LOG", "1") != "0"
```

- [ ] **Step 2: Add MEDIUM_PATTERNS and rewrite score_route bands**

```python
MEDIUM_PATTERNS = [
    r"\bimplement\b",
    r"\badd\s+(a\s+)?(feature|test|endpoint|handler|component)\b",
    r"\bwrite\s+(a\s+)?(test|tests)\b",
    r"\bfix\s+(the\s+)?bug\b",
    r"\bfix\b",
    r"\bunit\s+test\b",
    r"\brefactor\b",
]

def score_route(user_text: str, data: dict[str, Any]) -> tuple[str, str, int]:
    """Return (lane, reason, score). <=0 local, 1 cheap, >=2 frontier."""
    score = 0
    reasons: list[str] = []
    lower = user_text.lower()

    if not user_text:
        return "local", "empty-user-sticky-candidate", 0

    for pat in HARD_PATTERNS:
        if re.search(pat, lower, re.I):
            score += 2
            reasons.append(f"hard:{pat}")
    for pat in MEDIUM_PATTERNS:
        if re.search(pat, lower, re.I):
            score += 1
            reasons.append(f"medium:{pat}")
    for pat in EASY_PATTERNS:
        if re.search(pat, lower, re.I):
            score -= 1
            reasons.append(f"easy:{pat}")

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

    if score <= 0:
        lane = "local"
    elif score == 1:
        lane = "cheap"
    else:
        lane = "frontier"
    reason = ",".join(reasons) if reasons else "default-local"
    return lane, reason, score
```

- [ ] **Step 3: Update decide_route overrides and hosted fallback**

```python
def normalize_lane(value: str) -> str:
    v = value.strip().lower()
    if v == "cloud":
        return "frontier"
    return v

def decide_route(headers: dict[str, str], data: dict[str, Any]) -> tuple[str, str]:
    override = normalize_lane(headers.get("x-route") or Cfg.force or "")
    if override in {"local", "cheap", "frontier"}:
        if override in {"cheap", "frontier"} and not cloud_api_key(headers):
            return "local", f"cloud-unavailable→local (override:{override})"
        return override, f"override:{override}"

    key = session_key(data)
    if key in _SESSION_ROUTE:
        return _SESSION_ROUTE[key], f"sticky:{_SESSION_ROUTE[key]}"

    user_text = last_user_text(data.get("messages") or [])
    lane, reason, _score = score_route(user_text, data)

    if lane in {"cheap", "frontier"} and not cloud_api_key(headers):
        return "local", f"cloud-unavailable→local ({reason})"

    _SESSION_ROUTE[key] = lane
    if len(_SESSION_ROUTE) > 256:
        _SESSION_ROUTE.pop(next(iter(_SESSION_ROUTE)))
    return lane, reason
```

- [ ] **Step 4: Run classify tests**

Run: `bash scripts/test-router-classify.sh`  
Expected: `all classification checks passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/llm-router.py
git commit -m "feat: score turns into local, cheap, and frontier lanes"
```

---

### Task 3: Wire forwarding, health, and rewrite helpers

**Files:**
- Modify: `scripts/llm-router.py` (`Handler.do_GET`, `do_POST`, `rewrite_for_*`, `main`)

**Interfaces:**
- Consumes: `decide_route` → lane
- Produces: local → Ollama; cheap/frontier → Anthropic with matching model id

- [ ] **Step 1: Rewrite helpers**

```python
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
```

- [ ] **Step 2: Health + models list include three lanes**

Health JSON must include `cheap_model`, `frontier_model`, `local_model`, `cloud_key_configured`.

- [ ] **Step 3: do_POST branches on lane**

```python
route, reason = decide_route(headers, data)
# ...
if route == "local":
    self._forward(Cfg.local_upstream, rewrite_for_local(data), auth_headers_local(headers))
elif route == "cheap":
    key = cloud_api_key(headers)
    self._forward(Cfg.cloud_upstream, rewrite_for_hosted(data, Cfg.cheap_model), auth_headers_cloud(headers, key))
else:  # frontier
    key = cloud_api_key(headers)
    self._forward(Cfg.cloud_upstream, rewrite_for_hosted(data, Cfg.frontier_model), auth_headers_cloud(headers, key))
```

- [ ] **Step 4: CLI --local-model / --cheap-model / --frontier-model**

Update `argparse` accordingly; keep `--cloud-model` as alias setting frontier.

- [ ] **Step 5: Smoke health**

```bash
python3 scripts/llm-router.py --port 11437 &
sleep 0.3
curl -sf http://127.0.0.1:11437/health | python3 -m json.tool
kill %1
```

Expected: `"cheap_model": "claude-haiku-4-5"`, `"frontier_model": "claude-sonnet-4-6"`.

- [ ] **Step 6: Commit**

```bash
git add scripts/llm-router.py
git commit -m "feat: forward cheap/frontier lanes to Haiku and Sonnet"
```

---

### Task 4: Docs + session polish

**Files:**
- Modify: `README.md` (smart router section → three lanes)
- Modify: `docs/HANDOFF.md` (mark implementation in progress / done)
- Modify: `scripts/setup-14b-router.sh` (mention cheap/frontier in Done blurb)
- Keep: `IMPLEMENTATION-SESSION.md`

- [ ] **Step 1: README three-lane blurb**

Replace the 2-lane smart-router paragraph with local/cheap/frontier and Haiku+Sonnet.

- [ ] **Step 2: Handoff status**

Note: three-lane router implemented; Mac validation still needed.

- [ ] **Step 3: Full test + commit + push**

```bash
bash scripts/test-router-classify.sh
git add README.md docs/HANDOFF.md scripts/setup-14b-router.sh IMPLEMENTATION-SESSION.md
git commit -m "docs: document three-lane heuristic router"
git push -u origin HEAD
```

---

## Spec coverage check

| Spec item | Task |
|-----------|------|
| Score bands ≤0/1/≥2 | Task 2 |
| MEDIUM → cheap | Task 2 |
| Haiku + Sonnet locked | Tasks 2–3 |
| Sticky + overrides + cloud→frontier | Task 2 |
| No key → local | Task 2 |
| Health lists three models | Task 3 |
| Classify fixtures | Task 1 |
| README / no research doc edit | Task 4 |
| Feature-pipeline not built | (omitted) |
