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
launchctl setenv OLLAMA_CONTEXT_LENGTH "32768"
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
GlIyMmp2/gM2rOnN/yoAAA==
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
PARAMETER num_ctx 32768
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
  warn "${MEM_GB}GB is below the 32GB comfort line for Qwen 3.8 27B with a 32k agent context."
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
      log "restarting the Ollama app so MLX / keep-alive / 32k context take effect"
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
Plain "claude" still bills Anthropic — do not use it until 1 Sep.

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
Context:       32768  Thinking: medium (raise per hard bug)

From 1 Sep: keep claude-local for everyday work; use Cursor cloud or
plain claude only when the local agent is stuck.
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
