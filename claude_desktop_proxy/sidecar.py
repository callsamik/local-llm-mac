"""Warn if Ollama's Claude sidecar occupies :11435."""
from __future__ import annotations

import socket
import sys

from claude_desktop_proxy.config import Settings


def sidecar_warning() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        sock.connect(("127.0.0.1", 11435))
    except OSError:
        return
    finally:
        sock.close()
    sys.stderr.write(
        "\n"
        "!!  Port 11435 is in use (Ollama's Claude sidecar).\n"
        '!!  That sidecar returns: unknown Claude model "claude-sonnet-4-6"\n'
        "!!  Turn Ollama → Apps → Claude  Off, then in Desktop set:\n"
        f"!!    Gateway base URL  http://{Settings.listen_host}:{Settings.listen_port}\n"
        "!!  Do not leave Desktop pointed at 11435.\n"
        "\n"
    )
