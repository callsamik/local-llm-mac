"""CLI entry point for llm-router."""
from __future__ import annotations

import argparse
import json
import os
import sys

from llm_router.auth import cloud_api_key, load_claude_cli_oauth_token
from llm_router.composition import build_server
from llm_router.config import Cfg
from llm_router.scoring.composite import score_route


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Route Claude Code across local Qwen and Claude Haiku/Sonnet/Opus/Fable "
            "with cascade failover down to local."
        )
    )
    parser.add_argument("--host", default=Cfg.listen_host)
    parser.add_argument("--port", type=int, default=Cfg.listen_port)
    parser.add_argument("--local-model", default=Cfg.local_model)
    parser.add_argument("--haiku-model", default=Cfg.haiku_model)
    parser.add_argument("--sonnet-model", default=Cfg.sonnet_model)
    parser.add_argument("--opus-model", default=Cfg.opus_model)
    parser.add_argument("--fable-model", default=Cfg.fable_model)
    parser.add_argument(
        "--cheap-model",
        default=None,
        help="Legacy alias for --haiku-model",
    )
    parser.add_argument(
        "--frontier-model",
        default=None,
        help="Legacy alias for --sonnet-model",
    )
    parser.add_argument(
        "--cloud-model",
        default=None,
        help="Legacy alias for --sonnet-model",
    )
    parser.add_argument("--classify", metavar="TEXT", help="Print route decision for TEXT and exit")
    args = parser.parse_args()

    Cfg.listen_host = args.host
    Cfg.listen_port = args.port
    Cfg.local_model = args.local_model
    Cfg.haiku_model = args.cheap_model or args.haiku_model
    Cfg.sonnet_model = args.cloud_model or args.frontier_model or args.sonnet_model
    Cfg.opus_model = args.opus_model
    Cfg.fable_model = args.fable_model
    Cfg.cheap_model = Cfg.haiku_model
    Cfg.frontier_model = Cfg.sonnet_model
    Cfg.cloud_model = Cfg.sonnet_model

    if args.classify is not None:
        # Deterministic classify for tests/docs unless user forces LLM.
        if Cfg.llm_classify in {"auto", ""}:
            os.environ["ROUTER_CLASSIFY_OFFLINE"] = "1"
        decision = score_route(
            args.classify, {"messages": [{"role": "user", "content": args.classify}]}
        )
        print(
            json.dumps(
                {
                    "route": decision.lane,
                    "effort": decision.effort,
                    "thinking": decision.thinking,
                    "reason": decision.reason,
                    "score": decision.score,
                }
            )
        )
        return

    print(
        f"llm-router  http://{Cfg.listen_host}:{Cfg.listen_port}  "
        f"local={Cfg.local_model}  haiku={Cfg.haiku_model}  "
        f"sonnet={Cfg.sonnet_model}  opus={Cfg.opus_model}  "
        f"fable={Cfg.fable_model}@{Cfg.cloud_upstream}  "
        f"cascade={'on' if Cfg.cascade else 'off'}",
        flush=True,
    )
    if cloud_api_key({}):
        print("auth: Anthropic API key available for hosted lanes", flush=True)
    elif load_claude_cli_oauth_token():
        print(
            "auth: Claude Code CLI OAuth available for hosted lanes (no API key needed)",
            flush=True,
        )
    else:
        print(
            "warning: no API key and no Claude Code OAuth — hosted lanes fall back to local\n"
            "         Log in with: claude  (once), then restart llm-router",
            flush=True,
        )
    try:
        build_server(Cfg.listen_host, Cfg.listen_port).serve_forever()
    except OSError as exc:
        sys.stderr.write(f"error: bind {Cfg.listen_host}:{Cfg.listen_port}: {exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
