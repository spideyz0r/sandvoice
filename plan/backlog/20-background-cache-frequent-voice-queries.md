# Voice UX: Background Cache for Frequent Queries

**Status**: 📋 Backlog
**Priority**: 20
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

For a few common voice queries (weather, a handful of tickers/crypto, time-sensitive greetings), the user cares most about instant feedback.

This plan adds an opt-in background cache that periodically refreshes a small set of common answers so SandVoice can respond immediately with real content (and optionally refresh in the background).

---

## Problem Statement

Current behavior:
- Every request waits for network/API calls.

Desired behavior:
- For selected query types, respond instantly from a recent cached value with a freshness hint ("As of 2 minutes ago...").

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

---

## Proposed Design

### Cache items (initial scope)

- Weather for configured `location`
- Crypto prices (e.g., BTC, ETH)
- A short "good morning/evening" greeting template (local, no API)

### Refresh strategy

- Background thread refreshes each enabled item on a fixed interval.
- Each cache entry includes `value`, `fetched_at`, and `ttl_seconds`.

### Response behavior

- If cache entry is fresh: speak cached answer immediately.
- If stale but available: speak cached answer with a staleness warning and refresh in background.
- If missing: fall back to normal live fetch.

### Safety / cost controls

- Hard cap on number of cached items.
- Configurable refresh interval.
- Disabled by default.

---

## Configuration

```yaml
background_cache: enabled
background_cache_refresh_s: 300

background_cache_weather: enabled
background_cache_crypto:
  - BTC
  - ETH
```

Defaults:
- `background_cache: disabled`

---

## Acceptance Criteria

- [ ] When enabled, weather/crypto requests can be answered instantly from cache
- [ ] Spoken response includes freshness hint when using cached values
- [ ] No background refresh results in unsolicited speech
- [ ] Barge-in can interrupt playback as usual
- [ ] Cache background thread stops cleanly on shutdown

---

## Testing

- Unit test: cache returns fresh value and includes timestamp/freshness metadata
- Unit test: stale value triggers background refresh
- Unit test: cache thread starts only when enabled
