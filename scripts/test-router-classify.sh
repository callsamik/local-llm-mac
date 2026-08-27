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
check "whats this function doing" local

# haiku (everyday coding)
check "implement a login form with validation" haiku
check "add a unit test for parseDate" haiku
check "fix the bug in the save handler" haiku
check "implement oauth login with jwt" haiku
check "add a react page for settings" haiku
check "create a pytest for UserService" haiku
check "refactor the billing helper" haiku
check "wire up the webhook handler" haiku
check "pls make a login page" haiku
check "whip up a unit test for parseDate" haiku

# sonnet / opus / fable (hard ladder)
check "memory leak in the worker pool" sonnet
check "why is this broken in ci" sonnet
check "production is down on checkout" sonnet
check "security audit of the auth flow" opus
check "threat model the payment flow" opus
check "sev-1 production outage on checkout" opus
check "investigate why the flaky e2e breaks" opus
check "compare trade-offs for event sourcing" opus
check "can you dig into why payments fail randomly" opus
check "root cause the flaky payment race condition across services" fable
check "design the architecture for a multi-service migration" fable
check "company-wide migration of the platform" fable
check "use fable for this hardest problem" fable

# cascade helper
python3 - "$PY" <<'PY'
import sys
from importlib.machinery import SourceFileLoader

m = SourceFileLoader("llm_router", sys.argv[1]).load_module()
assert m.cascade_from("fable") == ["fable", "opus", "sonnet", "haiku", "local"]
assert m.cascade_from("cheap") == ["haiku", "local"]
assert m.cascade_from("frontier") == ["sonnet", "haiku", "local"]
assert m.should_failover_status(404, b"{}")
assert m.should_failover_status(429, b"{}")
assert m.should_failover_status(529, b"{}")
assert not m.should_failover_status(200, b"{}")
assert m.should_failover_status(
    400,
    b'{"error":{"type":"not_found_error","message":"model: claude-fable-5"}}',
)
print("ok  cascade helpers")
PY

echo "all classification checks passed"
