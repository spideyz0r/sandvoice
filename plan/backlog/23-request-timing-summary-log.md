# Request Timing Summary Log

**Status**: 📋 Backlog
**Priority**: 23
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- **Plan 28 (Logging Level Refactor)** — INFO level must be visible before this plan is useful. Merge Plan 28 first.

---

## Overview

Emit a single `logger.info()` line at the end of each request cycle summarising all timing, routing, and cache information. This enables clean benchmarking and performance regression detection without grepping through verbose debug output.

---

## Problem Statement

Currently all timing information is scattered across HTTP debug headers (`openai-processing-ms`) and individual DEBUG-level log lines. To benchmark a request you must enable debug mode (`debug: enabled` today, `log_level: debug` after Plan 28), which floods the terminal with noise. Then manually correlate timestamps and calculate deltas by hand.

There is no clean, always-visible summary of what happened in a request.

---

## Proposed Solution

Emit one `INFO` line at the end of every request cycle:

```
INFO: [request] transcribe=2.41s route=1.83s(gpt-4.1-nano→weather) plugin=0.05s(cache:hit-fresh) tts=1.92s total=6.21s
```

### Fields

| Field | Description |
|---|---|
| `transcribe=Xs` | Wall-clock time for STT call |
| `route=Xs(model→plugin)` | Routing LLM time + model name + selected route |
| `plugin=Xs(cache:STATUS)` | Plugin execution time + cache status (`hit-fresh`, `hit-stale`, `miss`, `none`) |
| `tts=Xs` | TTS generation time (wall-clock to first byte received) |
| `total=Xs` | Wake word detected → audio playback start |

---

## Implementation Notes

### Timing instrumentation
- Use `time.monotonic()` at each phase boundary in `common/wake_word.py`
- Pass a lightweight `_RequestTiming` dict/dataclass through the call chain
- Emit the summary line just before transitioning to RESPONDING state

### Cache status surfacing
The weather plugin already logs cache status at DEBUG level. To include it in the summary without changing plugin signatures, store the last cache hit type on the cache instance per-request:

```python
# In common/cache.py — add attribute updated on each get()
self.last_hit_type: str | None = None  # "fresh", "stale", "miss"

# In plugins/weather.py — already sets this implicitly via cache.get()
```

The summary line reads `s.cache.last_hit_type` after plugin execution.

### Route info
`AI.define_route()` already returns the full route dict including `route` name. Pass the model name alongside it (readable from `s.config.gpt_route_model`).

---

## Files to Touch

| File | Change |
|---|---|
| `common/wake_word.py` | Main instrumentation: `time.monotonic()` at each phase, emit summary INFO line |
| `common/cache.py` | Add `last_hit_type` attribute, set on each `get()` call |
| `plugins/weather.py` | No change needed (cache status flows via `s.cache.last_hit_type`) |
| `tests/test_wake_word.py` | Assert summary line is emitted; check timing fields present |
| `tests/test_cache.py` | Assert `last_hit_type` is set correctly on hit/miss |

---

## Out of Scope

- No new config keys
- No change to plugin signatures
- CLI mode timing (nice-to-have, follow-up)
- MP3 cache timing (`tts=0s(cached)`) — handle when MP3 caching is implemented

---

## Acceptance Criteria

- [ ] Single `INFO` line emitted after every wake-word request
- [ ] Line includes: transcribe time, route time + model + plugin name, plugin time + cache status, TTS time, total time
- [ ] Visible at `log_level: info` (requires Plan 28)
- [ ] Tests cover summary line emission and `last_hit_type` correctness
- [ ] >80% coverage on new code
