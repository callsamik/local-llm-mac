# Local coding LLM on Apple Silicon — research notes

**Audience:** engineering team  
**Hardware under test:** MacBook Pro, Apple Silicon M3 Pro, 36 GB unified memory (plugged in)  
**Date of findings:** late August 2026  
**Goal (original spike):** keep coding/agent work productive while Cursor and Claude balances are exhausted, then keep a cheap local default whenever balance is back.

**Goal (revised after spike — proposed):** treat local Qwen as a **first-class lane for easy/medium tasks**, not only an out-of-tokens fallback. Route harder / reasoning-heavy work to hosted Claude/GPT. Prefer a **~14B** local model on 36 GB machines so KV cache, long context, and other desktop work do not thrash unified memory (27B fits, but leaves little headroom).

This document is the research record: decisions, dead ends, architecture, measured behavior, and recommendations. Day-to-day install steps live in [`README.md`](./README.md).

---

## 1. Executive summary

| Question | Finding |
|---|---|
| Can we run a useful coding agent fully local on this Mac? | **Yes.** Ollama + **Qwen 3.8 27B** (~18 GB) fits in 36 GB with a ~49k context. |
| Which model answers? | Local **`qwen-code`** (Qwen 3.8 27B on Ollama). Not Claude cloud, not Cursor. |
| Best $0 coding path | Terminal / **cmux** → **`claude-local`** (Claude Code CLI → Ollama). Not Cursor Agent. Not signed-in Claude Desktop. |
| Can Cursor use local Qwen with **no Cursor balance**? | **Effectively no.** Agent/Chat/BYOK/custom models are gated by Cursor’s plan/usage. A tunnel to Ollama does not unlock “0 limit left.” Use Cursor as an editor only; run the agent in cmux. |
| Does Claude Desktop work with local Qwen? | **Only in third-party gateway mode**, with a rewrite proxy (or a future Ollama Apps mapping that actually accepts the Claude model ids). |
| Does a local model bypass Anthropic’s monthly spend limit in Desktop? | **No, if you stay signed into Claude.ai.** Spend limit is an account gate. Local inference does not clear it. |
| Why did “hello” take ~1 minute in Desktop? | Model was warm on GPU. Latency was **Desktop’s large system/tools stack + thinking**, not Ollama. |
| Why did Claude Code / cmux take ~11 minutes? | **Thinking is on by default** for Qwen 3.8. Reasoning tokens fill the budget before `content`. Prompt `/no_think` is **not** enough — use `think: false` / `--think=false`. |
| `500 no user query found in messages`? | Claude Code’s opening prompt overflowed **32k** context. Fix: **`num_ctx` 49152**. Not a cmux bug. |
| Is 27B the right long-term size on 36 GB? | **Questionable for multitasking.** It runs, but KV cache + ~49k context + thinking + IDE/browser pressure the machine. **~14B is the next spike** for headroom. |
| Better product goal than “fallback when out of tokens”? | **Yes — local/cloud router:** easy/medium → local Qwen; hard / high-reasoning → hosted model. |

---

## 2. Constraints and goals

### 2.1 Constraints

- Cursor / Claude balances exhausted (shared team situation at time of writing).
- Office Mac; code should stay on the laptop (no cloud gateway that can see repo contents).
- Prefer long agent runs (plan → edit → test → repeat) with controllable reasoning effort.
- Whenever balance is back: keep local as the cheap default; escalate to cloud only when stuck.
- **Revised:** leave enough RAM headroom for normal laptop use (IDE, browser, meetings) — do not size the local model to the absolute maximum that still boots.
- **Revised:** design for **intelligent routing** (local vs hosted), not only emergency offline/fallback.

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
│  cmux workspace(s)           │  host many Claude Code sessions
│  run: claude-local           │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
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

| Path | Works with $0 Cursor balance? | Notes |
|---|---|---|
| Cursor Agent Auto / Claude / GPT | No | Bills Cursor; blocked when usage is exhausted. |
| Cursor Agent → `localhost` Ollama | No | Agent traffic goes through Cursor’s servers; they cannot reach your laptop’s `127.0.0.1`. |
| Cursor + Override OpenAI Base URL → Ollama via HTTPS tunnel | Only if Cursor plan/usage still allows BYOK/custom models | Still not a pure air-gap (prompts may traverse Cursor). See §7.2–7.3. |
| Cursor Tab | Often still cloud | Can still consume Cursor quota; turn off while stretching. |
| Cursor as **editor only** | Yes | Open files, diffs, git — leave Agent/Auto alone. |
| **cmux** + `claude-local` | Yes | Reliable $0 coding agent on local Qwen. |

### 7.1 Why Cursor is a poor $0 agent host

Cursor’s Agent / Chat / Edit pipeline builds prompts on **Cursor’s backend**. Even with “your own” OpenAI-compatible endpoint:

1. The backend must call that endpoint — so **`http://127.0.0.1:11434` is unreachable** from their servers.
2. Product policy: **BYOK / Override Base URL / manual custom models require an active paid plan** (Pro/Teams). On Free, or when usage shows **0 limit left**, custom/local routes are typically **blocked server-side** (forum-confirmed behavior; not fixed by downgrading the app).
3. Therefore: **no Cursor balance ⇒ do not expect Agent to run on local Qwen.** Use cmux + `claude-local` instead.

### 7.2 If you still want Cursor → Ollama (when balance/plan allows)

Only attempt this when Cursor will actually accept a custom model (active Pro/Teams and usage not blocking BYOK).

1. Keep Ollama up (`ollama ps` → `qwen-code`, GPU, `CONTEXT 49152`).
2. Expose Ollama with a **public HTTPS** tunnel (Cursor cannot use raw localhost):

```bash
ngrok http 11434
# or Cloudflare Tunnel / similar
```

3. Cursor **Settings → Models**:
   - Enable **Override OpenAI Base URL**
   - Base URL: `https://YOUR-TUNNEL/v1` (must end with `/v1`)
   - API key: `ollama` (any non-empty placeholder)
   - Add model name exactly: **`qwen-code`** (no `:` — Cursor strips characters like `:` from tags such as `qwen3.8:27b`)
4. Select `qwen-code` in Chat/Agent (not Auto / Claude).
5. When you want built-in Claude/GPT again: **turn Override Off**.

**Caveats:**

- Prompt/context may still pass through Cursor’s servers — **not a pure local/air-gapped path** for office code.
- A tunnel publishes a route to your laptop API; use auth, short-lived URLs, and tear it down when done.
- Qwen thinking defaults on — Agent turns can still be slow unless thinking is disabled on the Ollama side (§8.3).
- This does **not** replace `claude-local`; it only wires Cursor’s UI when the account allows it.

### 7.3 When Cursor balance is exhausted (recommended workflow)

| Tool | Role |
|---|---|
| **cmux + `claude-local`** | Coding agent → local `qwen-code` |
| **Cursor** | Editor only (files, git, review) |
| **Claude Desktop** | Optional gateway mode only; not signed-in Anthropic while capped |

Do **not** spend time on tunnels or Override Base URL expecting them to bypass “You’ve hit your limit.” That limit is Cursor’s gate on Agent features.

Whenever Cursor balance is back: use Cursor cloud for hard tasks; keep `claude-local` as the cheap daily default.

---

## 7.4 cmux + Claude Code CLI

[cmux](https://cmux.com) is a macOS terminal built for many AI coding agents in parallel. It does **not** replace Claude Code; it hosts it.

**Working setup we used:**

1. Ollama up; `qwen-code` on PATH checks: `curl` tags + `which claude-local`.
2. Open a cmux workspace in the target repo.
3. Run **`claude-local`** (not `claude`).
4. Optional: enable Claude integration / `cmux hooks setup` for unread rings when the agent needs input.
5. Parallel work = one workspace per task, each with its own `claude-local`.

**Pitfalls:**

| Symptom | Cause | Fix |
|---|---|---|
| Spend / Anthropic errors in cmux | Ran plain `claude` | Use `claude-local` |
| `500 no user query found in messages` | Context 32k too small for Claude Code tools prompt | Recreate alias with `num_ctx 49152` (§8.5) |
| `API error · Retrying` with no detail | Claude Code hides the Ollama body | Probe with `curl` / `claude -p … 2>&1` (§8.7) |
| Multi-minute reply while `ollama ps` shows GPU + Forever | Thinking on by default | `--think=false` / `think: false` (§8.3) |
| Some cmux builds strip `ANTHROPIC_*` | Wrapper clears inherited auth env | Prefer `claude-local` (sets env in-process) |

---

## 8. Performance findings (M3 Pro 36 GB)

### 8.1 Runtime health (good)

After the 49k recreate:

```text
NAME                SIZE     PROCESSOR    CONTEXT    UNTIL
qwen-code:latest    17 GB    100% GPU     49152      Forever
```

Interpretation: model resident, Metal/GPU path, keep-alive working. When this is healthy, a multi-minute delay is **not** cold load.

### 8.2 Latency split

| Client | Rough result for a trivial prompt |
|---|---|
| Raw `curl` `/v1/chat/completions` (warm) | **~3 s** wall time observed |
| Same request: `/no_think` in user text | Still emits **`reasoning`**, often empty **`content`** if `max_tokens` is small |
| Claude Desktop chat “hello” | **~1 minute** (Desktop wrapper + thinking) |
| Claude Code / cmux with thinking default | Observed **~11 minutes** for a simple turn |

**Conclusion:** weights + GPU path are fine. Wall time is dominated by **thinking traces** and large client system/tool prompts.

### 8.3 Thinking behavior (critical)

Qwen 3.8 is a thinking model. In Ollama, **thinking is on by default**.

**Measured OpenAI-compat response** (`/no_think` in the user string, `max_tokens: 16`):

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "",
      "reasoning": "The user wants me to simply say \"pong\". This is a very simple request"
    },
    "finish_reason": "length"
  }],
  "usage": { "prompt_tokens": 58, "completion_tokens": 16, "total_tokens": 74 }
}
```

Findings:

1. Prompt text **`/no_think` is unreliable** for this stack — reasoning still ran.
2. All completion tokens went into **`reasoning`**; **`content` stayed empty**; finish reason **`length`**.
3. Claude Code’s Anthropic `/v1/messages` path with a huge system+tools prompt + default thinking is why sessions feel hung or take ~11 minutes.
4. Correct disable switch (Ollama):

```bash
# CLI
ollama run qwen-code --think=false "Say pong"

# API
curl http://127.0.0.1:11434/api/chat -d '{
  "model": "qwen-code",
  "think": false,
  "stream": false,
  "messages": [{"role": "user", "content": "Say pong"}]
}'

# Anthropic-compat attempt
curl http://127.0.0.1:11434/v1/messages \
  -H 'content-type: application/json' -H 'x-api-key: ollama' \
  -d '{"model":"qwen-code","max_tokens":64,"thinking":{"type":"disabled"},"messages":[{"role":"user","content":"Say pong"}]}'
```

**Operational guidance:** daily agent work with **`think: false`** (or a future `qwen-code-fast` alias). Turn thinking back on only for hard multi-file bugs. Do not rely on `/no_think` in the prompt alone.

### 8.4 Memory budget

~49k context + ~18 GB weights is the comfort line on 36 GB with macOS + IDE. If Activity Monitor memory pressure goes yellow/red, close browsers/other apps before raising context further. First load after raising `num_ctx` can take minutes while KV/context allocates even though `ollama ps` already lists the model.

### 8.5 `500 no user query found in messages` (Claude Code / cmux)

**Symptom:** `claude-local` starts, first real query fails with retries:

```text
500 no user query found in messages · Retrying …
```

**Cause (Ollama + Qwen 3.8):** Claude Code sends a large opening payload (system prompt + dozens of tool schemas, often ~35k+ tokens). With `num_ctx` 32768, Ollama silently truncates and can drop the user turn; the Qwen 3.8 renderer then errors with this misleading 500. Same class of bug as [ollama#17778](https://github.com/ollama/ollama/issues/17778) / [ollama#17754](https://github.com/ollama/ollama/issues/17754). Not a cmux bug.

**Fix on this Mac:** raise context to **49152** on the `qwen-code` alias (fits 36 GB with the 27B Q4/MLX weights). Confirm with `ollama ps` → `CONTEXT 49152`. Upgrade Ollama when renderer fixes land. Also pin Haiku/Sonnet helper model env vars to `qwen-code` in `claude-local`.

**Recreate without needing the git checkout:**

```bash
cat > /tmp/qwen-code.Modelfile <<'EOF'
FROM qwen3.8:27b
PARAMETER num_ctx 49152
PARAMETER num_predict 8192
PARAMETER temperature 0.6
PARAMETER top_p 0.95
PARAMETER top_k 20
PARAMETER repeat_penalty 1.05
SYSTEM """You are a local coding agent. Think carefully, then finish the job. Reasoning effort is medium. Prefer small patches. Do not claim you ran a command you did not run."""
EOF
ollama create qwen-code -f /tmp/qwen-code.Modelfile
```

If MLX was installed with `--mlx`, use `FROM qwen3.8:27b-nvfp4` instead.

### 8.6 Mitigations for latency

- Disable thinking: `--think=false` / `"think": false` (preferred).
- Do **not** trust `/no_think` alone on this model.
- Prefer `claude-local` in cmux/terminal over Claude Desktop for coding.
- Optional: MLX quant (`--mlx`).
- Optional later: second alias `qwen-code-fast` with thinking off by default; keep `qwen-code` for hard bugs.

### 8.7 Diagnosing opaque `API error · Retrying`

Claude Code / cmux often only shows `API error · Retrying in 0s · attempt N/10`. Surface the real failure:

```bash
# Direct Anthropic-compat probe
curl -sS -w "\nHTTP %{http_code}\n" --max-time 120 \
  http://127.0.0.1:11434/v1/messages \
  -H 'content-type: application/json' -H 'x-api-key: ollama' \
  -d '{"model":"qwen-code","max_tokens":64,"messages":[{"role":"user","content":"Say pong"}]}'

# One-shot Claude Code
ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY= \
ANTHROPIC_BASE_URL=http://127.0.0.1:11434 \
claude --model qwen-code -p "Say pong only" 2>&1 | tee /tmp/claude-local-err.txt

# Ollama log
tail -n 80 ~/.ollama/logs/server.log
```

If `/v1/messages` hangs for minutes while `ollama ps` already shows GPU + Forever, treat it as **thinking**, not a dead server — interrupt and retest with `think: false`.

---

## 9. Recommended operating modes

### 9.1 While balance is exhausted

1. **Primary:** cmux or Terminal → `claude-local` inside the repo (prefer `--think=false` / fast path until quality needs thinking).  
2. **Cursor:** editor only — do not expect Agent/BYOK/Ollama override to work with **0 Cursor limit**.  
3. **Optional UI:** Claude Desktop **Continue with Gateway** → `http://127.0.0.1:11436` (accept that cloud threads are not available in this mode).  
4. **Avoid:** plain `claude`, Cursor Agent cloud models, Desktop signed into Anthropic while capped.

### 9.2 Whenever balance is back

1. Keep `claude-local` as the cheap daily default.  
2. Use real `claude` / Cursor cloud when local is stuck.  
3. Do **not** leave a global `ANTHROPIC_BASE_URL` pointing at Ollama.

### 9.3 Commands cheat sheet

```bash
# Health
curl -s http://127.0.0.1:11434/api/tags >/dev/null && echo ollama_ok
which claude-local
ollama ps
curl -s http://127.0.0.1:11436/health

# Warm + thinking off
ollama run qwen-code --think=false "Say pong"

# Coding agent in cmux / terminal
cd /path/to/repo && claude-local

# Fast API smoke (thinking off)
curl -s http://127.0.0.1:11434/api/chat \
  -d '{"model":"qwen-code","think":false,"stream":false,"messages":[{"role":"user","content":"Say pong"}]}'
```

---

## 10. Repo artifacts

| Path | Purpose |
|---|---|
| `install.sh` | Self-contained Mac installer (Ollama env, model, `claude-local`, Desktop proxy LaunchAgent). |
| `scripts/claude-local` | Session-only env override → Ollama; pins haiku/sonnet helper models; does not rewrite `~/.zshrc`. |
| `scripts/claude-desktop-proxy.py` | 11436 rewrite proxy. |
| `scripts/claude-desktop-proxy` | Launcher wrapper. |
| `modelfiles/qwen-code.Modelfile` | Alias parameters (`num_ctx` 49152) + medium-reasoning system prompt. |
| `README.md` | Install / run guide. |
| This file | Research findings for the team. |

Installer also embeds the proxy for machines that only copy `install.sh`. Refresh `~/.local/bin/claude-local` after pulling launcher changes (or paste the script directly — no git checkout required).

---

## 11. Open questions / watch items

1. Will a future Ollama Apps → Claude mapping accept Desktop’s Claude ids and map them to local Qwen without a custom proxy?  
2. Can Desktop gateway mode ever attach to prior Claude.ai threads? (Today: no evidence; treat as separate stores.)  
3. Ship a second alias `qwen-code-fast` with thinking off by default?  
4. Can Claude Code be told to pass `think: false` / Anthropic `thinking.type=disabled` through to Ollama reliably?  
5. Will Cursor ever support true localhost models without a public tunnel and without a paid/usage gate?  
6. Team policy: when is local Qwen “good enough” vs escalate to Claude/GPT?  
7. **Spike:** Qwen / coder **~14B** on the same M3 Pro — latency, quality on easy/medium tasks, memory with IDE + browser open.  
8. **Spike:** thin **task router** (heuristics first) — easy/medium → local; hard/reasoning-heavy → hosted; measure token savings and escalate rate.

---

## 12. Bottom line for the team

1. **Local coding works** on M3 Pro 36 GB with **Qwen 3.8 27B** (`qwen-code`) + Ollama — as a spike, not a polished primary path.  
2. **`claude-local` in cmux/terminal is the reliable $0 agent.** Cursor Agent is not. Plain `claude` still bills Anthropic.  
3. **No Cursor balance ⇒ keep Cursor as an editor; run the agent in cmux.** Override Base URL / tunnels do not unlock Agent when usage is exhausted; BYOK/custom models need an active Cursor paid plan.  
4. **Claude Desktop + local Qwen requires gateway mode + name rewriting** (our 11436 proxy, unless Ollama’s Apps path is fixed).  
5. **Signed-in Desktop still enforces Anthropic spend limits** even when the UI shows Qwen.  
6. Use **`num_ctx` 49152** or Claude Code hits `500 no user query found in messages`.  
7. **Thinking defaults on** and can turn a simple reply into ~11 minutes; **`/no_think` is not enough** — use `--think=false` / `"think": false`.  
8. When the UI only says `API error · Retrying`, probe Ollama directly; do not debug cmux first.  
9. **Next direction:** prefer **~14B** for headroom on 36 GB, and shift from “fallback when out of tokens” to a **router** — local for easy/medium, hosted for hard reasoning.

---

## 13. Revised direction (post-spike)

### 13.1 Why not stay on 27B as the default local lane

27B Q4/MLX (~17–18 GB weights) **does run** on 36 GB unified memory. Under real use it competes with:

- KV cache at long context (we needed ~49k for Claude Code’s tool/system prompt)
- Reasoning/thinking traces (can dominate wall time and token budget)
- Cursor/IDE, browser, Slack, and other office workload

Net: viable for a dedicated agent session; **uncomfortable as always-on while multitasking**.

**Proposal:** evaluate a **~14B** coding-capable Qwen (or equivalent) as the default local model — lower footprint, faster turns, more headroom for context without yellow/red memory pressure.

### 13.2 Goal shift: router, not only fallback

| Old framing | New framing |
|---|---|
| Local model = last resort when Cursor/Claude balance is exhausted | Local model = **default for easy/medium** tasks |
| Hosted = everything else when you have credits | Hosted = **hard / reasoning-intensive** tasks (and when local fails the quality bar) |

Sketch:

```text
                    ┌──────────────┐
  user / agent ──►  │ task router  │
                    └──────┬───────┘
               easy/medium │         hard / high-reasoning
                           ▼                    ▼
                    local Qwen ~14B      hosted Claude / GPT
                    (Ollama / claude-local)
```

Routing signals (v1 heuristics, no ML required): task type (rename/test fix vs architecture), estimated context size, explicit user override (`/local` vs `/cloud`), prior local failure. Later: small classifier or confidence from the local model’s own “I’m stuck” signal.

### 13.3 Success metrics for the next spike

1. **Memory:** 14B + ~32–49k ctx + IDE open stays green in Activity Monitor.  
2. **Latency:** easy tasks (explain file, small patch) in seconds with thinking off.  
3. **Quality:** acceptable on a fixed suite of easy/medium prompts; escalate rate to hosted tracked.  
4. **Cost:** measurable reduction in hosted token spend when the router is on.

Until that spike lands, treat the 27B setup as a **documented prototype** (this gist/repo), not the recommended team default.

For install and daily commands, see [`README.md`](./README.md).
