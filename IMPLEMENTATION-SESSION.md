# Implementation session

**Goal:** Heuristic router with effort/thinking; Opus/Fable behind `ROUTER_ENABLE_*` flags.

**Enable costly tiers:**
```bash
export ROUTER_ENABLE_OPUS=1
export ROUTER_ENABLE_FABLE=1
# restart llm-router; confirm /health enable_* fields
```

**Repo:** https://github.com/callsamik/local-llm-mac  
**Mac:** `./install.sh` → `claude` login → `claude-routed`
