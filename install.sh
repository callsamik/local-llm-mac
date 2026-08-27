#!/usr/bin/env bash
# Install Ollama and the local models recommended for a MacBook Pro
# M3 Pro with 36GB unified memory (plugged in).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLLAMA_ENV_DST="${HOME}/.ollama/set-mac-env.sh"
LAUNCH_AGENT_DST="${HOME}/Library/LaunchAgents/com.ollama.mac-env.plist"
LAUNCH_AGENT_LABEL="com.ollama.mac-env"

WITH_MOE=0
WITH_DEVSTRAL=0
WITH_OMNIROUTE=0
USE_MLX_QUANT=0
USE_Q8=0
DRY_RUN=0
SMOKE_TEST=0
ALLOW_LINUX=0
SKIP_MODELS=0

usage() {
  cat <<'EOF'
Install Ollama and the Qwen 3.6 models that fit a 36GB M3 Pro.

Usage:
  ./install.sh [options]

Options:
  --mlx              Pull the MLX nvfp4 27B coding build (~20GB) instead of Q4
  --q8               Pull 27B Q8 (~30GB). Tight on 36GB; not recommended
  --with-moe         Also pull Qwen 3.6 35B-A3B coding (~23GB). Load one at a time
  --with-devstral    Also pull Devstral 24B for agentic edit-test-fix loops
  --with-omniroute   Also install OmniRoute (cloud gateway). Off by default; see README
  --skip-models      Install Ollama and Mac settings only
  --smoke-test       After pull, generate one short reply (loads the 27B into RAM)
  --dry-run          Print what would happen
  --allow-linux      Allow running the Linux Ollama installer (no MLX / LaunchAgent)
  -h, --help         Show this help
EOF
}

log()  { printf '==> %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }
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
    --q8) USE_Q8=1 ;;
    --with-moe) WITH_MOE=1 ;;
    --with-devstral) WITH_DEVSTRAL=1 ;;
    --with-omniroute) WITH_OMNIROUTE=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
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
  warn "${MEM_GB}GB is below the 32GB comfort line for Qwen 3.6 27B with a 32k context."
fi

PRIMARY_TAG="qwen3.6:27b-coding"
PRIMARY_ALIAS="qwen-code"
PRIMARY_SIZE_GB=18

if [[ "${USE_Q8}" -eq 1 && "${USE_MLX_QUANT}" -eq 1 ]]; then
  die "choose one of --mlx or --q8"
fi
if [[ "${USE_Q8}" -eq 1 ]]; then
  PRIMARY_TAG="qwen3.6:27b-q8_0"
  PRIMARY_SIZE_GB=30
  warn "Q8 is ~30GB. On 36GB this will swap if Chrome, Slack, or Cursor are open."
elif [[ "${USE_MLX_QUANT}" -eq 1 ]]; then
  PRIMARY_TAG="qwen3.6:27b-coding-nvfp4"
  PRIMARY_SIZE_GB=20
fi

MOE_TAG="qwen3.6:35b-a3b-coding"
MOE_ALIAS="qwen-fast"
MOE_SIZE_GB=23
DEVSTRAL_TAG="devstral:24b"
DEVSTRAL_ALIAS="devstral-agent"
DEVSTRAL_SIZE_GB=14

NEED_GB="${PRIMARY_SIZE_GB}"
if [[ "${WITH_MOE}" -eq 1 ]]; then
  NEED_GB=$((NEED_GB + MOE_SIZE_GB))
fi
if [[ "${WITH_DEVSTRAL}" -eq 1 ]]; then
  NEED_GB=$((NEED_GB + DEVSTRAL_SIZE_GB))
fi
NEED_GB=$((NEED_GB + 4))

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
    printf 'dry-run: install %s -> %s\n' "${ROOT}/scripts/set-ollama-env.sh" "${OLLAMA_ENV_DST}"
  else
    cp "${ROOT}/scripts/set-ollama-env.sh" "${OLLAMA_ENV_DST}"
    chmod 755 "${OLLAMA_ENV_DST}"
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
  local template="$3"
  local tmp
  tmp="$(mktemp)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'dry-run: ollama create %s FROM %s\n' "${alias_name}" "${from_model}"
    rm -f "${tmp}"
    return 0
  fi
  sed "s|{{FROM_MODEL}}|${from_model}|g" "${template}" > "${tmp}"
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
  create_alias "${PRIMARY_ALIAS}" "${PRIMARY_TAG}" "${ROOT}/modelfiles/qwen-code.Modelfile"

  if [[ "${WITH_MOE}" -eq 1 ]]; then
    log "pulling ${MOE_TAG} (~${MOE_SIZE_GB}GB)"
    run ollama pull "${MOE_TAG}"
    create_alias "${MOE_ALIAS}" "${MOE_TAG}" "${ROOT}/modelfiles/qwen-fast.Modelfile"
  fi
  if [[ "${WITH_DEVSTRAL}" -eq 1 ]]; then
    log "pulling ${DEVSTRAL_TAG} (~${DEVSTRAL_SIZE_GB}GB)"
    run ollama pull "${DEVSTRAL_TAG}"
    create_alias "${DEVSTRAL_ALIAS}" "${DEVSTRAL_TAG}" "${ROOT}/modelfiles/devstral-agent.Modelfile"
  fi
}

maybe_install_omniroute() {
  [[ "${WITH_OMNIROUTE}" -eq 1 ]] || return 0
  cat <<'EOF'
!!  OmniRoute is a multi-provider cloud gateway (local + hundreds of remote APIs).
!!  It is not required for local Qwen, and on an office laptop it can send prompts
!!  off the machine as soon as you connect a cloud provider. Continuing anyway.
EOF
  if ! command -v npm >/dev/null 2>&1; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      warn "npm is required for --with-omniroute"
      return 0
    fi
    die "npm is required for --with-omniroute. Install Node, then re-run."
  fi
  run npm install -g omniroute
  log "OmniRoute installed. Start it later with: omniroute"
  log "Do not point Cursor at it unless you intend traffic to leave this Mac."
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

print_next_steps() {
  cat <<EOF

Done.

Daily driver:  ollama run ${PRIMARY_ALIAS}
API:           http://127.0.0.1:11434
OpenAI path:   http://127.0.0.1:11434/v1
Keep-alive:    model stays loaded (plugged-in setup)
Context:       32768 tokens on ${PRIMARY_ALIAS}
Bind:          localhost only

Cursor: Settings → Models → OpenAI-compatible
  Base URL  http://127.0.0.1:11434/v1
  Model     ${PRIMARY_ALIAS}
  API key   ollama  (any non-empty string)

Load one large model at a time on 36GB. Do not keep ${PRIMARY_ALIAS} and a 35B MoE resident together.
EOF
  if [[ "${WITH_MOE}" -eq 1 ]]; then
    printf 'Fast chat:     ollama run %s\n' "${MOE_ALIAS}"
  fi
  if [[ "${WITH_DEVSTRAL}" -eq 1 ]]; then
    printf 'Agent loop:    ollama run %s\n' "${DEVSTRAL_ALIAS}"
  fi
}

if [[ "${IS_DARWIN}" -eq 1 ]]; then
  install_ollama_macos
else
  install_ollama_linux
fi
install_mac_env
start_ollama
pull_models
maybe_install_omniroute
smoke_test
print_next_steps
