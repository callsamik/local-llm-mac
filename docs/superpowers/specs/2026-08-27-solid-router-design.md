# SOLID Refactor — Design

**Date:** 2026-08-27  
**Status:** Implementing  
**Scope:** `llm-router` (primary) + light structure for `claude-desktop-proxy`

## Mapping

| Principle | Application |
|-----------|-------------|
| **S** | One module per concern: config, catalogs, heuristic score, LLM score, auth, rewrite, cascade, session, upstream, HTTP handler, CLI |
| **O** | Extend via `Scorer`, `AuthProvider`, `UpstreamClient` protocols — add scorers without editing handler |
| **L** | Implementations satisfy protocol contracts (same inputs/outputs) |
| **I** | Narrow protocols (`score`, `is_ready`/`headers_for`, `exchange`) — no god interface |
| **D** | Handler depends on abstractions; `build_app()` wires concrete types |

## Layout

```
llm_router/
  protocols.py      # Scorer, AuthProvider, UpstreamClient, ...
  config.py
  models.py         # RouteDecision, lane constants
  catalog.py        # regex/phrase data
  text.py           # normalize_prompt, last_user_text, session_key
  scoring/          # heuristic, llm, composite, effort
  auth.py
  rewrite.py
  cascade.py
  session.py
  upstream.py
  handler.py
  composition.py    # DI factory
  cli.py
scripts/llm-router.py  # thin shim (path + main)
```

Behavior, env vars, and classify fixtures stay the same.
