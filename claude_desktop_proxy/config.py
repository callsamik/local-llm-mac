"""Configuration for the Claude Desktop rewrite proxy."""
from __future__ import annotations

import os


class Settings:
    upstream = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
    listen_host = os.environ.get("CLAUDE_DESKTOP_PROXY_HOST", "127.0.0.1")
    listen_port = int(os.environ.get("CLAUDE_DESKTOP_PROXY_PORT", "11436"))
    local_model = os.environ.get("CLAUDE_LOCAL_MODEL", "qwen-fast")
