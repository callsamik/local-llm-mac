# Effort / Thinking + Opus/Fable Opt-in — Design

**Date:** 2026-08-27  
**Status:** Approved (hybrid C)  
**Parent:** heuristic router in `scripts/llm-router.py`

## Decision

1. **Auto ladder is three lanes:** `local → haiku → sonnet`.
2. **Opus and Fable are off by default** — selected only on **explicit request** (`x-route` / `ROUTER_FORCE` / opt-in phrases like “use opus”, “use fable”). Difficulty phrases (security audit, architecture, …) raise **sonnet effort**, they do **not** auto-pick opus/fable.
3. **Within a hosted lane**, the scorer also picks **effort** (`low|medium|high|xhigh|max`; user “extra” → API `xhigh`) and **thinking** (`off` or adaptive `on`).
4. **Model versions** stay env-pinned per family; cascade on errors. Cascade never *ascends*; when walking down from fable/opus, lower tiers are allowed. Auto starts never include opus/fable.
5. Hard block (optional): `ROUTER_DISABLE_OPUS=1` / `ROUTER_DISABLE_FABLE=1` → even requests fall back to sonnet.

## Effort / thinking defaults

| Selection | Effort | Thinking |
|-----------|--------|----------|
| local | — | off |
| haiku | low | off |
| sonnet (score ≈ 2) | medium | adaptive |
| sonnet (score 3–4, “opus-hard”) | high | adaptive |
| sonnet (score ≥ 5, “fable-hard”) | xhigh | adaptive (required) |
| opus (opt-in) | high (xhigh if asked) | adaptive |
| fable (opt-in) | xhigh (max if asked) | adaptive |

Never send `thinking: disabled` with effort `xhigh` or `max`. Honor client `output_config.effort` / `thinking` when already set.

## Classify JSON

```json
{"route":"sonnet","effort":"high","thinking":"adaptive","reason":"...","score":4}
```

Local: `"effort": null`, `"thinking": "off"`.
