# Handoff — Local LLM + Heuristic Router

**Date:** 2026-08-27  
**Branch:** `main`  
**Machine context:** Office MacBook Pro M3 Pro, **36 GB**, used for other work too → prefer **14B** local headroom over 27B when routing.

This document is for the next human or agent session. Do **not** reopen OmniRoute / multiprovider-llm unless the user explicitly asks.

---

## 1. What we are building (current decision)

**Primary deliverable:** offline **heuristic scorer** with a **five-lane ladder** + **cascade failover** (default `./install.sh` path):

| Lane | Model | Role |
|------|--------|------|
| **local** | `qwen-fast` (`qwen3:14b`) | Easy lookups / renames / explain |
| **haiku** | **Haiku** (alias `cheap`) | Everyday implement / fix / test |
| **sonnet** | **Sonnet** (aliases `frontier`, `cloud`) | Harder multi-file / CI flakes |
| **opus** | **Opus** | Security, incidents, races, deep digs |
| **fable** | **Fable** | Org-wide / longest-horizon / hardest |

**Cascade (default on):** start at the scored lane → walk **down** the ladder → **local last** on model-not-found, 429/5xx/529, connect errors. `ROUTER_CASCADE=0` disables.

**Design origin:** [`docs/superpowers/specs/2026-08-27-heuristic-router-design.md`](./superpowers/specs/2026-08-27-heuristic-router-design.md) (originally three-lane; **code now supersedes** that doc for lanes/cascade).

**Status:** Implemented in `scripts/llm-router.py`. Mac/cmux live validation still recommended.

**Project folder:** `~/Projects/local-llm-mac` → `/workspace`

---

## 2. What was deferred

| Item | Doc | Notes |
|------|-----|--------|
| Stage orchestrator Plan→Build→Clean→Audit | [`2026-08-27-feature-pipeline-design.md`](./superpowers/specs/2026-08-27-feature-pipeline-design.md) | **DEFERRED**. |
| OmniRoute / multiprovider-llm | — | Rejected: privacy (office code). |
| Claude Desktop as orchestrator | — | Side chat only (rewrite proxy `:11436`). |
| Updating `docs/LOCAL-LLM-RESEARCH.md` | — | User asked not to update unless they ask. |

---

## 3. Operator UX

```
Cursor          → editor only
cmux / terminal → claude-routed → llm-router :11437
                                    ├ fable  → Claude Fable
                                    ├ opus   → Claude Opus
                                    ├ sonnet → Claude Sonnet
                                    ├ haiku  → Claude Haiku
                                    └ local  → Ollama qwen-fast  (last resort on cascade)
claude-local    → always local Qwen
```

- Prefer **Claude Code CLI login** (OAuth). API key optional.
- No auth → hosted picks collapse to local.
- Do **not** put permanent `ANTHROPIC_BASE_URL=…` in shell rc.

---

## 4. Repo map

| Path | State |
|------|--------|
| `scripts/llm-router.py` | Five lanes + cascade + scoring layers |
| `scripts/claude-routed` | Claude Code → `:11437` |
| `scripts/setup-14b-router.sh` | 14B + router install |
| `scripts/test-router-classify.sh` | local/haiku/sonnet/opus/fable + cascade helpers |
| `README.md` | Documents ladder + cascade |

```bash
bash scripts/test-router-classify.sh
curl -s http://127.0.0.1:11437/health   # lanes, cascade, model ids, cloud_auth_ready
```

---

## 5. Score bands

| Score / signal | Lane |
|----------------|------|
| `≤ 0` / easy catalogs | local |
| `1` / medium implement-fix-test | haiku |
| `2` / hard but not stacked | sonnet |
| `3–4` / opus phrases / stacked hard | opus |
| `≥ 5` / fable phrases | fable |

Layers: regex → informal phrases → structural cues → optional local LLM classify (`ROUTER_LLM_CLASSIFY=auto`).

Overrides: `x-route` / `ROUTER_FORCE` = `local|haiku|sonnet|opus|fable` (+ legacy aliases).

---

## 6. Environment

| Port | Service |
|------|---------|
| `11434` | Ollama |
| `11436` | Claude Desktop rewrite proxy |
| `11437` | `llm-router` |

- `ROUTER_LOCAL_MODEL`, `ROUTER_HAIKU_MODEL`, `ROUTER_SONNET_MODEL`, `ROUTER_OPUS_MODEL`, `ROUTER_FABLE_MODEL`
- Legacy: `ROUTER_CHEAP_MODEL`, `ROUTER_FRONTIER_MODEL`, `ROUTER_CLOUD_MODEL`
- `ROUTER_CASCADE=1` (default), `ROUTER_LLM_CLASSIFY=auto`

---

## 7. Constraints

1. Privacy: Anthropic + local Ollama only.  
2. 36GB: prefer 14B local lane; unload 27B when routing.  
3. Qwen thinking: `--think=false` / `"think": false`.  
4. Cursor at $0: editor only.  
5. Do not implement feature-pipeline unless asked.

---

## 8. Next steps

1. Mac: `setup-14b-router.sh` / `./install.sh`, `claude` login, `claude-routed`, watch cascade logs.  
2. Confirm Opus/Fable model ids on the account (`ROUTER_OPUS_MODEL` / `ROUTER_FABLE_MODEL` if catalog differs).  
3. Feature-pipeline remains deferred.

---

## 9. One-line summary

> Five-lane router (`local`/`haiku`/`sonnet`/`opus`/`fable`) with downward cascade to local is in `scripts/llm-router.py`. Validate on Mac via `claude-routed`. Feature pipeline deferred.
