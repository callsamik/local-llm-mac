# Handoff — Local LLM + Heuristic Router

**Date:** 2026-08-27  
**Branch:** `main`  
**Machine:** Office MacBook Pro M3 Pro, **36 GB** → prefer **14B** local headroom.

Do **not** reopen OmniRoute / multiprovider-llm unless the user asks.

---

## Current decision

**Auto ladder:** `local → haiku → sonnet` only.  
**Opus / Fable:** opt-in only (`use opus` / `use fable`, `x-route`, `ROUTER_FORCE`). Hard prompts raise **sonnet effort**, not the lane.  
**Also scored:** effort (`low|medium|high|xhigh|max`, extra→xhigh) + thinking (`off`|adaptive).  
**Versions:** env-pinned; cascade on errors.  
**Hard block:** `ROUTER_DISABLE_OPUS=1` / `ROUTER_DISABLE_FABLE=1`.

Specs:
- [`docs/superpowers/specs/2026-08-27-effort-thinking-optin-design.md`](./superpowers/specs/2026-08-27-effort-thinking-optin-design.md)
- Earlier three-lane history: [`2026-08-27-heuristic-router-design.md`](./superpowers/specs/2026-08-27-heuristic-router-design.md) (superseded for lanes)

**Project:** `~/Projects/local-llm-mac` → `/workspace`

---

## Deferred

Feature-pipeline Plan→Build→Clean→Audit · OmniRoute · research-doc updates · Desktop as orchestrator.

---

## UX

```
cmux → claude-routed → llm-router :11437
  auto: local | haiku | sonnet (+ effort/thinking)
  opt-in: opus | fable
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

> Auto routes local/haiku/sonnet with effort+thinking; opus/fable only on request; cascade to local on errors.
