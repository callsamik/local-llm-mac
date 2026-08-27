# Effort / Thinking + Opus/Fable Opt-in — Implementation Plan

**Goal:** Auto-route only local/haiku/sonnet; attach effort+thinking; opus/fable on explicit request only.

**Files:** `scripts/llm-router.py`, `scripts/test-router-classify.sh`, `README.md`, `docs/HANDOFF.md`

## Task 1 — Scoring API

- Change `score_route` to return lane + effort + thinking (+ reason, score).
- Cap auto lane at sonnet; map former opus/fable difficulty → sonnet + high/xhigh.
- Opt-in phrases / overrides for opus|fable; respect `ROUTER_DISABLE_*`.
- Clamp LLM classify away from opus/fable unless opt-in.

## Task 2 — Request rewrite + cascade

- `rewrite_for_hosted`: set `output_config.effort`, `thinking` adaptive/disabled.
- Sticky session stores lane+effort+thinking.
- `cascade_from` skips disabled opus/fable; auto chains never start there.
- Logs + `/health` expose enable/disable flags and effort policy.

## Task 3 — Tests + docs

- Update fixtures: former opus/fable cases → sonnet; “use opus/fable” → those lanes.
- Assert effort/thinking on a few classify checks.
- README / HANDOFF blurb; commit.
