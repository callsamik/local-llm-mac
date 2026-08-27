# Local coding model for a 36GB M3 Pro

Installs Ollama and **Qwen 3.6 27B coding** — the local model that fits this MacBook and is the strongest open coder you can actually run on 36GB.

One model. Coding only. Nothing leaves the laptop.

## Install on the Mac

```bash
chmod +x install.sh scripts/set-ollama-env.sh
./install.sh
```

That will:

1. Install Ollama (Homebrew if present, otherwise the official app into `~/Applications`)
2. Bind the API to `127.0.0.1:11434`
3. Enable MLX, flash attention, keep-alive, and a 32k context
4. Persist those settings across reboot
5. Pull `qwen3.6:27b-coding` (~18GB) and create the `qwen-code` alias

Optional: `./install.sh --mlx` pulls the same coding checkpoint as MLX nvfp4 (~20GB) instead of Q4. Slightly higher quality, still comfortable on 36GB.

Expect a long download.

## Use it in Cursor

```bash
ollama run qwen-code
```

Then: Settings → Models → OpenAI-compatible provider

- Base URL: `http://127.0.0.1:11434/v1`
- Model: `qwen-code`
- API key: any non-empty string

`/no_think` in a prompt skips reasoning tokens when you want a faster reply.

## After reboot

The LaunchAgent at `~/Library/LaunchAgents/com.ollama.mac-env.plist` reapplies localhost bind, keep-alive, MLX, flash attention, 32k context, and a single parallel slot. Open the Ollama app once after login if the API is not up.

If Activity Monitor memory pressure goes yellow/red, close extra Chrome tabs. The 27B needs headroom for the context cache on top of the ~18GB weights.
