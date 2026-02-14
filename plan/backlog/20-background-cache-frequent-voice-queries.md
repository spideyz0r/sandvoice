# Voice UX: Background Cache for Frequent Queries

**Status**: 📋 Backlog
**Priority**: 20
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

For a few common voice queries (weather, a handful of tickers/crypto, time-sensitive greetings), the user cares most about instant feedback.

This plan adds an opt-in cache for a small set of common answers so SandVoice can respond immediately with real content.

Key behavior: respond from cache immediately when allowed, and "kick" a refresh in the background so the next request stays fast.

---

## Problem Statement

Current behavior:
- Every request waits for network/API calls.

Desired behavior:
- For selected query types, respond instantly from a cached value when allowed.
- Refresh happens in the background when a cache entry is missing or expired.

---

## Goals

- Instant voice answers for frequently requested info
- Avoid unsolicited spoken updates (only speak on user request)
- Keep refresh predictable and configurable (cost control)
- Make caching opt-in

---

## Non-Goals

- General caching of arbitrary user questions
- Learning user behavior automatically without explicit config
- Voice UX conventions like saying "as of X minutes" (we want it to sound current)

---

## Proposed Design

### Where caching lives

- Caching is a shared capability exposed to plugins (not duplicated per plugin).
- The route system still selects a plugin; the plugin decides whether it can serve from cache.
- Implementation detail: use a local SQLite database for persistence across restarts.
  - Store small JSON/text payloads (not audio blobs).

### Plugin contract (standard pattern)

Each plugin that opts into caching follows the same steps:

1) Derive a cache key from the request context
2) Ask the shared cache for an entry
3) Decide:
   - serve cached immediately (fast path)
   - or fetch live (slow path)
4) If cached was served and entry is expired, kick a refresh in the background

Caching should not be implemented ad-hoc in every plugin; plugins should use a shared cache API.

### Cache items (initial scope)

- Weather for configured `location`
- Crypto prices (e.g., BTC, ETH)
- A short "good morning/evening" greeting template (local, no API)

Note: greeting templates do not require network calls; cache is optional.

### Refresh strategy

- On-demand refresh (always): when a cache entry is missing or expired, fetch live.
- Kick refresh (important for perceived speed): if a cached value is served but is expired, schedule a refresh in background.
- Optional periodic refresh (configurable): a background scheduler keeps certain keys warm.

Each cache entry stores:
- `value` (string or JSON)
- `created_at` / `updated_at`
- `ttl_s` (time-to-live; after this, refresh should happen)
- `max_stale_s` (hard limit; after this, do not serve cached)

### Response behavior (voice-first)

- If cached entry exists and is within `max_stale_s`: return it immediately.
- If it is expired (older than `ttl_s`): schedule a background refresh (do not block the answer).
- If it is older than `max_stale_s`: do not serve cached; fetch live and update cache.

We intentionally do not add "freshness wording" to spoken responses. Correctness comes from conservative TTL and max-stale defaults.

### Safety / cost controls

- Hard cap on number of cached items.
- Configurable refresh interval.
- Disabled by default.

### Concurrency and latency notes

We want voice answers to remain instant.

- The read path must be fast (in-memory lookup and/or a quick SQLite read).
- Background refresh should never speak.
- To keep SQLite reliable, cache writes should be serialized (e.g., a cache worker that owns the write connection).
  - This does not block voice playback because the user-facing response can be returned before the write completes.

---

## Configuration

```yaml
background_cache: enabled
background_cache_refresh_s: 300

background_cache_weather: enabled
background_cache_crypto:
  - BTC
  - ETH

# Mandatory per-plugin staleness bounds (example defaults)
cache_weather_ttl_s: 600
cache_weather_max_stale_s: 1800

cache_crypto_ttl_s: 120
cache_crypto_max_stale_s: 600
```

Defaults:
- `background_cache: disabled`

---

## Acceptance Criteria

- [ ] When enabled, weather/crypto requests can be answered instantly from cache
- [ ] Plugins define and enforce `ttl_s` and `max_stale_s` (do not serve very old data)
- [ ] No background refresh results in unsolicited speech
- [ ] Barge-in can interrupt playback as usual
- [ ] Cache background thread stops cleanly on shutdown

---

## Testing

- Unit test: cache returns fresh value and includes timestamp/freshness metadata
- Unit test: stale value triggers background refresh
- Unit test: cache thread starts only when enabled

---

## Implementation Sketch (No Code)

### Data model

SQLite table (example):
- `key` (primary key)
- `value_json`
- `updated_at`
- `ttl_s`
- `max_stale_s`

### Cache API (conceptual)

- `get(key) -> entry|None`
- `set(key, value, ttl_s, max_stale_s)`
- `should_refresh(entry) -> bool` (age > ttl)
- `can_serve(entry) -> bool` (age <= max_stale)
- `kick_refresh(key, refresh_fn)` (enqueues work; at-most-one in-flight per key)

### Plugin integration

- Plugins compute keys consistently:
  - weather: include `location` and `unit`
  - crypto: include symbol and quote currency
- Plugins are responsible for choosing TTL/max-stale defaults appropriate to the domain.
