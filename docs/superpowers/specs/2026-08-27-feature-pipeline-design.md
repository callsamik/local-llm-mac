# Feature Pipeline + Failover Router — Design

**Date:** 2026-08-27  
**Status:** **DEFERRED** — superseded for near-term work by [`2026-08-27-heuristic-router-design.md`](./2026-08-27-heuristic-router-design.md) (local / cheap / frontier heuristic). Keep this doc as a future optional architecture; do not implement until the heuristic spike is validated.  
**Out of scope for now:** OmniRoute, multiprovider-llm, and any multi-cloud gateway that can see office code.

## 1. Goal

Run a **pure hosted stage pipeline** for production feature work on the office Mac, with **local Qwen strictly isolated** as side-chat and emergency failover for selected stages only.

| Stage | Model | On Anthropic failure |
|-------|--------|----------------------|
| Plan | Claude Opus | **Abort** (never Qwen) |
| Build | Claude Sonnet (parallel workers) | **Degrade to local Qwen** + `degraded=true` |
| Clean | Claude Haiku | **Degrade to local Qwen** + `degraded=true` |
| Audit | Claude Opus | **Abort** (never Qwen); pass → allow commit; fail → block commit |

## 2. Non-goals

- Mixing Qwen into healthy Plan/Build/Clean/Audit as a peer tier.
- Running the pipeline inside Cursor Agent or Claude Desktop.
- Multi-provider cloud routing (OpenRouter, OmniRoute, multiprovider gateways).
- Rewriting `docs/LOCAL-LLM-RESEARCH.md` as part of this work.
- Replacing `claude-local` ad-hoc chat (that path stays as-is for offline/side questions).

## 3. How it fits Claude / Cursor

```
Cursor IDE          → editor / browse only (not the orchestrator)
claude-local        → ad-hoc local Qwen (outside pipeline)
feature-pipeline    → Plan→Build→Clean→Audit (this design)
llm-router (:11437) → Anthropic Messages switchboard + Build/Clean failover
Claude Desktop      → optional side chat; not the pipeline
```

- **Cursor Agent** is not supported as the runner (localhost reachability + usage gates).
- **Claude Code CLI** (or direct Anthropic Messages API) is the worker runtime under the orchestrator.
- Operator runs from **terminal or cmux** on the target repo.

## 4. Architecture

```
                    [ feature-pipeline CLI ]
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         Plan (Opus)    Build (Sonnet×N)  Clean (Haiku)
              │               │               │
              │               ╳ failover      ╳ failover
              │               ▼               ▼
              │         [ qwen-fast / Ollama ]  (degraded only)
              ▼
         Audit (Opus) ── pass → git commit
                      └── fail → block + report
```

Two components:

1. **`feature-pipeline`** — stage orchestrator (owns order, parallelism, abort/degrade policy, commit gate, banners).
2. **`llm-router`** — local Anthropic-compatible proxy (pins models by stage header; performs Build/Clean failover to Ollama; refuses Plan/Audit failover).

Qwen never appears in a healthy production stage path. Failover is explicit, logged, and surfaced as **DEGRADED MODE**.

## 5. Components

### 5.1 `feature-pipeline` (new)

**Responsibility:** Drive one feature request through the four stages.

**CLI (proposed):**

```bash
feature-pipeline [--dry-run] [--no-commit] [--max-workers N] "description of the feature"
# or
feature-pipeline [--dry-run] [--no-commit] -f path/to/request.md
```

**Working directory:** current repo root (must be a git checkout).

**Artifacts directory:** `.pipeline/<run-id>/`

| File | Contents |
|------|----------|
| `meta.json` | run id, start time, models, degraded flags |
| `repo-scan.json` | tree summary + detected dependency manifests |
| `plan.json` | Opus task list (structured) |
| `build/<task-id>.json` | per-worker result (files touched, status) |
| `clean-report.json` | Haiku cleanup summary |
| `audit.json` | Opus pass/fail + findings |
| `banner.txt` | HUMAN-VISIBLE status including DEGRADED if set |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Audit passed; commit performed (unless `--no-commit`) |
| 2 | Plan aborted (hosted unavailable / bad plan) |
| 3 | Audit failed or Audit aborted |
| 4 | Build/Clean completed only in degraded mode and Audit still required hosted — if Audit cannot run, exit 3; if Audit passes after degraded build, exit 0 with warning |
| 5 | Operator interrupted / invalid args |

### 5.2 `llm-router` (extend existing)

**Listen:** `127.0.0.1:11437` (unchanged).

**Stage header:** `x-pipeline-stage: plan|build|clean|audit`  
**Optional override:** `x-route: local|plan|build|clean|audit`  
**Failover allow:** implied by stage — Build/Clean yes; Plan/Audit no.

**Model pins (env, defaults):**

| Env | Default |
|-----|---------|
| `ROUTER_PLAN_MODEL` | `claude-opus-4-6` (or current Opus id available to the account) |
| `ROUTER_BUILD_MODEL` | `claude-sonnet-4-6` |
| `ROUTER_CLEAN_MODEL` | `claude-haiku-4-5` (or current Haiku id) |
| `ROUTER_AUDIT_MODEL` | same as plan / Opus |
| `ROUTER_LOCAL_MODEL` | `qwen-fast` |
| `OLLAMA_UPSTREAM` | `http://127.0.0.1:11434` |
| `ANTHROPIC_UPSTREAM` | `https://api.anthropic.com` |

Exact Anthropic model id strings are configurable so account availability does not block the design.

**Failover triggers (Build/Clean only):** HTTP `429`, `402`, connection errors, and Anthropic auth/rate errors returned by upstream.  
**On failover:** rewrite to local model, set response header `x-router-degraded: true`, log `degraded=true reason=…`.  
**Plan/Audit on same failures:** return error to client; **do not** call Ollama.

**Heuristic easy/hard routing** (existing `claude-routed` behavior) remains for ad-hoc Claude Code sessions **outside** `feature-pipeline`. Pipeline requests always send `x-pipeline-stage` and bypass the heuristic scorer.

### 5.3 Local Qwen (`qwen-fast`)

- Already defined via `modelfiles/qwen-code-14b.Modelfile` (`qwen3:14b`, lean `num_ctx`).
- Used by: `claude-local` / ad-hoc side chat; Build/Clean failover only.
- Not used for Plan or Audit under any circumstance.

## 6. Stage contracts

### 6.1 Plan (Opus) — non-negotiable hosted

**Input:** feature description + `repo-scan.json` (file tree truncated, lockfile/package names, top-level layout).

**Output (`plan.json`):**

```json
{
  "summary": "one paragraph",
  "tasks": [
    {
      "id": "t1",
      "title": "…",
      "files": ["path/a.ts", "path/b.ts"],
      "instructions": "…",
      "depends_on": []
    }
  ],
  "clean_hints": ["normalize imports in …"],
  "risks": ["…"]
}
```

**Rules:**

- Tasks must be partitionable for parallel Sonnet workers (minimal overlapping files).
- If Opus call fails → **ABORT** with fatal banner; no Build.
- If plan JSON invalid / empty tasks → **ABORT** (treat as Plan failure).

### 6.2 Build (Sonnet) — parallel; may degrade

**Input:** one plan task per worker.

**Execution:**

- Ready tasks (deps satisfied) run with `--max-workers` (default 3).
- Each worker applies file edits in the repo (Claude Code tool loop **or** Messages API + explicit patch application — implementation plan will pick one; preference: Claude Code `--print` / headless with model pin if reliable, else Messages + unified diff apply).
- Worker results written under `.pipeline/<run-id>/build/`.

**Failover:**

- If hosted Sonnet fails for a worker → retry that worker once via local Qwen through router with stage `build`.
- Set run-level `degraded=true`; print **DEGRADED MODE** banner; continue remaining tasks.
- Do not cancel the whole pipeline solely because one Build worker degraded.

### 6.3 Clean (Haiku) — may degrade

**Input:** list of files touched in Build + `clean_hints` from plan.

**Job:** import path fixes, internal string/format cleanup, light doc touch-ups. No new features. No architecture changes.

**Failover:** same as Build (Qwen allowed, `degraded=true`, banner).

**Ordering:** Clean runs **after** all Build workers for the run complete (not interleaved with unfinished Build), so Haiku sees a stable file set. Parallelism inside Clean is optional (by file group).

### 6.4 Audit (Opus) — non-negotiable hosted

**Input:** plan summary, file diff vs run start (`git diff`), clean report, `degraded` flag.

**Output (`audit.json`):**

```json
{
  "pass": true,
  "findings": [],
  "commit_message": "feat: …"
}
```

**Rules:**

- If Opus unavailable → **ABORT**; **do not commit** even if Build looked fine.
- If `pass: false` → block commit; print findings + diff summary.
- If `pass: true` → `git add` touched paths (or `git add -u` scoped) + `git commit` with `commit_message` unless `--no-commit`.
- Degraded Build/Clean does **not** skip Audit; Audit must still be hosted Opus.

## 7. Failover & banners

**Fatal (Plan/Audit):**

```
════════════════════════════════════════
 CRITICAL FAILURE — PIPELINE ABORTED
 Stage: plan|audit
 Reason: 429|402|connection|invalid-output
 Local Qwen is NOT used for this stage.
════════════════════════════════════════
```

**Degraded (Build/Clean):**

```
════════════════════════════════════════
 DEGRADED MODE
 Stage: build|clean
 Hosted model unavailable → local qwen-fast
 degraded=true
 Audit still requires hosted Opus.
════════════════════════════════════════
```

Banners go to stderr and `banner.txt`. Structured logs also append JSON lines to `.pipeline/<run-id>/events.jsonl`.

## 8. Security & privacy

- Hosted calls: **Anthropic API only** (direct or via local `llm-router` → Anthropic).
- Local calls: **Ollama on 127.0.0.1 only**.
- No third-party LLM gateways.
- API key: `ANTHROPIC_API_KEY` or `ROUTER_ANTHROPIC_API_KEY`; placeholder `ollama` never counts as a real key.
- `.pipeline/` should be gitignored.
- Pipeline does not push; commit is local only unless the operator pushes.

## 9. Operator workflow (Mac)

```bash
# one-time
./scripts/setup-14b-router.sh   # qwen-fast + llm-router LaunchAgent
export ANTHROPIC_API_KEY=sk-ant-...

# each feature
cd /path/to/work-repo
llm-router                      # if not already running
feature-pipeline "Add X with tests"
# or dry-run / no commit while validating
feature-pipeline --dry-run --no-commit "…"
```

Ad-hoc questions stay on `claude-local` and never enter `.pipeline/`.

## 10. Testing strategy

| Layer | What |
|-------|------|
| Unit | Stage→model pin map; Plan/Audit refuse failover; Build/Clean allow failover |
| Unit | Plan JSON schema validation; audit pass/fail commit gate |
| Integration (dry-run) | Fake upstreams: Anthropic mock returns 429 on Build → assert Qwen path + `degraded=true`; Plan 429 → abort, no Ollama call |
| Manual on Mac | One small real feature with key present; one run with key revoked mid-Build |

No requirement to hit real Anthropic from the cloud agent VM for merge readiness; dry-run + mocks are enough in CI/agent.

## 11. File layout (to add / change)

| Path | Action |
|------|--------|
| `scripts/feature-pipeline.py` | **New** orchestrator |
| `scripts/feature-pipeline` | **New** thin launcher |
| `scripts/llm-router.py` | **Extend** stage pins + failover policy |
| `scripts/test-pipeline-*.sh` | **New** unit/integration checks |
| `.gitignore` | Ignore `.pipeline/` |
| `README.md` | Short “Feature pipeline” section (not the research doc) |
| `docs/LOCAL-LLM-RESEARCH.md` | **Do not update** in this workstream |

## 12. Implementation phases (after spec approval)

1. Router stage pins + Plan/Audit abort vs Build/Clean failover (with tests).  
2. Orchestrator dry-run: scan → mock plan → mock build/clean/audit → banners/exit codes.  
3. Live Anthropic/Ollama wiring + commit gate.  
4. Parallel Build workers + README operator section.

## 13. Open decisions (fixed by this design)

| Topic | Decision |
|-------|----------|
| Plan/Audit failover to Qwen? | **No — abort** |
| Build/Clean failover to Qwen? | **Yes — explicit degraded** |
| Clean before Build finishes? | **No — Clean after all Build** |
| Cursor Agent as runner? | **No** |
| Claude Desktop as runner? | **No** |
| Multi-provider gateways? | **No** |
| Commit on Audit pass? | **Yes** (disable with `--no-commit`) |
| Push? | **No** (operator only) |

## 14. Success criteria

1. Healthy run uses only Opus/Sonnet/Haiku for the four stages.  
2. Killing Anthropic mid-Plan aborts with fatal banner and zero Qwen Plan calls.  
3. Killing Anthropic mid-Build marks degraded, finishes via Qwen, still requires Opus Audit.  
4. Audit fail blocks commit; Audit pass creates a local commit.  
5. Ad-hoc `claude-local` remains available and does not write pipeline artifacts.
