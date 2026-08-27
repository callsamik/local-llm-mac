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

# local
check "rename the helper and fix the typo" local
check "list the files in this folder" local
check "what is UserService?" local
check "what is a Dockerfile?" local
check "explain this function" local
check "show me the auth module" local
check "ping" local

# cheap
check "implement a login form with validation" cheap
check "add a unit test for parseDate" cheap
check "fix the bug in the save handler" cheap
check "implement oauth login with jwt" cheap
check "add a react page for settings" cheap
check "create a pytest for UserService" cheap
check "refactor the billing helper" cheap
check "wire up the webhook handler" cheap

# frontier
check "root cause the flaky payment race condition across services" frontier
check "design the architecture for a multi-service migration" frontier
check "security audit of the auth flow" frontier
check "threat model the payment flow" frontier
check "memory leak in the worker pool" frontier
check "sev-1 production outage on checkout" frontier
check "investigate why the flaky e2e breaks" frontier
check "compare trade-offs for event sourcing" frontier

echo "all classification checks passed"
