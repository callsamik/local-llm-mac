# SOLID Router Refactor — Implementation Plan

**Goal:** Split monolithic `scripts/llm-router.py` into a SOLID `llm_router` package with protocol-based DI; keep shim + tests green.

## Task 1 — Package skeleton + models/config/protocols/catalog/text

## Task 2 — Scoring (heuristic, llm, effort, composite) + auth/rewrite/cascade/session/upstream

## Task 3 — Handler + composition + CLI shim; update setup/tests

## Task 4 — Light SOLID split for desktop proxy; docs; commit
