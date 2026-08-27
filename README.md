# Local coding agent for a 36GB M3 Pro

Installs Ollama and **Qwen 3.8 27B** — same size as the 3.6 27B, trained for long agent runs (plan → edit → test → repeat) with thinking left on.

One model. Code stays on the laptop. Default reasoning effort is **medium** so it does not spend 20 minutes on a rename; raise it for hard bugs.

## Install on the Mac

```bash
chmod +x install.sh
./install.sh
```

That will:

1. Install Ollama (Homebrew if present, otherwise the official app into `~/Applications`)
2. Bind the API to `127.0.0.1:11434`
3. Enable MLX, flash attention, keep-alive, and a 32k context
4. Persist those settings across reboot
5. Pull `qwen3.8:27b` (~18GB) and create the `qwen-code` alias
6. Install Claude Code and a `claude-local` launcher that points it at that model

Optional: `./install.sh --mlx` pulls `qwen3.8:27b-nvfp4` (still ~18GB, usually faster on Apple Silicon).

Expect a long download.

## Until 1 September (no Cursor / Claude balance)

Do the work in a **terminal**, not Cursor Agent.

```bash
cd /path/to/your/repo
claude-local
```

That is Claude Code driving **local Qwen 3.8**. It does not use Cursor usage or Anthropic credits.

- Do **not** run plain `claude` until the recharge — that still bills Anthropic.
- Do **not** pick Auto / Claude / GPT in Cursor Agent — that still bills Cursor. Cursor also often cannot reach `localhost` Ollama because Agent traffic goes through Cursor’s servers.
- Cursor Tab can still use Cursor’s cloud; turn it off if you need to stretch anything left.

Need a new terminal after install so `claude-local` is on PATH (`~/.local/bin`).

## From 1 September

Keep `claude-local` for everyday agent runs so the new balance lasts. Use Cursor cloud or plain `claude` only when the local agent is stuck.

Do **not** put `ANTHROPIC_BASE_URL=http://127.0.0.1:11434` in `~/.zshrc` — that would send every `claude` session to Ollama after you have credits again.

```bash
# local (free)
claude-local

# Anthropic, after 1 Sep
claude
```

## Claude Desktop app

Yes, after Ollama is running. The stock Claude Desktop app still talks to Anthropic (no/low balance until 1 Sep). Point it at local Ollama instead:

1. Use a current Ollama (Claude Desktop support shipped 25 Aug 2026).
2. Open Ollama → Claude → turn **Claude** on. Ollama writes the third-party gateway for you.
3. In Claude Desktop, choose **`claude-sonnet-4-5`** (that is still local Qwen; Desktop rejects `qwen-code`).
4. On 1 Sep, turn Claude **off** in Ollama to restore Anthropic.

Claude Desktop only accepts names like `claude-sonnet-4-5`. After the model is installed:

```bash
ollama cp qwen-code claude-sonnet-4-5
ollama cp qwen-code claude-sonnet-4-6
```

In the gateway form, set the model list to `claude-sonnet-4-5`. The weights are still Qwen 3.8 on this Mac; nothing is billed to Anthropic as long as the gateway URL is `http://127.0.0.1:11434`.

If the toggle is missing: Help → Troubleshooting → Enable Developer Mode → Developer → Configure Third-Party Inference → Gateway `http://127.0.0.1:11434`, API key `ollama`.

Cloud connectors that need Anthropic’s backend (Gmail, Drive, and similar) will not work in this mode. `claude-local` in a terminal is the more reliable $0 agent until credits return.

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
| Quick lookup | `"reasoning_effort": "low"` or `/no_think` in the prompt |

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

Do not leave `xhigh` on for every request. On this Mac it will burn the 32k context on thinking and feel stalled.

## Context on 36GB

32k tokens is the budget that still leaves room for macOS + Cursor + the 18GB weights. That is enough for an agent to read several files and a test log. It is not enough to dump the whole repo into the prompt — let the agent open files as it goes.

If Activity Monitor memory pressure goes yellow/red, close Chrome tabs or drop context; do not raise `num_ctx` first.

## After reboot

The LaunchAgent at `~/Library/LaunchAgents/com.ollama.mac-env.plist` reapplies localhost bind, keep-alive, MLX, flash attention, 32k context, and a single parallel slot. Open the Ollama app once after login if the API is not up.
