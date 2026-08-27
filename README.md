# Local coding agent for a 36GB M3 Pro

Installs Ollama and **Qwen 3.8 27B** — same size as the 3.6 27B, trained for long agent runs (plan → edit → test → repeat) with thinking left on.

One model. Code stays on the laptop. Default reasoning effort is **medium** so it does not spend 20 minutes on a rename; raise it for hard bugs.

**Team write-up:** full research, dead ends, Desktop/spend-limit findings, and performance notes are in [`docs/LOCAL-LLM-RESEARCH.md`](./docs/LOCAL-LLM-RESEARCH.md).

**Session handoff** (current decisions, what’s built vs deferred, next steps): [`docs/HANDOFF.md`](./docs/HANDOFF.md).

## Install on the Mac

```bash
chmod +x install.sh
./install.sh
```

That will:

1. Install Ollama (Homebrew if present, otherwise the official app into `~/Applications`)
2. Bind the API to `127.0.0.1:11434`
3. Enable MLX, flash attention, keep-alive, and a 49k context
4. Persist those settings across reboot
5. Pull `qwen3.8:27b` (~18GB) and create the `qwen-code` alias
6. Install Claude Code and a `claude-local` launcher that points it at that model
7. Install a Claude Desktop rewrite proxy on `127.0.0.1:11436` (LaunchAgent on Mac)

Optional: `./install.sh --mlx` pulls `qwen3.8:27b-nvfp4` (still ~18GB, usually faster on Apple Silicon).

Expect a long download.

## While Cursor / Claude balance is exhausted

Do the work in a **terminal** or **cmux**, not Cursor Agent.

```bash
cd /path/to/your/repo
claude-local
```

That is Claude Code driving **local Qwen 3.8** (`qwen-code`). It does not use Cursor usage or Anthropic credits.

In [cmux](https://cmux.com): open a workspace on the repo, then run `claude-local` (not plain `claude`). One workspace per parallel agent.

Thinking is **on by default** and can make short replies take many minutes. For snappy turns:

```bash
ollama run qwen-code --think=false "Say pong"
```

Prompt text `/no_think` alone is **not** reliable on this model — use `--think=false` / API `"think": false`.

- Do **not** run plain `claude` while balance is exhausted — that still bills Anthropic.
- Do **not** pick Auto / Claude / GPT in Cursor Agent — that still bills Cursor. Cursor also often cannot reach `localhost` Ollama because Agent traffic goes through Cursor’s servers.
- **No Cursor balance:** use Cursor as an **editor only**. Agent/BYOK/Override OpenAI Base URL to Ollama will not unlock Agent at “0 limit left.” Run the agent in cmux with `claude-local` instead. Details: [`docs/LOCAL-LLM-RESEARCH.md`](./docs/LOCAL-LLM-RESEARCH.md) §7.
- Cursor Tab can still use Cursor’s cloud; turn it off if you need to stretch anything left.

Need a new terminal after install so `claude-local` is on PATH (`~/.local/bin`).

If Claude Code shows `500 no user query found in messages`, recreate `qwen-code` with `num_ctx 49152` (see research doc). Opaque `API error · Retrying` → probe Ollama with `curl` first.

## Whenever balance is back

Keep `claude-local` for everyday agent runs so the new balance lasts. Use Cursor cloud or plain `claude` only when the local agent is stuck.

Do **not** put `ANTHROPIC_BASE_URL=http://127.0.0.1:11434` in `~/.zshrc` — that would send every `claude` session to Ollama after you have credits again.

```bash
# local (free)
claude-local

# Anthropic, whenever balance is back
claude
```

## Smart router (14B local + cloud for hard tasks)

On a 36GB machine that also runs IDE/browser work, **Qwen3 14B** (`qwen-fast`) leaves more headroom than 27B once KV cache and context are counted. A small proxy on `:11437` sends easy/medium turns to that local model and harder / reasoning-heavy turns to hosted Claude when `ANTHROPIC_API_KEY` is set.

```bash
chmod +x scripts/setup-14b-router.sh
./scripts/setup-14b-router.sh
```

Then:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # optional; without it, hard tasks stay local
llm-router                             # if LaunchAgent is not already up
claude-routed                          # in cmux / terminal on your repo
```

Heuristics (sticky per conversation): architecture, migrations, race conditions, security audits, “root cause”, long prompts, and enabled thinking → cloud; renames, typos, “what is…”, list files → local. Override with header `x-route: local|cloud` or `ROUTER_FORCE=local|cloud`.

Unload the 27B when using this path so RAM stays free: `ollama stop qwen-code`.

Classify without Ollama: `./scripts/test-router-classify.sh`

## Claude Desktop app

The error `unknown Claude model "claude-sonnet-4-6"` on **port 11435** means Desktop is talking to Ollama’s Claude sidecar. That sidecar only catalogs real Claude slots. Aliasing Qwen as `claude-sonnet-4-6` on port 11434 does not change 11435.

**Do not use `http://127.0.0.1:11435`.**

1. In Ollama: **Apps → Claude → Off** (or `ollama launch claude-desktop --restore`).
2. Start the rewrite proxy if the installer LaunchAgent is not already serving it:

```bash
claude-desktop-proxy
```

3. In Claude Desktop (Help → Troubleshooting → Enable Developer Mode → Developer → Configure Third-Party Inference):

- Gateway base URL: `http://127.0.0.1:11436`
- API key: `ollama`
- Auth: `x-api-key`
- Model: `claude-sonnet-4-6`
- Tier: `sonnet`

4. Cmd+Q Desktop, reopen, Continue with Gateway.

The proxy advertises `claude-sonnet-4-6` (Desktop requires an Anthropic-looking id) and rewrites it to local `qwen-code` on port 11434. Confirm the proxy is the one you hit:

```bash
curl -s http://127.0.0.1:11436/health
```

You should see `"proxy": "claude-desktop-proxy"`. If that fails, the LaunchAgent is not up — run `claude-desktop-proxy` in a terminal and leave it open.

**Gateway timeout on `/v1/messages`:** model discovery works, but the first chat hangs. Load the 27B into RAM first, then send `ping`:

```bash
ollama run qwen-code "Reply with the single word pong."
```

Wait until it prints `pong` (can take a minute). Then retry Desktop. Keep Ollama open so keep-alive holds the model.

Cloud connectors that need Anthropic’s backend (Gmail, Drive, and similar) will not work in this mode. `claude-local` in a terminal is the more reliable $0 agent while balance is exhausted.

## Use it as a chat model

```bash
ollama run qwen-code
```

### Reasoning effort

Thinking is on. The wrapper defaults to **medium**.

| Job | What to send |
|---|---|
| Multi-file bug, tests failing, long unsupervised run | `"reasoning_effort": "high"` (or `xhigh` if the client accepts it) |
| Normal agent coding (default) | nothing extra — medium |
| Quick lookup | `"think": false` / `ollama run … --think=false` (preferred). Do not rely on `/no_think` alone. |

Example for a hard run:

```bash
curl http://127.0.0.1:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen-code",
    "reasoning_effort": "high",
    "messages": [{"role": "user", "content": "Find why payments double-charge and patch it."}]
  }'
```

Do not leave `xhigh` on for every request. On this Mac it will burn the 49k context on thinking and feel stalled.

## Context on 36GB

49k tokens is the budget that still leaves room for macOS + Cursor + the 18GB weights while fitting Claude Code’s large system/tools prompt (32k was too small and caused `500 no user query found in messages`). That is enough for an agent to read several files and a test log. It is not enough to dump the whole repo into the prompt — let the agent open files as it goes.

If Activity Monitor memory pressure goes yellow/red, close Chrome tabs or drop context; do not raise `num_ctx` first.

## After reboot

The LaunchAgent at `~/Library/LaunchAgents/com.ollama.mac-env.plist` reapplies localhost bind, keep-alive, MLX, flash attention, 49k context, and a single parallel slot. Open the Ollama app once after login if the API is not up.

The Claude Desktop rewrite proxy relaunches from `~/Library/LaunchAgents/com.local-llm.claude-desktop-proxy.plist` on `127.0.0.1:11436`.
