# Local coding agent for a 36GB M3 Pro

Installs Ollama and **Qwen 3.8 27B** — same size as the 3.6 27B, trained for long agent runs (plan → edit → test → repeat) with thinking left on.

One model. Code stays on the laptop. Default reasoning effort is **medium** so it does not spend 20 minutes on a rename; raise it for hard bugs.

## Install on the Mac

```bash
chmod +x install.sh scripts/set-ollama-env.sh scripts/claude-local
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

## Two ways to “use Claude”

| Command | Brain | Where code goes |
|---|---|---|
| `claude-local` | Qwen 3.8 on this Mac | Stays on the laptop |
| `claude` | Anthropic Claude (your subscription / API key) | Anthropic’s API |

Use both. Do **not** put `ANTHROPIC_BASE_URL=http://127.0.0.1:11434` in `~/.zshrc` — that would send every `claude` session to Ollama and break real Claude.

```bash
cd /path/to/your/repo
claude-local
```

Same thing, Ollama’s built-in launcher:

```bash
ollama launch claude --model qwen-code
```

If `~/.claude/settings.json` has `CLAUDE_CODE_USE_BEDROCK`, `claude-local` unsets it for that process only. Remove it from the file if Bedrock still wins.

Need `~/.local/bin` on PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Use it as a chat model

```bash
ollama run qwen-code
```

Cursor / Continue / Aider (OpenAI-compatible):

- Base URL: `http://127.0.0.1:11434/v1`
- Model: `qwen-code`
- API key: any non-empty string

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
