# Implementation session — heuristic router

**Project path:** `~/Projects/local-llm-mac` → `/workspace`  
**Started:** 2026-08-27  
**Goal:** Three-lane `llm-router`: local (Qwen) / cheap (Haiku) / frontier (Sonnet)

| Doc | Path |
|-----|------|
| Spec | `docs/superpowers/specs/2026-08-27-heuristic-router-design.md` |
| Plan | `docs/superpowers/plans/2026-08-27-heuristic-router.md` |
| Handoff | `docs/HANDOFF.md` |

## Run

```bash
cd ~/Projects/local-llm-mac
bash scripts/test-router-classify.sh
```

Deferred: feature-pipeline. Out of scope: OmniRoute, multiprovider-llm.
