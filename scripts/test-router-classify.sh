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

check_meta() {
  local text="$1" expect_route="$2" expect_effort="$3" expect_thinking="$4"
  local got
  got="$(python3 "${PY}" --classify "${text}")"
  python3 -c '
import json,sys
d=json.loads(sys.argv[1])
assert d["route"]==sys.argv[2], d
assert d.get("effort")== (None if sys.argv[3]=="null" else sys.argv[3]), d
assert d["thinking"]==sys.argv[4], d
' "${got}" "${expect_route}" "${expect_effort}" "${expect_thinking}"
  printf 'ok  %s effort=%s thinking=%s ← %s\n' \
    "${expect_route}" "${expect_effort}" "${expect_thinking}" "${text}"
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

# hard work stays on sonnet while opus/fable flags are off (default)
check "memory leak in the worker pool" sonnet
check "why is this broken in ci" sonnet
check "production is down on checkout" sonnet
check "security audit of the auth flow" sonnet
check "threat model the payment flow" sonnet
check "sev-1 production outage on checkout" sonnet
check "investigate why the flaky e2e breaks" sonnet
check "compare trade-offs for event sourcing" sonnet
check "can you dig into why payments fail randomly" sonnet
check "root cause the flaky payment race condition across services" sonnet
check "design the architecture for a multi-service migration" sonnet
check "company-wide migration of the platform" sonnet

# explicit ask still gated by enable flags (default off → sonnet)
check "use fable for this hardest problem" sonnet
check "use opus for this security audit" sonnet

# effort / thinking defaults (flags off → sonnet caps)
check_meta "rename the helper and fix the typo" local null off
check_meta "implement a login form with validation" haiku low off
check_meta "memory leak in the worker pool" sonnet medium adaptive
check_meta "security audit of the auth flow" sonnet high adaptive
check_meta "company-wide migration of the platform" sonnet xhigh adaptive

# cascade + enable-flag helpers
python3 - "$PY" <<'PY'
import sys
from importlib.machinery import SourceFileLoader

m = SourceFileLoader("llm_router", sys.argv[1]).load_module()

# Defaults: opus/fable off
assert m.Cfg.enable_opus is False
assert m.Cfg.enable_fable is False
assert m.cascade_from("fable") == ["sonnet", "haiku", "local"]
assert m.cascade_from("cheap") == ["haiku", "local"]

# Enable both → full cascade from fable
m.Cfg.enable_opus = True
m.Cfg.enable_fable = True
m.Cfg.disable_opus = False
m.Cfg.disable_fable = False
assert m.cascade_from("fable") == ["fable", "opus", "sonnet", "haiku", "local"]

# Category auto-assign when enabled
d = m.score_route(
    "security audit of the auth flow",
    {"messages": [{"role": "user", "content": "security audit of the auth flow"}]},
)
assert d.lane == "opus", d
d = m.score_route(
    "company-wide migration of the platform",
    {"messages": [{"role": "user", "content": "company-wide migration of the platform"}]},
)
assert d.lane == "fable", d
d = m.score_route(
    "use opus for this security audit",
    {"messages": [{"role": "user", "content": "use opus for this security audit"}]},
)
assert d.lane == "opus", d

# Turn fable off → company-wide falls to opus (still enabled)
m.Cfg.enable_fable = False
m.Cfg.disable_fable = True
d = m.score_route(
    "company-wide migration of the platform",
    {"messages": [{"role": "user", "content": "company-wide migration of the platform"}]},
)
assert d.lane == "opus", d

# Both off → sonnet
m.Cfg.enable_opus = False
m.Cfg.disable_opus = True
d = m.score_route(
    "security audit of the auth flow",
    {"messages": [{"role": "user", "content": "security audit of the auth flow"}]},
)
assert d.lane == "sonnet", d

# reset
m.Cfg.enable_opus = False
m.Cfg.enable_fable = False
m.Cfg.disable_opus = True
m.Cfg.disable_fable = True

assert m.should_failover_status(404, b"{}")
assert m.normalize_effort("extra") == "xhigh"
assert m.effort_thinking_for("sonnet", 6)[0] == "xhigh"

payload = m.rewrite_for_hosted({"messages": []}, "claude-sonnet-4-6", "high", "adaptive")
assert payload["output_config"]["effort"] == "high"

print("ok  cascade / enable-flag / frontier helpers")
PY

echo "all classification checks passed"
