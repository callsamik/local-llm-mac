# Local coding agent for a 36GB M3 Pro

**Primary install:** Ollama + **Qwen3 14B** (`qwen-fast`) + **heuristic router** (`claude-routed`):

| Lane | Model |
|------|--------|
| local | Qwen 14B on the Mac |
| cheap | Haiku (Claude Code OAuth) |
| frontier | Sonnet (Claude Code OAuth) |

Optional: `--with-27b` also installs Qwen 3.8 27B as `qwen-code` for heavy local-only runs.

**Team write-up:** [`docs/LOCAL-LLM-RESEARCH.md`](./docs/LOCAL-LLM-RESEARCH.md) (historical spike notes).  
**Handoff:** [`docs/HANDOFF.md`](./docs/HANDOFF.md).

## Install on the Mac

```bash
chmod +x install.sh
./install.sh
```

That will:

1. Install Ollama (Homebrew if present, otherwise the official app into `~/Applications`)
2. Bind the API to `127.0.0.1:11434` and persist Mac env (MLX, flash attention, keep-alive, context)
3. Pull **`qwen3:14b`**, create **`qwen-fast`**, install **`llm-router`** + **`claude-routed`** (LaunchAgent on `:11437`)
4. Install Claude Code and **`claude-local`** (side chat / forced local)
5. Install the Claude Desktop rewrite proxy on `127.0.0.1:11436`

Optional flags:

```bash
./install.sh --with-27b          # also pull ~18GB qwen-code (27B)
./install.sh --with-27b --mlx    # 27B MLX nvfp4
./install.sh --skip-router       # skip 14B router path (not recommended)
```

Already have Ollama? Router-only upgrade:

```bash
./scripts/setup-14b-router.sh
```

## Everyday use (cmux)

```bash
claude                 # once: Claude Code CLI login (subscription)
claude-routed          # router: local / Haiku / Sonnet
```

Forced local only: `claude-local`.

Unload 27B if installed and you want RAM for the router path: `ollama stop qwen-code`.

## While Cursor balance is exhausted

Use **cmux / terminal** with `claude-routed` or `claude-local` — not Cursor Agent (Agent traffic goes through Cursor’s servers and still bills usage).

Thinking on local Qwen: use `--think=false` / API `"think": false` — do not rely on `/no_think` alone.

Do **not** put `ANTHROPIC_BASE_URL=…` permanently in `~/.zshrc`.

## Smart router details

| Lane | Model | Typical asks |
|------|--------|----------------|
| **local** | `qwen-fast` | rename, explain, list files |
| **cheap** | Haiku | implement / fix / add tests |
| **frontier** | Sonnet | architecture, races, security audits |

Hosted lanes use **Claude Code CLI OAuth** (no `ANTHROPIC_API_KEY` required). Optional pay-as-you-go key still works if set.

Scoring layers (in order): regex catalogs → informal phrase/slang normalization → structural cues (questions, imperatives, code fences) → optional **local Qwen** classify when still uncertain (`ROUTER_LLM_CLASSIFY=auto` by default; `never` to disable; `always` to force).

```bash
curl -s http://127.0.0.1:11437/health
./scripts/test-router-classify.sh
```

Design: [`docs/superpowers/specs/2026-08-27-heuristic-router-design.md`](./docs/superpowers/specs/2026-08-27-heuristic-router-design.md).

## Claude Desktop app

The error `unknown Claude model "claude-sonnet-4-6"` on **port 11435** means Desktop is talking to Ollama’s Claude sidecar. That sidecar only catalogs real Claude slots.

**Do not use `http://127.0.0.1:11435`.**

1. In Ollama: **Apps → Claude → Off** (or `ollama launch claude-desktop --restore`).
2. Start the rewrite proxy if needed: `claude-desktop-proxy`
3. Gateway: `http://127.0.0.1:11436` · key `ollama` · model `claude-sonnet-4-6` · tier `sonnet`
4. Cmd+Q Desktop, reopen, Continue with Gateway.

The proxy rewrites Claude-looking ids to local **`qwen-fast`** by default. Warm the model first:

```bash
ollama run qwen-fast --think=false "Reply with the single word pong."
```

## Use it as a chat model

```bash
ollama run qwen-fast --think=false
# optional heavy local:
ollama run qwen-code
```

### Reasoning effort

| Job | What to send |
|---|---|
| Multi-file bug / long unsupervised run | `"reasoning_effort": "high"` (hosted frontier, or 27B local) |
| Normal agent coding | default |
| Quick lookup | `"think": false` / `ollama run … --think=false` |

## Context on 36GB

Prefer **14B + router** so KV cache, IDE, and browser still fit. The optional 27B path uses a 49k context budget that leaves little headroom once weights + cache are loaded.

If Activity Monitor memory pressure goes yellow/red, unload `qwen-code`, close Chrome tabs, or shorten context — do not raise `num_ctx` first.

## After reboot

- `~/Library/LaunchAgents/com.ollama.mac-env.plist` — Ollama env
- `~/Library/LaunchAgents/com.local-llm.llm-router.plist` — heuristic router `:11437`
- `~/Library/LaunchAgents/com.local-llm.claude-desktop-proxy.plist` — Desktop proxy `:11436`

Open the Ollama app once after login if the API is not up.
