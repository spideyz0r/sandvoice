# Plugin Route Name Normalization (Hyphens vs Underscores)

**Status**: 📋 Backlog
**Priority**: 11
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

SandVoice routes are user/LLM-facing strings (from `routes.yaml`) that map to plugin modules under `plugins/`.

Today at least one route uses a hyphenated name (`hacker-news`), while Python imports require valid module identifiers (no `-`). This can prevent plugins from loading and makes route naming fragile.

This task standardizes plugin module naming and adds a small compatibility layer so route names can remain hyphenated without breaking Python imports.

---

## Problem Statement

Current behavior:
- `sandvoice.py` loads plugins by filename and imports them via `importlib.import_module(f"plugins.{module_name}")`.
- Files like `plugins/hacker-news.py` cannot be imported because `hacker-news` is not a valid Python module name.

Impact:
- The `hacker-news` route is effectively broken (plugin never loads, route falls back to generic response).
- Adding new plugins with hyphenated names will silently fail.

---

## Goals

- Ensure every plugin in `plugins/` is importable on all platforms
- Allow route names to use hyphens (voice-friendly) while keeping Python modules underscore-safe
- Preserve backward compatibility for any existing route strings (e.g., `hacker-news`)
- Make failures obvious in debug mode (clear log/print when plugin load fails)

---

## Non-Goals

- Redesign of the routing prompt or plugin API
- Dynamic plugin discovery beyond the current directory scan

---

## Proposed Design

### 1) Standardize plugin filenames/modules

- Rename hyphenated plugin files to underscore form:
  - `plugins/hacker-news.py` -> `plugins/hacker_news.py`
- Keep the route name as-is (hyphenated) for LLM prompt readability.

### 2) Add route/plugin name normalization and aliases

Introduce a normalization function used in both plugin registration and route dispatch:

- Canonical plugin key: underscore form (module identifier)
- Supported aliases:
  - Hyphen form (`hacker-news`) should resolve to underscore module (`hacker_news`)
  - Underscore form should also resolve (useful for tests/manual invocation)

Implementation sketch:
- In `SandVoice.load_plugins()`:
  - Register a plugin under its module name (underscore)
  - Also register an alias key with hyphens (replace `_` -> `-`) when different
- In `SandVoice.route_message()`:
  - If `route["route"]` not found, try a normalized variant (`-` -> `_`) before falling back

This keeps `routes.yaml` stable while allowing pythonic module names.

---

## Acceptance Criteria

- [ ] `hacker-news` route triggers the Hacker News plugin reliably
- [ ] Plugin loader imports all plugins successfully (no silent failures due to invalid module names)
- [ ] Route dispatch supports both `hacker-news` and `hacker_news` (alias behavior)
- [ ] Debug mode prints a clear error if a plugin fails to load (including filename)

---

## Testing

- Unit test: plugin loader registers alias keys correctly
- Unit test: route dispatch normalizes `hacker-news` -> `hacker_news`
- Smoke test: run `python sandvoice.py --cli` and ask for Hacker News
