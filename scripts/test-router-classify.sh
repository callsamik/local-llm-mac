#!/usr/bin/env bash
# Unit-ish checks for llm-router classification (no Ollama required).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/scripts/llm-router.py"

check() {
  local text="$1" expect="$2"
  local got
  got="$(python3 "${PY}" --classify "${text}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["route"])')"
  if [[ "${got}" != "${expect}" ]]; then
    printf 'FAIL: %r → %s (want %s)\n' "${text}" "${got}" "${expect}" >&2
    python3 "${PY}" --classify "${text}" >&2
    exit 1
  fi
  printf 'ok  %s ← %s\n' "${expect}" "${text}"
}

check "rename the helper and fix the typo" local
check "list the files in this folder" local
check "what is UserService?" local
check "implement a login form with validation" cheap
check "add a unit test for parseDate" cheap
check "fix the bug in the save handler" cheap
check "root cause the flaky payment race condition across services" frontier
check "design the architecture for a multi-service migration" frontier
check "security audit of the auth flow" frontier
echo "all classification checks passed"
