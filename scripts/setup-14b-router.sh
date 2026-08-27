#!/usr/bin/env bash
# Pull qwen3:14b, create qwen-fast alias, install router + claude-routed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${HOME}/.local/bin"
SHARE="${HOME}/.local/share/local-llm-mac"

log() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v ollama >/dev/null 2>&1 || die "ollama not on PATH"
command -v python3 >/dev/null 2>&1 || die "python3 required"
curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null || die "Ollama API not up on 11434"

mkdir -p "${BIN}" "${SHARE}"

log "pulling qwen3:14b (~9.3GB)"
ollama pull qwen3:14b

log "creating alias qwen-fast"
ollama create qwen-fast -f "${ROOT}/modelfiles/qwen-code-14b.Modelfile"

log "installing llm-router + claude-routed"
cp "${ROOT}/scripts/llm-router.py" "${SHARE}/llm-router.py"
cp "${ROOT}/scripts/claude-routed" "${BIN}/claude-routed"
cat > "${BIN}/llm-router" <<EOF
#!/usr/bin/env bash
exec python3 "${SHARE}/llm-router.py" "\$@"
EOF
chmod 755 "${BIN}/llm-router" "${BIN}/claude-routed"

# Optional LaunchAgent on macOS
if [[ "$(uname -s)" == Darwin ]]; then
  PLIST="${HOME}/Library/LaunchAgents/com.local-llm.llm-router.plist"
  PY="$(command -v python3)"
  mkdir -p "${HOME}/Library/LaunchAgents" "${HOME}/.ollama"
  cat > "${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.local-llm.llm-router</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>${SHARE}/llm-router.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${HOME}/.ollama/llm-router.log</string>
  <key>StandardErrorPath</key><string>${HOME}/.ollama/llm-router.log</string>
</dict>
</plist>
EOF
  # Optional: put a real Anthropic key in ~/.config/local-llm-mac/anthropic.env
  # as ROUTER_ANTHROPIC_API_KEY=sk-ant-... so LaunchAgent can cloud-route.
  ENV_FILE="${HOME}/.config/local-llm-mac/anthropic.env"
  if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
    if [[ -n "${ROUTER_ANTHROPIC_API_KEY:-}${ANTHROPIC_API_KEY:-}" ]]; then
      KEY_VAL="${ROUTER_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY}}"
      /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables dict" "${PLIST}" 2>/dev/null || true
      /usr/libexec/PlistBuddy -c "Delete :EnvironmentVariables:ROUTER_ANTHROPIC_API_KEY" "${PLIST}" 2>/dev/null || true
      /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:ROUTER_ANTHROPIC_API_KEY string ${KEY_VAL}" "${PLIST}"
      log "injected ROUTER_ANTHROPIC_API_KEY into LaunchAgent from anthropic.env"
    fi
  fi
  launchctl unload "${PLIST}" >/dev/null 2>&1 || true
  launchctl load "${PLIST}"
  log "LaunchAgent loaded (com.local-llm.llm-router)"
fi

# Ensure PATH hint
MARKER="# local-llm-mac: claude-local on PATH"
LINE='export PATH="$HOME/.local/bin:$PATH"'
for rc in "${HOME}/.zprofile" "${HOME}/.zshrc"; do
  touch "${rc}"
  grep -Fq "${MARKER}" "${rc}" || printf '\n%s\n%s\n' "${MARKER}" "${LINE}" >> "${rc}"
done

log "smoke: classify a few prompts"
python3 "${SHARE}/llm-router.py" --classify "rename the helper and fix the typo"
python3 "${SHARE}/llm-router.py" --classify "implement a login form with validation"
python3 "${SHARE}/llm-router.py" --classify "root cause the flaky payment race condition across services"

cat <<EOF

Done.

1) Warm the 14B (optional):
   ollama run qwen-fast --think=false "pong"

2) Hosted lanes use Claude Code CLI login (no API key required):
   claude    # log in once if needed
   # then restart llm-router so it can read OAuth from Keychain / ~/.claude

   Optional: export ANTHROPIC_API_KEY=sk-ant-... if you have a pay-as-you-go key

3) In cmux / terminal:
   llm-router
   cd /path/to/repo
   claude-routed

Lanes: local=qwen-fast · cheap=Haiku · frontier=Sonnet
Auth: Claude Code OAuth (preferred) or API key
Overrides: x-route: local|cheap|frontier
Force: ROUTER_FORCE=local|cheap|frontier llm-router

Health: curl -s http://127.0.0.1:11437/health
# look for cloud_auth_ready / claude_cli_oauth_configured
EOF
