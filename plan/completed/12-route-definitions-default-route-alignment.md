# Route Definitions: Default Route Alignment (And Typos)

**Status**: 📋 Backlog
**Priority**: 12
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Routing in SandVoice depends on the model returning a valid route name that matches the plugin registry.

Today, `routes.yaml` contains a typo and inconsistent default route naming that can cause unnecessary fallbacks and makes the system harder to reason about.

This task aligns route names across:
- routing prompt (`routes.yaml`)
- error fallback in `common/ai.py`
- plugin keys in `sandvoice.py`

---

## Problem Statement

Observed issues:
- `routes.yaml` defines `default-rote` (typo) instead of a consistent default route name.
- `common/ai.py:AI.define_route()` returns `{ "route": "default-route" ... }` on failures.

Impact:
- The routing prompt can encourage the model to emit an invalid/unknown route string.
- Behavior becomes “accidentally correct” (falls back to generic response) rather than intentionally correct.

---

## Goals

- Standardize on one default route name across the codebase (recommend: `default-route`)
- Ensure the routing prompt only lists valid route identifiers
- Preserve backward compatibility if any existing users/configs rely on `default-rote`
- Add small tests so route name drift is caught early

---

## Non-Goals

- Changing the overall routing policy (e.g., adding new route categories)
- Rewriting the prompt style beyond what’s needed for correctness

---

## Proposed Design

### 1) Fix route name typo in the prompt

- Update `routes.yaml` to use `default-route` (or `default`) consistently.

### 2) Compatibility alias (optional but recommended)

- Add a route normalization step so `default-rote` (legacy typo) maps to `default-route`.
- Apply normalization in the same place as other route string compatibility (see backlog task 11).

### 3) Tighten the contract in code

- Ensure `AI.define_route()` fallback uses the same default route name listed in `routes.yaml`.
- Consider validating that returned JSON has a `route` string and `reason` string; if invalid, normalize to default.

---

## Acceptance Criteria

- [ ] `routes.yaml` lists `default-route` (no `default-rote` typo)
- [ ] On routing failures, the system uses the same default route name everywhere
- [ ] If the model returns `default-rote`, SandVoice normalizes it to `default-route`
- [ ] No user-visible regressions (general questions still get answered)

---

## Testing

- Unit test: route normalization maps `default-rote` -> `default-route`
- Unit test: `AI.define_route()` fallback returns a valid route identifier
