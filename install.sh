#!/usr/bin/env bash
# Install Ollama + Qwen 14B heuristic router (primary) on a MacBook Pro M3 Pro (36GB).
# Optional: --with-27b also installs Qwen 3.8 27B as qwen-code.
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
WITH_27B=0
SKIP_ROUTER=0

usage() {
  cat <<'EOF'
Install Ollama, Qwen 14B + heuristic router (primary), Claude Code, and helpers.

Default (36GB Mac): qwen-fast (14B) + llm-router + claude-routed
  local → Haiku → Sonnet → Opus → Fable (cascade to local on errors; Claude Code OAuth)

Usage:
  ./install.sh [options]

Options:
  --with-27b         Also pull Qwen 3.8 27B as qwen-code (optional; more RAM)
  --mlx              With 27B: pull MLX nvfp4 instead of GGUF Q4 (implies --with-27b)
  --skip-router      Do not install llm-router / claude-routed / 14B pull via setup
  --skip-models      Install Ollama, Mac settings, and proxies only
  --skip-claude      Do not install Claude Code or launchers
  --smoke-test       After pull, generate one short reply (loads a model into RAM)
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
MODEL="${CLAUDE_LOCAL_MODEL:-qwen-fast}"
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
  local share
  share="$(dirname "${dest}")"
  mkdir -p "${share}"
  if [[ -d "${ROOT}/claude_desktop_proxy" ]]; then
    rm -rf "${share}/claude_desktop_proxy"
    cp -R "${ROOT}/claude_desktop_proxy" "${share}/claude_desktop_proxy"
  fi
  if [[ -f "${ROOT}/scripts/claude-desktop-proxy.py" ]]; then
    cp "${ROOT}/scripts/claude-desktop-proxy.py" "${dest}"
    chmod 644 "${dest}"
    return
  fi
  die "missing scripts/claude-desktop-proxy.py"
}

write_claude_desktop_proxy_bin() {
  local dest="$1"
  mkdir -p "$(dirname "${dest}")"
  cat > "${dest}" <<'EOF'
#!/usr/bin/env bash
# Start the Claude Desktop rewrite proxy (Anthropic ids → local model on :11434).
set -euo pipefail
PY="${CLAUDE_DESKTOP_PROXY_PY:-${HOME}/.local/share/local-llm-mac/claude-desktop-proxy.py}"
SHARE="$(dirname "${PY}")"
export PYTHONPATH="${SHARE}:${PYTHONPATH:-}"
export CLAUDE_LOCAL_MODEL="${CLAUDE_LOCAL_MODEL:-qwen-fast}"
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
    --mlx) USE_MLX_QUANT=1; WITH_27B=1 ;;
    --with-27b) WITH_27B=1 ;;
    --skip-router) SKIP_ROUTER=1 ;;
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

if [[ "${MEM_GB}" -gt 0 && "${MEM_GB}" -lt 24 ]]; then
  warn "${MEM_GB}GB is tight for local Qwen + IDE; prefer the 14B router path and close other apps."
fi

# Primary path: 14B local lane for the heuristic router.
PRIMARY_TAG="qwen3:14b"
PRIMARY_ALIAS="qwen-fast"
PRIMARY_SIZE_GB=10

LEGACY_TAG="qwen3.8:27b"
LEGACY_ALIAS="qwen-code"
LEGACY_SIZE_GB=18
if [[ "${USE_MLX_QUANT}" -eq 1 ]]; then
  LEGACY_TAG="qwen3.8:27b-nvfp4"
  LEGACY_SIZE_GB=18
fi

NEED_GB=${PRIMARY_SIZE_GB}
if [[ "${WITH_27B}" -eq 1 ]]; then
  NEED_GB=$((NEED_GB + LEGACY_SIZE_GB))
fi
NEED_GB=$((NEED_GB + 4))

if [[ "${SKIP_MODELS}" -eq 0 && "${FREE_GB}" -gt 0 && "${FREE_GB}" -lt "${NEED_GB}" ]]; then
  die "need about ${NEED_GB}GB free to pull the selected models; ${FREE_GB}GB available."
fi

if [[ "${SKIP_ROUTER}" -eq 1 && "${WITH_27B}" -eq 0 && "${SKIP_MODELS}" -eq 0 ]]; then
  warn "--skip-router with no --with-27b leaves no coding model unless you pull one yourself."
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

  # 14B is installed by install_router (setup-14b-router.sh) unless skipped.
  if [[ "${SKIP_ROUTER}" -eq 1 ]]; then
    log "pulling ${PRIMARY_TAG} (~${PRIMARY_SIZE_GB}GB) without router setup"
    run ollama pull "${PRIMARY_TAG}"
    if [[ "${DRY_RUN}" -eq 0 ]]; then
      ollama create "${PRIMARY_ALIAS}" -f "${ROOT}/modelfiles/qwen-code-14b.Modelfile"
    else
      printf 'dry-run: ollama create %s -f modelfiles/qwen-code-14b.Modelfile\n' "${PRIMARY_ALIAS}"
    fi
  fi

  if [[ "${WITH_27B}" -eq 1 ]]; then
    log "pulling optional ${LEGACY_TAG} (~${LEGACY_SIZE_GB}GB)"
    run ollama pull "${LEGACY_TAG}"
    create_alias "${LEGACY_ALIAS}" "${LEGACY_TAG}"
  fi

  # Claude Desktop rejects ids that are not claude-sonnet/opus/haiku.
  local desktop_src="${PRIMARY_ALIAS}"
  if [[ "${WITH_27B}" -eq 1 ]]; then
    desktop_src="${LEGACY_ALIAS}"
  fi
  for desktop_name in claude-sonnet-4-5 claude-sonnet-4-6; do
    log "aliasing ${desktop_src} as ${desktop_name} for Claude Desktop"
    run ollama cp "${desktop_src}" "${desktop_name}"
  done
}

install_router() {
  [[ "${SKIP_ROUTER}" -eq 0 ]] || return 0
  [[ "${SKIP_MODELS}" -eq 0 ]] || {
    warn "skipping router model pull because --skip-models; bins may still be useful later"
  }
  local setup="${ROOT}/scripts/setup-14b-router.sh"
  [[ -f "${setup}" ]] || die "missing ${setup}"
  log "installing 14B qwen-fast + llm-router + claude-routed (primary path)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: bash %s\n' "${setup}"
    return 0
  fi
  if [[ "${SKIP_MODELS}" -eq 1 ]]; then
    # Install bins only: copy from setup script logic without pull.
    local bin="${HOME}/.local/bin"
    local share="${HOME}/.local/share/local-llm-mac"
    mkdir -p "${bin}" "${share}"
    rm -rf "${share}/llm_router"
    [[ -d "${ROOT}/llm_router" ]] && cp -R "${ROOT}/llm_router" "${share}/llm_router"
    cp "${ROOT}/scripts/llm-router.py" "${share}/llm-router.py"
    cp "${ROOT}/scripts/claude-routed" "${bin}/claude-routed"
    cat > "${bin}/llm-router" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${share}:\${PYTHONPATH:-}"
exec python3 "${share}/llm-router.py" "\$@"
EOF
    chmod 755 "${bin}/llm-router" "${bin}/claude-routed"
    ensure_local_bin_on_path "${bin}"
    warn "models skipped; run ./scripts/setup-14b-router.sh later to pull qwen3:14b"
    return 0
  fi
  bash "${setup}"
}

smoke_test() {
  [[ "${SMOKE_TEST}" -eq 1 ]] || return 0
  [[ "${SKIP_MODELS}" -eq 0 ]] || return 0
  local model="${PRIMARY_ALIAS}"
  if [[ "${SKIP_ROUTER}" -eq 1 && "${WITH_27B}" -eq 1 ]]; then
    model="${LEGACY_ALIAS}"
  fi
  log "smoke test: one short generation from ${model} (loads the model into RAM)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: ollama run %s\n' "${model}"
    return 0
  fi
  ollama run "${model}" --think=false "Reply with the single word pong."
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
  <key>EnvironmentVariables</key>
  <dict>
    <key>CLAUDE_LOCAL_MODEL</key>
    <string>qwen-fast</string>
    <key>PYTHONPATH</key>
    <string>${HOME}/.local/share/local-llm-mac</string>
  </dict>
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

Primary path (36GB): heuristic router — local / haiku / sonnet / opus / fable (+ cascade).

  # once: Claude Code CLI login (subscription OAuth; no API key required)
  claude

  # cmux / terminal on your repo
  claude-routed

Health:  curl -s http://127.0.0.1:11437/health
Classify: python3 ~/.local/share/local-llm-mac/llm-router.py --classify "rename helper"

Local-only side chat (no hosted lanes):
  claude-local

Do not put ANTHROPIC_BASE_URL in ~/.zshrc — use claude-routed / claude-local only.

Claude Desktop (optional): not port 11435. Turn Ollama → Apps → Claude Off, then:
  Gateway: http://127.0.0.1:${DESKTOP_PROXY_PORT}   key: ollama   model: claude-sonnet-4-6

Local model:   ${PRIMARY_ALIAS}  (${PRIMARY_TAG}, ~${PRIMARY_SIZE_GB}GB)
Router:        http://127.0.0.1:11437
Ollama API:    http://127.0.0.1:11434
Desktop proxy: http://127.0.0.1:${DESKTOP_PROXY_PORT}
EOF
  if [[ "${WITH_27B}" -eq 1 ]]; then
    cat <<EOF
Optional 27B:  ${LEGACY_ALIAS}  (${LEGACY_TAG}, ~${LEGACY_SIZE_GB}GB)
  Prefer unloading it while using the router: ollama stop ${LEGACY_ALIAS}
EOF
  fi
}

if [[ "${IS_DARWIN}" -eq 1 ]]; then
  install_ollama_macos
else
  install_ollama_linux
fi
install_mac_env
start_ollama
install_router
pull_models
install_claude_code
install_claude_launcher
install_desktop_proxy
smoke_test
print_next_steps
