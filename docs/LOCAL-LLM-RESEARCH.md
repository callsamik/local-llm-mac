# Local coding LLM on Apple Silicon — research notes

**Audience:** engineering team  
**Hardware under test:** MacBook Pro, Apple Silicon M3 Pro, 36 GB unified memory (plugged in)  
**Date of findings:** late August 2026  
**Goal:** keep coding/agent work productive while Cursor and Claude balances are exhausted, then keep a cheap local default whenever balance is back.

This document is the research record: decisions, dead ends, architecture, measured behavior, and recommendations. Day-to-day install steps live in [`README.md`](./README.md).

---

## 1. Executive summary

| Question | Finding |
|---|---|
| Can we run a useful coding agent fully local on this Mac? | **Yes.** Ollama + **Qwen 3.8 27B** (~18 GB) fits in 36 GB with a ~49k context. |
| Best $0 coding path | Terminal **`claude-local`** (Claude Code CLI → Ollama). Not Cursor Agent. Not signed-in Claude Desktop. |
| Does Claude Desktop work with local Qwen? | **Only in third-party gateway mode**, with a rewrite proxy (or a future Ollama Apps mapping that actually accepts the Claude model ids). |
| Does a local model bypass Anthropic’s monthly spend limit in Desktop? | **No, if you stay signed into Claude.ai.** Spend limit is an account gate. Local inference does not clear it. |
| Why did “hello” take ~1 minute in Desktop? | Model was warm on GPU. Latency was **Desktop’s large system/tools stack + thinking**, not Ollama. Raw curl answered in milliseconds. |

---

## 2. Constraints and goals

### 2.1 Constraints

- Cursor / Claude balances exhausted (shared team situation at time of writing).
- Office Mac; code should stay on the laptop (no cloud gateway that can see repo contents).
- Prefer long agent runs (plan → edit → test → repeat) with controllable reasoning effort.
- Whenever balance is back: keep local as the cheap default; escalate to cloud only when stuck.

### 2.2 Non-goals

- Replacing Anthropic quality for every task.
- Running Opus-class models locally on 36 GB.
- Keeping Claude Desktop **cloud chat history** while on a free local model (those are different Desktop modes).

---

## 3. Model and stack decisions

### 3.1 Model: Qwen 3.8 27B

| Option | Verdict |
|---|---|
| **Qwen 3.8 27B** (`qwen3.8:27b`) | **Chosen.** Same footprint class as 3.6 27B (~18 GB), stronger for agentic coding. Alias used: `qwen-code`. |
| Optional MLX quant (`qwen3.8:27b-nvfp4`) | Same size class; usually faster on Apple Silicon (`./install.sh --mlx`). |
| Larger models (70B+) | Rejected for comfort on 36 GB with OS + IDE + ~49k agent context. |

**Defaults baked into `qwen-code`:**

- `num_ctx` **49152** (32k was too small for Claude Code’s system+tools prompt; see §8.5)  
- Thinking on, **medium** reasoning effort (via system prompt)  
- Keep-alive so the model stays loaded (`OLLAMA_KEEP_ALIVE=-1`)

### 3.2 Runtime: Ollama

- Bind API to `127.0.0.1:11434` only (localhost).
- Enable MLX, flash attention, single parallel slot.
- Persist env via LaunchAgent: `~/Library/LaunchAgents/com.ollama.mac-env.plist`.

### 3.3 Rejected approaches

| Approach | Why rejected |
|---|---|
| **OmniRoute / cloud LLM gateways** | Can see office code; defeats “stay local.” |
| **Cursor Agent as the $0 path** | Agent traffic often goes through Cursor’s servers; `localhost` Ollama frequently unreachable; Auto/Claude/GPT still bill Cursor. |
| **Global `ANTHROPIC_BASE_URL=…11434` in `~/.zshrc`** | Breaks real `claude` whenever balance is back; every session would hit Ollama by accident. |
| **Relying on Ollama → Apps → Claude (port 11435) alone** | On the tested builds this returned `unknown Claude model "claude-sonnet-4-6"`. |

---

## 4. Architecture (ports and roles)

```text
┌──────────────────────────────┐
│  Claude Code CLI             │  claude-local
│  (terminal agent)            │───────► 127.0.0.1:11434  Ollama  (qwen-code)
└──────────────────────────────┘              ▲
                                              │ Anthropic /v1/messages
┌──────────────────────────────┐              │
│  Claude Desktop              │              │
│  (gateway / 3P mode only)    │──► :11436 ───┘
│  sends claude-sonnet-4-6     │   rewrite proxy
└──────────────────────────────┘   (advertise Claude ids → rewrite → qwen-code)

┌──────────────────────────────┐
│  Ollama Apps → Claude        │──► :11435  Claude sidecar
│  (do NOT use on broken builds)│   catalogs real Claude slots;
└──────────────────────────────┘   rejected our local aliases
```

| Port | Process | Role |
|---|---|---|
| **11434** | Ollama | Real local API. OpenAI + Anthropic-compatible `/v1/messages`. Serves `qwen-code`. |
| **11435** | Ollama Claude sidecar | Started by **Apps → Claude**. Catalog of Claude slots. Source of `unknown Claude model "…"`. |
| **11436** | `claude-desktop-proxy` | Our rewrite proxy. Desktop gateway URL. |

---

## 5. Claude Desktop findings (deep dive)

### 5.1 Why Desktop needs Anthropic-looking model names

Claude Desktop’s third-party gateway discovery filters models to ones that look like Claude (or are marked with `anthropic_family_tier`). Native ids like `qwen-code` are dropped (“0 usable models”), then Desktop falls back to something like `claude-sonnet-4-6`.

Copying weights with `ollama cp qwen-code claude-sonnet-4-6` helps **11434**, but **does not** teach the **11435** sidecar to accept that id.

### 5.2 Error: `unknown Claude model "claude-sonnet-4-6"` on 11435

```text
400 http://127.0.0.1:11435/v1/messages
{"type":"error","error":{"type":"invalid_request_error",
 "message":"unknown Claude model \"claude-sonnet-4-6\""}}
```

**Root cause:** Desktop was pointed at Ollama’s Claude sidecar. That process only accepts models from its own Claude catalog / mapping UI — not arbitrary local aliases.

**Mitigation we shipped:**

1. Turn **Ollama → Apps → Claude → Off** (so Desktop is not forced onto 11435).
2. Run rewrite proxy on **11436**.
3. Point Desktop gateway at `http://127.0.0.1:11436`.
4. Advertise `claude-sonnet-4-6` (tier `sonnet`) on `GET /v1/models`.
5. Rewrite request `model` to `qwen-code` before forwarding to 11434.

### 5.3 Why we turned Apps → Claude Off

That toggle **is** the 11435 sidecar. Leaving it on kept Desktop on the path that returned the 400. Ollama.app itself stays running; only the Claude integration is off.

**Future caveat:** if a newer Ollama build maps Sonnet → Qwen correctly inside Apps UI and no longer returns `unknown Claude model`, that path may replace our proxy for **name conversion**. It still does **not** solve Anthropic spend limits while signed in (see §6).

### 5.4 Config UI: “Couldn’t load configuration” / blank screen

Observed state:

- `~/Library/Application Support/Claude-3p/configLibrary/` existed.
- `_meta.json` was ~20 bytes with **`appliedId: null`** → no configuration applied.
- No machine MDM plist at `/Library/Managed Preferences/com.anthropic.claudefordesktop.plist`.

**Fix:** write a valid gateway config JSON + `_meta.json` with a non-null `appliedId`, pointing at `http://127.0.0.1:11436`, then fully quit and relaunch Desktop.

### 5.5 Gateway timeout on `/v1/messages` after successful discovery

Symptom: “Model discovery — found 4 models” but Inference timed out on `/v1/messages`.

Contributing factors:

1. **Cold load** of 17–18 GB weights can exceed Desktop’s client timeout.
2. Proxy originally streamed/kept HTTP/1.1 alive without a clean `Content-Length` / `Connection: close`, which made Desktop wait until abort.

**Mitigations:** warm with `ollama run qwen-code "pong"` first; proxy updated to close responses and stream SSE when requested.

### 5.6 Seeing “Qwen 3.8” in the Desktop footer

That label means the **routing target / display name** for the slot is Qwen. It does **not** mean:

- Anthropic billing is off, or  
- the rewrite layer is unused.

If gateway base URL is still `11436`, the proxy is what made that Claude-shaped slot usable.

---

## 6. Anthropic login vs local inference (critical)

This was the most important product finding for the team.

### 6.1 Two layers

| Layer | What it controls |
|---|---|
| **Model routing** (proxy / Ollama mapping) | Which weights answer (`qwen-code` vs Claude API). |
| **Claude.ai sign-in** | Identity, **cloud chat history**, **monthly spend / plan gates**. |

They are not stacked. A working local route does not disable the account gate.

### 6.2 Spend limit while using a “local” model

| Desktop state | Anthropic spend limit applies? |
|---|---|
| Signed in to Claude.ai (footer may still say Qwen) | **Yes** |
| Continue with Gateway / signed out, proxy → local Qwen | **No** (no Anthropic inference billing on that path) |
| Terminal `claude-local` | **No** |

Observed: after gateway + proxy worked, **signed-in** Desktop still showed **“You’ve reached your monthly spend limit.”**

### 6.3 Logging out and lost context

Signing out / switching to gateway mode moves Desktop into **Cowork-on-3P**:

- History for that mode is **local**, not the Claude.ai cloud thread.
- Old cloud threads stay with the Anthropic account; they are not merged into gateway mode.
- Repo files on disk are untouched.

**Implication:** you cannot keep the Anthropic cloud conversation **and** dodge the spend limit. Whenever balance is back, sign back into normal Claude to recover cloud threads.

### 6.4 Would a fixed Ollama Apps mapping allow “stay logged in”?

**No** for spend-cap bypass. It would only remove the need for our proxy for name conversion. Logged-in + exhausted plan still blocks.

---

## 7. Cursor-specific findings

| Path | Bills? | Notes |
|---|---|---|
| Cursor Agent Auto / Claude / GPT | Yes (Cursor) | Not a $0 path. |
| Cursor Agent → localhost Ollama | Unreliable | Agent often runs via Cursor’s servers; cannot reach laptop Ollama. |
| Cursor Tab | Can still use cloud | Turn off if stretching remaining quota. |
| Terminal outside Cursor | — | Preferred while balance is exhausted. |

---

## 8. Performance findings (M3 Pro 36 GB)

### 8.1 Runtime health (good)

```text
NAME                SIZE     PROCESSOR    CONTEXT    UNTIL
qwen-code:latest    17 GB    100% GPU     32768      Forever
```

Interpretation: model resident, Metal/GPU path, keep-alive working. Cold start was **not** the ongoing “hello is slow” issue.

### 8.2 Latency split

| Client | Rough result for a trivial prompt |
|---|---|
| Raw `curl` to `11434` with `/no_think` | **Milliseconds** (after warm) |
| Claude Desktop chat “hello” | **~1 minute** |

**Conclusion:** Ollama + Qwen are fine for short replies. Desktop wraps large system prompts, tools/skills, and (by default) model thinking. That dominates wall time.

### 8.4 Memory budget

~49k context + ~18 GB weights is the comfort line on 36 GB with macOS + IDE. If Activity Monitor memory pressure goes yellow/red, close browsers/other apps before raising context further.

### 8.5 `500 no user query found in messages` (Claude Code / cmux)

**Symptom:** `claude-local` starts, first real query fails with retries:

```text
500 no user query found in messages · Retrying …
```

**Cause (Ollama + Qwen 3.8):** Claude Code sends a large opening payload (system prompt + dozens of tool schemas, often ~35k+ tokens). With `num_ctx` 32768, Ollama silently truncates and can drop the user turn; the Qwen 3.8 renderer then errors with this misleading 500. Same class of bug as [ollama#17778](https://github.com/ollama/ollama/issues/17778) / [ollama#17754](https://github.com/ollama/ollama/issues/17754). Not a cmux bug.

**Fix on this Mac:** raise context to **49152** on the `qwen-code` alias (fits 36 GB with the 27B Q4/MLX weights). Upgrade Ollama when renderer fixes land. Also pin Haiku/Sonnet helper model env vars to `qwen-code` in `claude-local`.

### 8.6 Mitigations for chat latency

- Prefix short chats with `/no_think`.
- Prefer `claude-local` for coding agents (closer to raw Ollama cost).
- Optional: MLX quant (`--mlx`).
- Optional later: lower `num_ctx` for chat-only aliases (agent alias stays at 49k).

---

## 9. Recommended operating modes

### 9.1 While balance is exhausted

1. **Primary:** `claude-local` inside the repo.  
2. **Optional UI:** Claude Desktop **Continue with Gateway** → `http://127.0.0.1:11436` (accept that cloud threads are not available in this mode).  
3. **Avoid:** plain `claude`, Cursor Agent cloud models, Desktop signed into Anthropic while capped.

### 9.2 Whenever balance is back

1. Keep `claude-local` as the cheap daily default.  
2. Use real `claude` / Cursor cloud when local is stuck.  
3. Do **not** leave a global `ANTHROPIC_BASE_URL` pointing at Ollama.

### 9.3 Commands cheat sheet

```bash
# Health
curl -s http://127.0.0.1:11434/api/tags
ollama ps
curl -s http://127.0.0.1:11436/health

# Warm model
ollama run qwen-code "Reply with the single word pong."

# Coding agent (free / local)
cd /path/to/repo && claude-local

# Fast smoke (no Desktop)
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"qwen-code","messages":[{"role":"user","content":"/no_think\nhello"}],"max_tokens":32}'
```

---

## 10. Repo artifacts

| Path | Purpose |
|---|---|
| `install.sh` | Self-contained Mac installer (Ollama env, model, `claude-local`, Desktop proxy LaunchAgent). |
| `scripts/claude-local` | Session-only env override → Ollama; does not rewrite `~/.zshrc` Anthropic setup. |
| `scripts/claude-desktop-proxy.py` | 11436 rewrite proxy. |
| `scripts/claude-desktop-proxy` | Launcher wrapper. |
| `modelfiles/qwen-code.Modelfile` | Alias parameters + medium-reasoning system prompt. |
| `README.md` | Install / run guide. |
| This file | Research findings for the team. |

Installer also embeds the proxy for machines that only copy `install.sh`.

---

## 11. Open questions / watch items

1. Will a future Ollama Apps → Claude mapping accept Desktop’s Claude ids and map them to local Qwen without a custom proxy?  
2. Can Desktop gateway mode ever attach to prior Claude.ai threads? (Today: no evidence; treat as separate stores.)  
3. Best chat-only Modelfile (lower ctx, think off) vs agent alias — may be worth a second Ollama tag (`qwen-chat`) later.  
4. Team policy: when is local Qwen “good enough” vs escalate to Claude/GPT?

---

## 12. Bottom line for the team

1. **Local coding works** on M3 Pro 36 GB with Qwen 3.8 27B + Ollama.  
2. **`claude-local` is the reliable $0 agent.** Cursor Agent is not.  
3. **Claude Desktop + local Qwen requires gateway mode + name rewriting** (our 11436 proxy, unless Ollama’s Apps path is fixed).  
4. **Signed-in Desktop still enforces Anthropic spend limits** even when the UI shows Qwen.  
5. **Desktop is slow for trivial chat** because of its prompt/tools/thinking wrapper; raw Ollama is fast when the model is warm on GPU.

For install and daily commands, see [`README.md`](./README.md).
