# Heuristic Router: local / cheap / frontier — Design

**Date:** 2026-08-27  
**Status:** Approved defaults locked (Haiku + Sonnet); pending final review before implementation plan  
**Supersedes for near-term work:** [`2026-08-27-feature-pipeline-design.md`](./2026-08-27-feature-pipeline-design.md) (deferred)

**Out of scope:** OmniRoute, multiprovider-llm, Cursor-pool models (Fable/Sol/etc.), stage orchestrator Plan→Build→Clean→Audit (deferred).

## 1. Goal

Extend the existing `llm-router` so each Claude Code turn is scored **offline** (no classifier model call) into one of three lanes:

| Lane | When | Backend | Default model |
|------|------|---------|---------------|
| **local** | Easy / medium; machine can handle it | Ollama `127.0.0.1:11434` | `qwen-fast` (`qwen3:14b`) |
| **cheap** | Needs hosted quality, not deep reasoning | Anthropic API | **Haiku** (`claude-haiku-4-5` or env override) |
| **frontier** | Hard / reasoning-intensive | Anthropic API | **Sonnet** (`claude-sonnet-4-6` or env override) |

**Hosted pair (locked):** **A — Haiku + Sonnet** (not Sonnet + Opus). Opus is out of scope for this spike; operators may still override `ROUTER_FRONTIER_MODEL` later, but the approved default frontier tier is Sonnet.

Local is a **happy-path** lane (not failover-only). This validates cost/latency savings on a 36GB Mac while keeping office code off third-party gateways.

## 2. Non-goals

- Stage-pinned pipeline (Opus plan / Sonnet build / Haiku clean / Opus audit) — **deferred**.
- Multi-provider cloud routing.
- Using Cursor Agent or Claude Desktop as the router client of record.
- Training or calling a local classifier model for routing.
- Updating `docs/LOCAL-LLM-RESEARCH.md` in this workstream.

## 3. How it fits Claude / Cursor / cmux

```
Cursor IDE       → editor only (Agent not required for this spike)
cmux / terminal  → claude-routed  ──►  llm-router :11437
                                      ├─ local    → Ollama qwen-fast
                                      ├─ cheap    → Anthropic Haiku
                                      └─ frontier → Anthropic Sonnet
claude-local     → forced local (bypass scorer); still available
```

- Operator works in **cmux** on the repo, runs `claude-routed`.
- `ANTHROPIC_BASE_URL=http://127.0.0.1:11437`; sentinel `ANTHROPIC_API_KEY=ollama` only so Claude Code honors the base URL.
- **Hosted auth:** Claude Code CLI subscription OAuth (`~/.claude` / macOS Keychain), or optional real `ANTHROPIC_API_KEY` if present.
- Without either, cheap/frontier **fall back to local** and log `cloud-unavailable→local`.
- Cursor-pool “frontier” names (Fable, etc.) are **not** targets; “frontier” here means **hosted Anthropic Sonnet**.

## 4. Architecture

```
Claude Code request (/v1/messages)
        │
        ▼
┌───────────────────┐
│  override?        │  x-route / ROUTER_FORCE
│  local|cheap|     │
│  frontier         │
└─────────┬─────────┘
          │ none
          ▼
┌───────────────────┐
│  sticky session?  │  same conversation fingerprint
└─────────┬─────────┘
          │ none
          ▼
┌───────────────────┐
│  heuristic score  │  last user text + thinking flags
│  → local|cheap|   │
│    frontier       │
└─────────┬─────────┘
          ▼
   rewrite model id → forward to Ollama or Anthropic
```

Single process: extend `scripts/llm-router.py`. Keep `claude-routed` as the launcher.

## 5. Scoring rules

Return `(lane, reason, score)`.

| Score band | Lane |
|------------|------|
| `score <= 0` | **local** |
| `score == 1` | **cheap** |
| `score >= 2` | **frontier** |

### Signals (additive)

**Toward frontier (+2 each, unless noted):**

- Existing hard patterns: architecture, migration, race/deadlock/flaky, security audit, multi-service, root cause, deep dive, complex bug, production incident, etc.
- `thinking.type` in `{enabled, adaptive}`
- User text mentions `reasoning_effort` high/xhigh or “think hard”
- User text length > 6000 chars (+2); > 2500 chars (+1 only)

**Toward cheap / away from local:**

- Medium coding asks that are not hard and not easy: default path when score would be 0 but task looks like “implement / fix / add / write test” without hard keywords → **+1** (cheap), so normal feature edits use Haiku when a key exists rather than overloading 14B.

**Toward local (−1 each):**

- Existing easy patterns: rename, typo, explain, what/where is, list files, summarize, format, comment, docstring, simple, quick, ping, boilerplate, add a log/print/comment.

**Empty user text** (tool-loop continuation): do not rescore; use **sticky** lane from session.

### Sticky sessions

First scored user turn in a conversation fingerprints the session; later tool rounds keep that lane so a frontier debugging loop does not bounce to local mid-tools.

### Overrides

| Mechanism | Values |
|-----------|--------|
| Header `x-route` | `local` \| `cheap` \| `frontier` \| `auto` |
| Env `ROUTER_FORCE` | same |
| Legacy `cloud` | maps to **frontier** |
| `claude-local` | does not use this router (direct Ollama) OR may call router with `ROUTER_FORCE=local` — prefer keep `claude-local` direct for simplicity |

## 6. Model & env config

| Env | Default | Role |
|-----|---------|------|
| `ROUTER_LOCAL_MODEL` | `qwen-fast` | local lane |
| `ROUTER_CHEAP_MODEL` | `claude-haiku-4-5` | cheap lane (override if account id differs) |
| `ROUTER_FRONTIER_MODEL` | `claude-sonnet-4-6` | frontier lane (**Sonnet**, per choice A) |
| ~~Opus as frontier~~ | — | **Not** the approved default for this spike |
| `OLLAMA_UPSTREAM` | `http://127.0.0.1:11434` | |
| `ANTHROPIC_UPSTREAM` | `https://api.anthropic.com` | |
| `ANTHROPIC_API_KEY` / `ROUTER_ANTHROPIC_API_KEY` | — | required for cheap/frontier |

Health payload lists all three models and `cloud_key_configured`.

## 7. Failure behavior

| Condition | Behavior |
|-----------|----------|
| cheap/frontier selected, no real API key | Route **local**, reason `cloud-unavailable→local` |
| cheap/frontier upstream 429/402/connection error | **Do not** auto-escalate to the other hosted tier in v1; return error to client (operator can retry or `x-route: local`). Optional later: single retry to local with `x-router-degraded: true` |
| local / Ollama down | 502 with clear upstream error |

v1 stays simple: **no silent Hosted→Hosted failover**; optional **Hosted→local degraded** can be a follow-up flag `ROUTER_DEGRADE_TO_LOCAL=1`.

## 8. Operator workflow (Mac / cmux)

```bash
./scripts/setup-14b-router.sh          # once: pull 14B, install router
export ANTHROPIC_API_KEY=sk-ant-...    # for cheap/frontier
ollama stop qwen-code                  # free 27B RAM if loaded
llm-router                             # if LaunchAgent not up
# in cmux on the repo:
claude-routed
```

Classify without serving:

```bash
python3 scripts/llm-router.py --classify "rename the helper"
# → {"route":"local",...}
python3 scripts/llm-router.py --classify "implement a login form with validation"
# → {"route":"cheap",...}
python3 scripts/llm-router.py --classify "root cause the flaky payment race"
# → {"route":"frontier",...}
```

## 9. Testing

| Test | Expect |
|------|--------|
| Easy phrases | `local` |
| “implement / add feature / fix bug” without hard words | `cheap` |
| Hard phrases (race, architecture, security audit, …) | `frontier` |
| Legacy `--classify` + unit script updated for three lanes | pass |
| No API key + frontier phrase | decide_route → `local` with cloud-unavailable reason |
| Sticky: second message tool_result empty user | same lane as first |

## 10. Files to change

| Path | Action |
|------|--------|
| `scripts/llm-router.py` | Three-lane scorer, model pins, health, classify |
| `scripts/test-router-classify.sh` | Cases for local / cheap / frontier |
| `scripts/claude-routed` | Unchanged entry; ensure key passthrough |
| `README.md` | Document three lanes (short); do not rewrite research doc |
| `docs/superpowers/specs/2026-08-27-feature-pipeline-design.md` | Mark **deferred** |

## 11. Relationship to deferred pipeline

The stage orchestrator (Opus/Sonnet/Haiku by **stage**, Qwen failover-only) remains a **later** design. This heuristic router is the near-term spike to validate:

- local handles real easy/medium load on 36GB  
- Haiku absorbs mid-tier hosted work  
- Sonnet only when the scorer says frontier  

If the spike works, a future pipeline can **reuse** this router (e.g. force lanes per stage) without mixing concerns in v1.

## 12. Success criteria

1. `--classify` and live `/v1/messages` agree on local / cheap / frontier for the fixture set.  
2. On a Mac with key set, cmux `claude-routed` sends easy turns to Ollama and hard turns to Sonnet (visible in router logs).  
3. Mid-tier “implement X” lands on Haiku, not Sonnet.  
4. No third-party gateway; Anthropic + local Ollama only.  
5. Research doc untouched.
