#!/usr/bin/env bash
# Install Ollama and Qwen 3.8 27B for agentic coding on a MacBook Pro M3 Pro (36GB).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLLAMA_ENV_DST="${HOME}/.ollama/set-mac-env.sh"
LAUNCH_AGENT_DST="${HOME}/Library/LaunchAgents/com.ollama.mac-env.plist"
LAUNCH_AGENT_LABEL="com.ollama.mac-env"
DESKTOP_PROXY_PY_DST="${HOME}/.local/share/local-llm-mac/claude-desktop-proxy.py"
DESKTOP_PROXY_BIN_DST="${HOME}/.local/bin/claude-desktop-proxy"
DESKTOP_PROXY_AGENT_DST="${HOME}/Library/LaunchAgents/com.local-llm.claude-desktop-proxy.plist"
DESKTOP_PROXY_AGENT_LABEL="com.local-llm.claude-desktop-proxy"
DESKTOP_PROXY_PORT="11436"

USE_MLX_QUANT=0
DRY_RUN=0
SMOKE_TEST=0
ALLOW_LINUX=0
SKIP_MODELS=0
SKIP_CLAUDE=0

usage() {
  cat <<'EOF'
Install Ollama, Qwen 3.8 27B, Claude Code, and a Claude Desktop rewrite proxy.

Usage:
  ./install.sh [options]

Options:
  --mlx              Pull the MLX nvfp4 build (~18GB) instead of GGUF Q4
  --skip-models      Install Ollama, Mac settings, and the Desktop proxy only
  --skip-claude      Do not install Claude Code or the claude-local launcher
  --smoke-test       After pull, generate one short reply (loads the 27B into RAM)
  --dry-run          Print what would happen
  --allow-linux      Allow running the Linux Ollama installer (no MLX / LaunchAgent)
  -h, --help         Show this help
EOF
}

log()  { printf '==> %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

write_ollama_env_script() {
  local dest="$1"
  cat > "${dest}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
launchctl setenv OLLAMA_HOST "127.0.0.1:11434"
launchctl setenv OLLAMA_KEEP_ALIVE "-1"
launchctl setenv OLLAMA_FLASH_ATTENTION "1"
launchctl setenv OLLAMA_MLX "1"
launchctl setenv OLLAMA_CONTEXT_LENGTH "49152"
launchctl setenv OLLAMA_NUM_PARALLEL "1"
EOF
  chmod 755 "${dest}"
}

write_claude_local_script() {
  local dest="$1"
  cat > "${dest}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
MODEL="${CLAUDE_LOCAL_MODEL:-qwen-code}"
HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
if [[ "${HOST}" != http* ]]; then
  BASE_URL="http://${HOST}"
else
  BASE_URL="${HOST}"
fi
if ! curl -sf "${BASE_URL}/api/tags" >/dev/null 2>&1; then
  printf 'error: Ollama is not running at %s\nOpen the Ollama app, then retry.\n' "${BASE_URL}" >&2
  exit 1
fi
unset CLAUDE_CODE_USE_BEDROCK
unset AWS_REGION AWS_DEFAULT_REGION
export ANTHROPIC_AUTH_TOKEN="ollama"
export ANTHROPIC_API_KEY=""
export ANTHROPIC_BASE_URL="${BASE_URL}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${ANTHROPIC_DEFAULT_HAIKU_MODEL:-${MODEL}}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-${MODEL}}"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-${MODEL}}"
if command -v claude >/dev/null 2>&1; then
  exec claude --model "${MODEL}" "$@"
fi
if command -v ollama >/dev/null 2>&1 && ollama launch --help >/dev/null 2>&1; then
  exec ollama launch claude --model "${MODEL}" --yes -- "$@"
fi
printf 'error: Claude Code CLI not found.\nInstall it, then retry:\n  curl -fsSL https://claude.ai/install.sh | bash\n' >&2
exit 1
EOF
  chmod 755 "${dest}"
}

write_claude_desktop_proxy_py() {
  local dest="$1"
  mkdir -p "$(dirname "${dest}")"
  if [[ -f "${ROOT}/scripts/claude-desktop-proxy.py" ]]; then
    cp "${ROOT}/scripts/claude-desktop-proxy.py" "${dest}"
    chmod 644 "${dest}"
    return
  fi
  python3 - "${dest}" <<'PY'
import base64, gzip, pathlib, sys
blob = """
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
"""
pathlib.Path(sys.argv[1]).write_bytes(gzip.decompress(base64.b64decode("".join(blob.split()))))
PY
  chmod 644 "${dest}"
}

write_claude_desktop_proxy_bin() {
  local dest="$1"
  mkdir -p "$(dirname "${dest}")"
  cat > "${dest}" <<'EOF'
#!/usr/bin/env bash
# Start the Claude Desktop rewrite proxy (Anthropic ids → qwen-code on :11434).
set -euo pipefail
PY="${CLAUDE_DESKTOP_PROXY_PY:-${HOME}/.local/share/local-llm-mac/claude-desktop-proxy.py}"
if [[ ! -f "${PY}" ]]; then
  printf 'error: %s not found. Re-run install.sh.\n' "${PY}" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf 'error: python3 is required for the Claude Desktop proxy.\n' >&2
  exit 1
fi
if curl -sf "http://127.0.0.1:11435/v1/models" >/dev/null 2>&1 \
  || nc -z 127.0.0.1 11435 >/dev/null 2>&1; then
  printf '!!  Ollama Claude sidecar is listening on 11435.\n' >&2
  printf '!!  That is the process that returns: unknown Claude model "claude-sonnet-4-6"\n' >&2
  printf '!!  Turn it Off: Ollama menu → Apps → Claude → Off\n' >&2
  printf '!!  Then in Claude Desktop set Gateway to http://127.0.0.1:11436\n' >&2
fi
if ! curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
  printf 'warning: Ollama is not responding on 127.0.0.1:11434. Open the Ollama app.\n' >&2
fi
exec python3 "${PY}" "$@"
EOF
  chmod 755 "${dest}"
}

write_qwen_modelfile() {
  local dest="$1"
  local from_model="$2"
  cat > "${dest}" <<EOF
FROM ${from_model}
PARAMETER num_ctx 49152
PARAMETER num_predict 8192
PARAMETER temperature 0.6
PARAMETER top_p 0.95
PARAMETER top_k 20
PARAMETER repeat_penalty 1.05

SYSTEM """You are a local coding agent on this machine. Think before you act, then finish the job.

Reasoning effort is set to medium. Think carefully, validate key assumptions, then move to a concrete plan and execute. Do not loop on alternatives or rewrite the same approach. If blocked, say what you tried and what you need.

For multi-step work: inspect the relevant files, make the smallest correct change, run or reason about tests, and continue until the task is done or you are blocked. Prefer applying a patch over dumping a whole file. Do not claim you ran a command you did not run.
"""
EOF
}

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: %s\n' "$*"
    return 0
  fi
  "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mlx) USE_MLX_QUANT=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
    --skip-claude) SKIP_CLAUDE=1 ;;
    --smoke-test) SMOKE_TEST=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --allow-linux) ALLOW_LINUX=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

OS="$(uname -s)"
ARCH="$(uname -m)"
IS_DARWIN=0
[[ "${OS}" == Darwin ]] && IS_DARWIN=1

if [[ "${IS_DARWIN}" -eq 0 && "${ALLOW_LINUX}" -eq 0 ]]; then
  die "this installer targets macOS Apple Silicon. Pass --allow-linux to continue on ${OS}."
fi
if [[ "${IS_DARWIN}" -eq 1 && "${ARCH}" != arm64 && "${ARCH}" != aarch64 ]]; then
  warn "this machine is ${ARCH}. The model picks assume Apple Silicon unified memory."
fi

mem_gb() {
  if [[ "${IS_DARWIN}" -eq 1 ]]; then
    local bytes
    bytes="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
    echo $((bytes / 1024 / 1024 / 1024))
  elif [[ -r /proc/meminfo ]]; then
    awk '/MemTotal/ { printf "%d", $2/1024/1024 }' /proc/meminfo
  else
    echo 0
  fi
}

free_gb() {
  if [[ "${IS_DARWIN}" -eq 1 ]]; then
    df -g "${HOME}" | awk 'NR==2 { print $4 }'
  else
    df -BG "${HOME}" | awk 'NR==2 { gsub(/G/, "", $4); print $4 }'
  fi
}

MEM_GB="$(mem_gb)"
FREE_GB="$(free_gb)"
log "hardware: ${OS} ${ARCH}, ${MEM_GB}GB RAM, ${FREE_GB}GB free on the home volume"

if [[ "${MEM_GB}" -gt 0 && "${MEM_GB}" -lt 32 ]]; then
  warn "${MEM_GB}GB is below the 32GB comfort line for Qwen 3.8 27B with a 49k agent context."
fi

PRIMARY_TAG="qwen3.8:27b"
PRIMARY_ALIAS="qwen-code"
PRIMARY_SIZE_GB=18

if [[ "${USE_MLX_QUANT}" -eq 1 ]]; then
  PRIMARY_TAG="qwen3.8:27b-nvfp4"
  PRIMARY_SIZE_GB=18
fi

NEED_GB=$((PRIMARY_SIZE_GB + 4))

if [[ "${SKIP_MODELS}" -eq 0 && "${FREE_GB}" -gt 0 && "${FREE_GB}" -lt "${NEED_GB}" ]]; then
  die "need about ${NEED_GB}GB free to pull the selected models; ${FREE_GB}GB available."
fi

start_ollama_cli() {
  local bin=""
  if bin="$(find_ollama)"; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      printf 'dry-run: %s serve\n' "${bin}"
    else
      nohup "${bin}" serve >/tmp/ollama-serve.log 2>&1 &
    fi
  elif [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: ollama serve\n'
  else
    die "ollama CLI not found; install Ollama and re-run"
  fi
}

wait_for_ollama() {
  local i
  for i in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

find_ollama() {
  if command -v ollama >/dev/null 2>&1; then
    command -v ollama
    return 0
  fi
  local candidate
  for candidate in \
    "/usr/local/bin/ollama" \
    "/opt/homebrew/bin/ollama" \
    "${HOME}/Applications/Ollama.app/Contents/Resources/ollama" \
    "/Applications/Ollama.app/Contents/Resources/ollama"; do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

install_ollama_macos() {
  if find_ollama >/dev/null; then
    log "Ollama already installed: $(find_ollama)"
    return 0
  fi

  if command -v brew >/dev/null 2>&1; then
    log "installing Ollama with Homebrew"
    if brew info --cask ollama >/dev/null 2>&1; then
      run brew install --cask ollama
    else
      run brew install ollama
    fi
    return 0
  fi

  log "Homebrew not found; downloading the official Mac app into ~/Applications"
  local dmg="/tmp/Ollama.dmg"
  run mkdir -p "${HOME}/Applications"
  run curl -fL --retry 3 --retry-delay 2 -o "${dmg}" "https://ollama.com/download/Ollama.dmg"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi
  local mount
  mount="$(hdiutil attach "${dmg}" -nobrowse -mountrandom /tmp | awk '/\/Volumes\// || /\/tmp\// { print $NF; exit }')"
  [[ -n "${mount}" ]] || die "failed to mount Ollama.dmg"
  if [[ -d "${mount}/Ollama.app" ]]; then
    rm -rf "${HOME}/Applications/Ollama.app"
    cp -R "${mount}/Ollama.app" "${HOME}/Applications/"
  else
    hdiutil detach "${mount}" -quiet || true
    die "Ollama.app not found inside the disk image"
  fi
  hdiutil detach "${mount}" -quiet || true
}

install_ollama_linux() {
  if command -v ollama >/dev/null 2>&1; then
    log "Ollama already installed: $(command -v ollama)"
    return 0
  fi
  log "installing Ollama with the official Linux script"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: curl -fsSL https://ollama.com/install.sh | sh\n'
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
}

start_ollama() {
  if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    log "Ollama API already listening on 127.0.0.1:11434"
    return 0
  fi
  if [[ "${IS_DARWIN}" -eq 1 ]]; then
    if [[ -d "${HOME}/Applications/Ollama.app" ]]; then
      run open -a "${HOME}/Applications/Ollama.app"
    elif [[ -d "/Applications/Ollama.app" ]]; then
      run open -a Ollama
    elif command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q ollama; then
      run brew services start ollama
    else
      start_ollama_cli
    fi
  else
    if command -v systemctl >/dev/null 2>&1; then
      run sudo systemctl start ollama || true
    fi
    if ! curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      start_ollama_cli
    fi
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi
  log "waiting for Ollama on 127.0.0.1:11434"
  wait_for_ollama || die "Ollama did not become ready. Open the Ollama app and re-run."
}

install_mac_env() {
  [[ "${IS_DARWIN}" -eq 1 ]] || return 0
  log "writing persistent Ollama environment for the macOS app"
  run mkdir -p "${HOME}/.ollama" "${HOME}/Library/LaunchAgents"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: write %s\n' "${OLLAMA_ENV_DST}"
  else
    write_ollama_env_script "${OLLAMA_ENV_DST}"
  fi

  local plist
  plist="$(cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LAUNCH_AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${OLLAMA_ENV_DST}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF
)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: write LaunchAgent %s\n' "${LAUNCH_AGENT_DST}"
  else
    printf '%s\n' "${plist}" > "${LAUNCH_AGENT_DST}"
    launchctl unload "${LAUNCH_AGENT_DST}" >/dev/null 2>&1 || true
    launchctl load "${LAUNCH_AGENT_DST}"
    bash "${OLLAMA_ENV_DST}"
  fi

  if [[ "${DRY_RUN}" -eq 0 ]]; then
    if pgrep -x Ollama >/dev/null 2>&1; then
      log "restarting the Ollama app so MLX / keep-alive / 49k context take effect"
      killall Ollama >/dev/null 2>&1 || true
      sleep 1
      if [[ -d "${HOME}/Applications/Ollama.app" ]]; then
        open -a "${HOME}/Applications/Ollama.app"
      else
        open -a Ollama 2>/dev/null || true
      fi
      wait_for_ollama || warn "Ollama did not come back after restart; open it from Applications and re-run."
    fi
  fi
}

create_alias() {
  local alias_name="$1"
  local from_model="$2"
  local tmp
  tmp="$(mktemp)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: ollama create %s FROM %s\n' "${alias_name}" "${from_model}"
    rm -f "${tmp}"
    return 0
  fi
  write_qwen_modelfile "${tmp}" "${from_model}"
  ollama create "${alias_name}" -f "${tmp}"
  rm -f "${tmp}"
}

pull_models() {
  [[ "${SKIP_MODELS}" -eq 0 ]] || return 0
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    local ollama_bin
    ollama_bin="$(find_ollama)" || die "ollama CLI not on PATH after install"
    export PATH="$(dirname "${ollama_bin}"):${PATH}"
  fi

  log "pulling ${PRIMARY_TAG} (~${PRIMARY_SIZE_GB}GB). This can take a while."
  run ollama pull "${PRIMARY_TAG}"
  create_alias "${PRIMARY_ALIAS}" "${PRIMARY_TAG}"
  # Claude Desktop rejects ids that are not claude-sonnet/opus/haiku.
  # Same local weights, names the app will accept.
  for desktop_name in claude-sonnet-4-5 claude-sonnet-4-6; do
    log "aliasing ${PRIMARY_ALIAS} as ${desktop_name} for Claude Desktop"
    run ollama cp "${PRIMARY_ALIAS}" "${desktop_name}"
  done
}

smoke_test() {
  [[ "${SMOKE_TEST}" -eq 1 ]] || return 0
  [[ "${SKIP_MODELS}" -eq 0 ]] || return 0
  log "smoke test: one short generation from ${PRIMARY_ALIAS} (loads the model into RAM)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: ollama run %s\n' "${PRIMARY_ALIAS}"
    return 0
  fi
  ollama run "${PRIMARY_ALIAS}" "Reply with the single word pong."
}

install_claude_code() {
  [[ "${SKIP_CLAUDE}" -eq 0 ]] || return 0
  if command -v claude >/dev/null 2>&1; then
    log "Claude Code already installed: $(command -v claude)"
    return 0
  fi

  log "installing Claude Code (the agent CLI). It will talk to local Qwen, not Anthropic, via claude-local."
  if command -v brew >/dev/null 2>&1; then
    if brew info --cask claude-code >/dev/null 2>&1; then
      run brew install --cask claude-code
      return 0
    fi
    if brew info claude-code >/dev/null 2>&1; then
      run brew install claude-code
      return 0
    fi
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: curl -fsSL https://claude.ai/install.sh | bash\n'
    return 0
  fi

  if curl -fsSL https://claude.ai/install.sh | bash; then
    return 0
  fi

  if command -v npm >/dev/null 2>&1; then
    log "official installer failed; trying npm"
    run npm install -g @anthropic-ai/claude-code
    return 0
  fi

  warn "could not install Claude Code automatically. Install it, then run: ${HOME}/.local/bin/claude-local"
}

install_claude_launcher() {
  [[ "${SKIP_CLAUDE}" -eq 0 ]] || return 0
  local dest_dir="${HOME}/.local/bin"
  local dest="${dest_dir}/claude-local"
  log "installing claude-local launcher to ${dest}"
  run mkdir -p "${dest_dir}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: write %s\n' "${dest}"
  else
    write_claude_local_script "${dest}"
  fi
  ensure_local_bin_on_path "${dest_dir}"
}

install_desktop_proxy() {
  log "installing Claude Desktop rewrite proxy on 127.0.0.1:${DESKTOP_PROXY_PORT}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: write %s and %s\n' "${DESKTOP_PROXY_PY_DST}" "${DESKTOP_PROXY_BIN_DST}"
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found; skip Claude Desktop proxy. Install Python 3 and re-run."
    return 0
  fi
  write_claude_desktop_proxy_py "${DESKTOP_PROXY_PY_DST}"
  write_claude_desktop_proxy_bin "${DESKTOP_PROXY_BIN_DST}"
  ensure_local_bin_on_path "$(dirname "${DESKTOP_PROXY_BIN_DST}")"

  [[ "${IS_DARWIN}" -eq 1 ]] || return 0

  local py_bin
  py_bin="$(command -v python3)"
  mkdir -p "${HOME}/Library/LaunchAgents" "${HOME}/.ollama"
  local log_file="${HOME}/.ollama/claude-desktop-proxy.log"
  cat > "${DESKTOP_PROXY_AGENT_DST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${DESKTOP_PROXY_AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${py_bin}</string>
    <string>${DESKTOP_PROXY_PY_DST}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>${log_file}</string>
  <key>StandardErrorPath</key>
  <string>${log_file}</string>
</dict>
</plist>
EOF
  launchctl unload "${DESKTOP_PROXY_AGENT_DST}" >/dev/null 2>&1 || true
  launchctl load "${DESKTOP_PROXY_AGENT_DST}"
  if curl -sf "http://127.0.0.1:${DESKTOP_PROXY_PORT}/health" >/dev/null 2>&1; then
    log "Claude Desktop proxy is up at http://127.0.0.1:${DESKTOP_PROXY_PORT}"
  else
    warn "proxy LaunchAgent loaded but http://127.0.0.1:${DESKTOP_PROXY_PORT}/health is not ready yet"
    warn "start it with: claude-desktop-proxy"
  fi
}

ensure_local_bin_on_path() {
  local dest_dir="$1"
  local marker="# local-llm-mac: claude-local on PATH"
  local line='export PATH="$HOME/.local/bin:$PATH"'
  local rc
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: append PATH hint to ~/.zprofile and ~/.zshrc if missing\n'
    return 0
  fi
  for rc in "${HOME}/.zprofile" "${HOME}/.zshrc"; do
    touch "${rc}"
    if ! grep -Fq "${marker}" "${rc}"; then
      printf '\n%s\n%s\n' "${marker}" "${line}" >> "${rc}"
    fi
  done
  export PATH="${dest_dir}:${PATH}"
  log "ensured ~/.local/bin is on PATH in ~/.zprofile and ~/.zshrc (new terminals only)"
}

print_next_steps() {
  cat <<EOF

Done.

Until Cursor / Claude credits reset: use the terminal, not Cursor Agent.

  cd /path/to/your/repo
  claude-local

That is Claude Code + local Qwen 3.8. No Anthropic or Cursor usage.
Plain "claude" still bills Anthropic — do not use it while balance is exhausted.

Claude Desktop (the app) is not port 11435. That sidecar returns:
  unknown Claude model "claude-sonnet-4-6"
Turn Ollama → Apps → Claude  Off, then:

  Gateway base URL:  http://127.0.0.1:${DESKTOP_PROXY_PORT}
  API key:           ollama
  Auth:              x-api-key
  Model:             claude-sonnet-4-6
  Tier:              sonnet

The rewrite proxy maps that name to local ${PRIMARY_ALIAS}. Cmd+Q Desktop, reopen.

Model:         ${PRIMARY_ALIAS}  (${PRIMARY_TAG}, ~${PRIMARY_SIZE_GB}GB)
API:           http://127.0.0.1:11434 (Ollama)
Desktop proxy: http://127.0.0.1:${DESKTOP_PROXY_PORT}
Keep-alive:    model stays loaded
Context:       49152  Thinking: medium (raise per hard bug)

Whenever balance is back: keep claude-local for everyday work; use Cursor
cloud or plain claude only when the local agent is stuck.
EOF
}

if [[ "${IS_DARWIN}" -eq 1 ]]; then
  install_ollama_macos
else
  install_ollama_linux
fi
install_mac_env
start_ollama
pull_models
install_claude_code
install_claude_launcher
install_desktop_proxy
smoke_test
print_next_steps
