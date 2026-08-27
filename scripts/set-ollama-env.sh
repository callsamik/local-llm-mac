#!/usr/bin/env bash
# Applied at login via LaunchAgent so the Ollama macOS app sees these.
# The menu-bar app does not read ~/.zshrc.
set -euo pipefail

launchctl setenv OLLAMA_HOST "127.0.0.1:11434"
launchctl setenv OLLAMA_KEEP_ALIVE "-1"
launchctl setenv OLLAMA_FLASH_ATTENTION "1"
launchctl setenv OLLAMA_MLX "1"
launchctl setenv OLLAMA_CONTEXT_LENGTH "49152"
launchctl setenv OLLAMA_NUM_PARALLEL "1"
