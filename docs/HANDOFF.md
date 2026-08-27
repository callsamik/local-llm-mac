# Handoff — Local LLM + Heuristic Router

**Date:** 2026-08-27  
**Branch:** `main`  
**Machine context:** Office MacBook Pro M3 Pro, **36 GB**, used for other work too → prefer **14B** local headroom over 27B when routing.

This document is for the next human or agent session. Do **not** reopen OmniRoute / multiprovider-llm unless the user explicitly asks.

---

## 1. What we are building (current decision)

**Primary deliverable:** offline **heuristic scorer** with three lanes:

| Lane | Model | Role |
|------|--------|------|
| **local** | `qwen-fast` (`qwen3:14b` via Ollama) | Easy/medium — **happy path**, not failover-only |
| **cheap** | **Haiku** | Hosted mid-tier |
| **frontier** | **Sonnet** | Hard / reasoning-heavy |

**Locked choice:** hosted pair **A = Haiku + Sonnet** (not Sonnet + Opus).

**Design spec (source of truth):**  
[`docs/superpowers/specs/2026-08-27-heuristic-router-design.md`](./superpowers/specs/2026-08-27-heuristic-router-design.md)

**Status of that spec:** defaults locked; user had not yet said “write the implementation plan” / “implement” after locking A. Next step after handoff: confirm spec OK → **implementation plan** → extend `llm-router.py` to three lanes.

---

## 2. What was deferred

| Item | Doc | Notes |
|------|-----|--------|
| Stage orchestrator Plan→Build→Clean→Audit | [`2026-08-27-feature-pipeline-design.md`](./superpowers/specs/2026-08-27-feature-pipeline-design.md) | Marked **DEFERRED**. Local was failover-only there; that contradicted the original heuristic ask. |
| OmniRoute / multiprovider-llm | — | Rejected: privacy (office code) + not the stage/heuristic brain. |
| Cursor Agent / Fable / pool frontier models | — | Not pipeline/router targets. Cursor = editor. |
| Claude Desktop as orchestrator | — | Side chat only (rewrite proxy `:11436`). |
| Updating `docs/LOCAL-LLM-RESEARCH.md` | — | User asked not to update research doc while trying things practically; keep that unless they ask. |

---

## 3. How the operator uses it (intended UX)

```
Cursor          → editor / browse (not the router runner)
cmux / terminal → claude-routed → llm-router :11437
                                    ├ local    → Ollama qwen-fast
                                    ├ cheap    → Anthropic Haiku
                                    └ frontier → Anthropic Sonnet
claude-local    → always local Qwen (side chat / offline)
```

- Real `ANTHROPIC_API_KEY` needed for cheap/frontier.
- No key → those lanes fall back to local with an explicit log reason.
- Do **not** put permanent `ANTHROPIC_BASE_URL=…11434` in shell rc (breaks real `claude` later).

---

## 4. What already exists in the repo (code)

### Working / partial today

| Path | State |
|------|--------|
| `scripts/llm-router.py` | **2-lane** only: `local` vs `cloud` (cloud ≈ Sonnet). Needs upgrade to `local` / `cheap` / `frontier`. |
| `scripts/claude-routed` | Points Claude Code at `:11437`. |
| `scripts/setup-14b-router.sh` | Pulls `qwen3:14b`, creates `qwen-fast`, installs router + optional LaunchAgent. |
| `modelfiles/qwen-code-14b.Modelfile` | Lean 14B alias (`num_ctx` 24576). |
| `scripts/test-router-classify.sh` | Tests 2-lane classify; must be extended for cheap. |
| `scripts/claude-local` | Session-only env → Ollama `qwen-code` (27B path). |
| `scripts/claude-desktop-proxy.py` | Desktop gateway rewrite on `:11436` → local model. |
| `install.sh` + `modelfiles/qwen-code.Modelfile` | Original 27B install path. |
| `README.md` | Mentions 27B install + early 14B/2-lane router section. |

### Classify smoke (current 2-lane)

```bash
bash scripts/test-router-classify.sh
# easy → local; hard → cloud (will become frontier)
```

---

## 5. Score bands (to implement)

From the heuristic design:

| Score | Lane |
|------|------|
| `≤ 0` | local |
| `== 1` | cheap |
| `≥ 2` | frontier |

- Hard patterns / thinking / long text → push toward frontier.
- Easy patterns → push toward local.
- Mid “implement / fix / add test” without hard keywords → **cheap** (+1), so 14B is not overloaded and Sonnet is not burned on routine edits.
- Sticky session so tool loops stay on one lane.
- Overrides: `x-route: local|cheap|frontier`, `ROUTER_FORCE=…`; legacy `cloud` → frontier.

---

## 6. Environment / ports (Mac)

| Port | Service |
|------|---------|
| `11434` | Ollama |
| `11436` | Claude Desktop rewrite proxy (optional) |
| `11437` | `llm-router` |

Useful env:

- `ROUTER_LOCAL_MODEL=qwen-fast`
- `ROUTER_CHEAP_MODEL=claude-haiku-4-5` (adjust if account catalog differs)
- `ROUTER_FRONTIER_MODEL=claude-sonnet-4-6`
- `ANTHROPIC_API_KEY` or `ROUTER_ANTHROPIC_API_KEY`
- Placeholder `ollama` must **not** count as a real key (already handled in router).

Mac setup sketch:

```bash
./scripts/setup-14b-router.sh
export ANTHROPIC_API_KEY=sk-ant-...
ollama stop qwen-code    # free 27B if loaded
llm-router               # if LaunchAgent not up
# cmux on repo:
claude-routed
```

---

## 7. Constraints to preserve

1. **Privacy:** Anthropic + local Ollama only. No third-party LLM gateways that see office code.  
2. **36GB headroom:** Prefer 14B (`qwen-fast`) for the local lane; unload 27B when using the router path.  
3. **Thinking on Qwen:** `/no_think` unreliable; use `--think=false` / API `"think": false`.  
4. **Claude Code 500 “no user query found”:** was ctx too small on 27B path → `num_ctx` 49152 for `qwen-code`; 14B alias uses 24576 by design.  
5. **Cursor at $0 balance:** editor only; Agent/BYOK won’t unlock local.  
6. **Do not** expand scope back into stage pipeline unless user asks.

---

## 8. Suggested next steps (in order)

1. User confirms heuristic design is final.  
2. Write implementation plan under `docs/superpowers/plans/` (writing-plans skill).  
3. Implement three-lane scoring in `llm-router.py` + update `test-router-classify.sh` + short README note.  
4. On Mac: `setup-14b-router.sh`, run classify fixtures, then `claude-routed` in cmux and watch `[llm-router] route=…` logs.  
5. Only after spike validation: reconsider deferred feature-pipeline design.

---

## 9. Key commits (recent)

| Commit | Meaning |
|--------|---------|
| `fefa31e` | 14B Modelfile + 2-lane router + `claude-routed` + setup script |
| `b60cfce` | Feature-pipeline design (now deferred) |
| `0dc8ce0` | Heuristic local/cheap/frontier design as primary |
| `be0820c` | Lock hosted pair to Haiku + Sonnet |

---

## 10. Open questions (none blocking choice A)

- Exact Haiku/Sonnet model id strings on the user’s Anthropic account (env-overridable).  
- Whether v1 should degrade hosted 429 → local (`ROUTER_DEGRADE_TO_LOCAL`); design says optional follow-up.  
- Whether README should demote 27B to “legacy” once 14B path is proven — not required for the spike.

---

## 11. One-line summary for the next agent

> Extend `scripts/llm-router.py` from 2-lane local/cloud to **3-lane local (Qwen) / cheap (Haiku) / frontier (Sonnet)** per [`docs/superpowers/specs/2026-08-27-heuristic-router-design.md`](./superpowers/specs/2026-08-27-heuristic-router-design.md); leave the stage pipeline deferred; no OmniRoute; implement after an implementation plan unless the user says to code immediately.
