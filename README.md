# Local LLM setup for a 36GB M3 Pro

Installs Ollama and the Qwen 3.6 models that actually fit a MacBook Pro M3 Pro with 36GB unified memory, then wires them for plugged-in daily use.

This is a Mac installer. Run it on the laptop, not in a container.

## What you get

| Role | Ollama tag | Disk | When |
|---|---|---|---|
| Daily coding driver | `qwen3.6:27b-coding` → alias `qwen-code` | ~18GB | Default |
| Faster MLX quant | `qwen3.6:27b-coding-nvfp4` → alias `qwen-code` | ~20GB | `--mlx` |
| Fast chat / tools | `qwen3.6:35b-a3b-coding` → alias `qwen-fast` | ~23GB | `--with-moe` |
| Agentic edit-test-fix | `devstral:24b` → alias `devstral-agent` | ~14GB | `--with-devstral` |

Official Ollama does not ship Q5/Q6 for the dense 27B. The useful steps up from Q4 on this library are MLX nvfp4 (~20GB, still comfortable) and Q8 (~30GB, too tight with Cursor + Chrome). Default is the coding Q4 with a 32k context wrapper.

On 36GB, keep **one** of the large models loaded. The 27B plus the 35B MoE will swap.

## Install on the Mac

```bash
chmod +x install.sh scripts/set-ollama-env.sh
./install.sh
```

That will:

1. Install Ollama (Homebrew if present, otherwise the official app into `~/Applications` so it does not need admin)
2. Bind the API to `127.0.0.1:11434`
3. Enable MLX, flash attention, keep-alive, and a 32k context
4. Persist those settings across reboot (macOS LaunchAgent — the menu-bar app ignores `~/.zshrc`)
5. Pull `qwen3.6:27b-coding` and create the `qwen-code` alias

Useful flags:

```bash
./install.sh --mlx                 # 20GB MLX nvfp4 instead of 18GB Q4
./install.sh --with-moe            # also pull the 35B-A3B coding MoE
./install.sh --with-devstral       # also pull Devstral 24B
./install.sh --smoke-test          # one short generation after the pull
./install.sh --dry-run             # print actions only
```

Expect a long download. ~20GB on office wifi is not a coffee-break job.

## Use it

```bash
ollama run qwen-code
```

API for Cursor, Continue, Aider, and anything OpenAI-compatible:

- Base URL: `http://127.0.0.1:11434/v1`
- Model: `qwen-code`
- API key: any non-empty string (Ollama ignores it)

In Cursor: Settings → Models → add an OpenAI-compatible provider with those values.

`/no_think` in the prompt skips reasoning tokens when you want a faster reply.

## Should you install OmniRoute?

**No, not for this setup.** Skip it unless you later want a cloud fallback in front of many providers.

OmniRoute (`omniroute`, also written OmniRouter) is a multi-provider gateway: one local port, then auto-fallback across hundreds of cloud APIs, OAuth CLIs, and free tiers. It can sit in front of Ollama, but that is not what makes local Qwen work.

For a 36GB office MacBook the costs outweigh the help:

- You only need one local model. Ollama already exposes `http://127.0.0.1:11434/v1`. A router does not make the 27B faster or smarter.
- OmniRoute’s value is quota-hopping and cloud fallback. The moment a combo includes a remote provider, prompts can leave the laptop. That fights the reason to run local on an office machine.
- Extra daemon, extra port (`20128`), extra Node install, extra dashboard. None of that is required to chat with `qwen-code`.

If you still want it later (local-first, then Claude/GPT only when the 27B is stuck), install it yourself and keep cloud providers off until you mean it:

```bash
./install.sh --with-omniroute --skip-models
```

Do not point Cursor at OmniRoute while any remote provider is connected if the code is not allowed to leave the machine.

## After reboot

The LaunchAgent at `~/Library/LaunchAgents/com.ollama.mac-env.plist` reapplies:

- `OLLAMA_HOST=127.0.0.1:11434` (localhost only)
- `OLLAMA_KEEP_ALIVE=-1` (keep the model in RAM; you are plugged in)
- `OLLAMA_MLX=1`
- `OLLAMA_FLASH_ATTENTION=1`
- `OLLAMA_CONTEXT_LENGTH=32768`
- `OLLAMA_NUM_PARALLEL=1` (one slot, so the KV cache does not eat the remaining RAM)

Open the Ollama app once after login if the API is not up.

## Hardware notes

M3 Pro unified memory is RAM and VRAM. After macOS + Cursor + a browser, budget about 24–28GB for the model and its context cache. Yellow/red memory pressure in Activity Monitor means you are swapping — close Chrome tabs or drop back to the default Q4 coding tag.
