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

# reason (local DeepSeek-R1: algorithms / maths / logic)
check "what is the time complexity of this algorithm" reason
check "explain the dynamic programming solution" reason
check "check my logic for this off-by-one" reason
check "is my math correct here" reason
check "reason through why this invariant holds" reason
check "which data structure is faster for lookups" reason

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
check "implement dijkstra shortest path algorithm" haiku

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
check "prove correctness of the lock-free queue algorithm" sonnet

# explicit ask still gated by enable flags (default off → sonnet)
check "use fable for this hardest problem" sonnet
check "use opus for this security audit" sonnet

# effort / thinking defaults (flags off → sonnet caps)
check_meta "rename the helper and fix the typo" local null off
check_meta "what is the time complexity of this algorithm" reason null adaptive
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
assert m.cascade_from("fable") == ["sonnet", "haiku", "reason", "local"]
assert m.cascade_from("cheap") == ["haiku", "reason", "local"]
assert m.cascade_from("reason") == ["reason", "local"]

# Enable both → full cascade from fable
m.Cfg.enable_opus = True
m.Cfg.enable_fable = True
m.Cfg.disable_opus = False
m.Cfg.disable_fable = False
assert m.cascade_from("fable") == ["fable", "opus", "sonnet", "haiku", "reason", "local"]

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

# reason lane helpers
assert m.normalize_lane("r1") == "reason"
assert m.normalize_lane("deepseek") == "reason"
assert m.model_for_lane("reason") == m.Cfg.reason_model
assert m.local_fallback_lane("sonnet") == "reason"
assert m.local_fallback_lane("opus") == "reason"
assert m.local_fallback_lane("haiku") == "local"
assert m.local_fallback_lane("reason") == "reason"
assert m.local_fallback_lane("local") == "local"
assert m.rewrite_for_local({"messages": []})["model"] == m.Cfg.local_model
assert m.rewrite_for_local({"messages": []}, "reason")["model"] == m.Cfg.reason_model

# No cloud auth: hard prompt → reason, medium → local
RouteDecider = sys.modules["llm_router.routing"].RouteDecider
CompositeScorer = sys.modules["llm_router.scoring.composite"].CompositeScorer
InMemorySessionStore = sys.modules["llm_router.session"].InMemorySessionStore


class NoCloud:
    def cloud_auth_ready(self, headers):
        return False


def decide(text, headers=None):
    decider = RouteDecider(CompositeScorer(), InMemorySessionStore(), NoCloud())
    return decider.decide(headers or {}, {"messages": [{"role": "user", "content": text}]})


import os
os.environ["ROUTER_CLASSIFY_OFFLINE"] = "1"
assert decide("memory leak in the worker pool").lane == "reason"
assert decide("implement a login form with validation").lane == "local"
assert decide("anything", {"x-route": "sonnet"}).lane == "reason"
assert decide("anything", {"x-route": "r1"}).lane == "reason"
print("ok  reason lane helpers / cloud-unavailable fallback")

# Idle unloader: unload only after the last in-flight request is idle
import time
IdleUnloader = sys.modules["llm_router.idle_unload"].IdleUnloader
unloaded = []
u = IdleUnloader(0.05, unloaded.append)
u.hold("deepseek-reason")
u.hold("deepseek-reason")
u.release("deepseek-reason")
time.sleep(0.1)
assert unloaded == [], unloaded
u.release("deepseek-reason")
u.hold("deepseek-reason")
time.sleep(0.1)
assert unloaded == [], unloaded
u.release("deepseek-reason")
time.sleep(0.15)
assert unloaded == ["deepseek-reason"], unloaded
off = IdleUnloader(0, unloaded.append)
off.hold("x")
off.release("x")
time.sleep(0.05)
assert unloaded == ["deepseek-reason"], unloaded
print("ok  idle unloader")
PY

echo "all classification checks passed"
