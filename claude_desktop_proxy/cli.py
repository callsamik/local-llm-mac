"""CLI entry for Claude Desktop rewrite proxy."""
from __future__ import annotations

import argparse
import sys

from claude_desktop_proxy.composition import build_server
from claude_desktop_proxy.config import Settings
from claude_desktop_proxy.sidecar import sidecar_warning


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite Claude Desktop model ids to local Ollama.")
    parser.add_argument("--host", default=Settings.listen_host)
    parser.add_argument("--port", type=int, default=Settings.listen_port)
    parser.add_argument("--upstream", default=Settings.upstream)
    parser.add_argument("--model", default=Settings.local_model)
    args = parser.parse_args()

    Settings.listen_host = args.host
    Settings.listen_port = args.port
    Settings.upstream = args.upstream.rstrip("/")
    Settings.local_model = args.model

    sidecar_warning()
    print(
        f"Claude Desktop proxy  http://{Settings.listen_host}:{Settings.listen_port}  "
        f"->  {Settings.upstream} ({Settings.local_model})",
        flush=True,
    )
    print(
        "Desktop gateway URL must be this address, not :11435. Ollama → Apps → Claude = Off.",
        flush=True,
    )
    try:
        build_server().serve_forever()
    except OSError as exc:
        sys.stderr.write(
            f"error: could not bind {Settings.listen_host}:{Settings.listen_port}: {exc}\n"
            "If something else is already serving that port, stop it or pass --port.\n"
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
