"""Authentication helpers for hosted Claude lanes."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def _is_placeholder_secret(value: str) -> bool:
    return value.strip().lower() in {"", "ollama", "proxy-managed", "placeholder", "unused"}


class AuthService:
    """Resolve API keys and Claude Code OAuth for upstream calls."""

    def cloud_api_key(self, headers: dict[str, str]) -> str:
        """Real Anthropic API key if present (not Claude Code subscription)."""
        key = (
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ROUTER_ANTHROPIC_API_KEY")
            or headers.get("x-api-key")
            or ""
        ).strip()
        if _is_placeholder_secret(key):
            return ""
        return key

    def load_claude_cli_oauth_token(self) -> str:
        """Load Claude Code CLI subscription OAuth access token if available.

        Sources (first hit wins):
          CLAUDE_ACCESS_TOKEN
          ~/.claude/.credentials.json (Linux/file fallback)
          macOS Keychain service "Claude Code-credentials"
        """
        env_token = (os.environ.get("CLAUDE_ACCESS_TOKEN") or "").strip()
        if env_token and not _is_placeholder_secret(env_token):
            return env_token

        cred_path = os.path.expanduser(
            os.environ.get("CLAUDE_CREDENTIALS_FILE", "~/.claude/.credentials.json")
        )
        try:
            with open(cred_path, encoding="utf-8") as fh:
                data = json.load(fh)
            # Common shapes used by Claude Code credential stores.
            for key in ("accessToken", "access_token", "claudeAiOauth"):
                val = data.get(key)
                if isinstance(val, str) and val.strip() and not _is_placeholder_secret(val):
                    return val.strip()
                if isinstance(val, dict):
                    nested = val.get("accessToken") or val.get("access_token") or ""
                    if isinstance(nested, str) and nested.strip() and not _is_placeholder_secret(nested):
                        return nested.strip()
            oauth = data.get("oauth")
            if isinstance(oauth, dict):
                nested = oauth.get("accessToken") or oauth.get("access_token") or ""
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
        except (OSError, json.JSONDecodeError, TypeError):
            pass

        if sys.platform == "darwin":
            try:
                out = subprocess.check_output(
                    ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                out = ""
            if out:
                if out.startswith("{"):
                    try:
                        payload = json.loads(out)
                        nested = payload.get("accessToken") or payload.get("access_token") or ""
                        oauth = payload.get("claudeAiOauth")
                        if isinstance(oauth, dict):
                            nested = nested or oauth.get("accessToken") or oauth.get("access_token") or ""
                        if isinstance(nested, str) and nested.strip():
                            return nested.strip()
                    except (json.JSONDecodeError, TypeError):
                        pass
                if not _is_placeholder_secret(out):
                    return out
        return ""

    def inbound_bearer_token(self, headers: dict[str, str]) -> str:
        auth = (headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            if token and not _is_placeholder_secret(token):
                return token
        return ""

    def cloud_auth_ready(self, headers: dict[str, str]) -> bool:
        """True if hosted Claude lanes can call Anthropic (API key or Claude Code OAuth)."""
        return bool(
            self.cloud_api_key(headers)
            or self.inbound_bearer_token(headers)
            or self.load_claude_cli_oauth_token()
        )

    def auth_headers_local(self, _headers: dict[str, str]) -> dict[str, str]:
        return {"x-api-key": "ollama"}

    def auth_headers_cloud(self, headers: dict[str, str]) -> dict[str, str]:
        """Auth for api.anthropic.com: prefer API key, else Claude Code OAuth bearer."""
        api_key = self.cloud_api_key(headers)
        out: dict[str, str] = {
            "anthropic-version": headers.get("anthropic-version") or "2023-06-01",
        }
        for k, v in headers.items():
            if k.startswith("anthropic-") and k != "anthropic-version":
                out[k] = v

        if api_key:
            out["x-api-key"] = api_key
            return out

        token = self.inbound_bearer_token(headers) or self.load_claude_cli_oauth_token()
        if not token:
            return out

        out["Authorization"] = f"Bearer {token}"
        # Anthropic rejects Claude Code OAuth without this beta flag.
        beta = out.get("anthropic-beta", "")
        flag = "oauth-2025-04-20"
        if flag not in beta:
            out["anthropic-beta"] = f"{beta},{flag}" if beta else flag
        return out


_default_auth = AuthService()


def cloud_api_key(headers: dict[str, str]) -> str:
    return _default_auth.cloud_api_key(headers)


def load_claude_cli_oauth_token() -> str:
    return _default_auth.load_claude_cli_oauth_token()


def inbound_bearer_token(headers: dict[str, str]) -> str:
    return _default_auth.inbound_bearer_token(headers)


def cloud_auth_ready(headers: dict[str, str]) -> bool:
    return _default_auth.cloud_auth_ready(headers)


def auth_headers_local(headers: dict[str, str]) -> dict[str, str]:
    return _default_auth.auth_headers_local(headers)


def auth_headers_cloud(headers: dict[str, str]) -> dict[str, str]:
    return _default_auth.auth_headers_cloud(headers)
