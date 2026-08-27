# Handoff — Local LLM + Heuristic Router

**Date:** 2026-08-27  
**Branch:** `main`  
**Machine:** Office MacBook Pro M3 Pro, **36 GB** → prefer **14B** local headroom.  
**Public repo:** https://github.com/callsamik/local-llm-mac

Do **not** reopen OmniRoute / multiprovider-llm unless the user asks.

---

## Current decision

**Auto ladder:** `local → haiku → sonnet` (+ effort/thinking).  
**Opus / Fable:** off by default. Turn on with config flags so only matching hard categories can use them.  
**Local LLM scores:** when heuristics are uncertain/conflicting/borderline (`ROUTER_LLM_CLASSIFY=auto`).  
**Versions:** env-pinned; cascade on errors.

### Enable Opus / Fable

```bash
export ROUTER_ENABLE_OPUS=1
export ROUTER_ENABLE_FABLE=1   # optional
# restart llm-router (or reload LaunchAgent)
curl -s http://127.0.0.1:11437/health   # enable_opus / enable_fable should be true
```

Accepted: `1` / `true` / `yes` / `on`.  
Force off: unset, `0`, or `ROUTER_DISABLE_OPUS=1` / `ROUTER_DISABLE_FABLE=1`.

When enabled, dedicated phrase/score bands assign those lanes (opus ≈ score ≥4 / security-incident cues; fable ≈ score ≥6 / org-wide cues). When disabled, those prompts stay on **sonnet** with higher effort. `x-route` / `use opus` are gated by the same flags.

Specs:
- [`docs/superpowers/specs/2026-08-27-effort-thinking-optin-design.md`](./superpowers/specs/2026-08-27-effort-thinking-optin-design.md)
- SOLID layout: [`docs/superpowers/specs/2026-08-27-solid-router-design.md`](./superpowers/specs/2026-08-27-solid-router-design.md)

**Code layout:** packages `llm_router/` and `claude_desktop_proxy/`; `scripts/*.py` are thin shims.

---

## Deferred

Feature-pipeline Plan→Build→Clean→Audit · OmniRoute · research-doc updates · Desktop as orchestrator.

---

## UX

```
cmux → claude-routed → llm-router :11437
  auto: local | haiku | sonnet (+ effort/thinking)
  optional: opus | fable when ROUTER_ENABLE_* =1
  cascade ↓ → local last
```

Claude Code OAuth preferred; no permanent `ANTHROPIC_BASE_URL` in shell rc.

---

## Verify

```bash
bash scripts/test-router-classify.sh
curl -s http://127.0.0.1:11437/health
```

---

## One-liner

> Auto routes local/haiku/sonnet with effort+thinking; enable Opus/Fable via `ROUTER_ENABLE_OPUS` / `ROUTER_ENABLE_FABLE` for category-matched hard prompts; cascade to local on errors.
