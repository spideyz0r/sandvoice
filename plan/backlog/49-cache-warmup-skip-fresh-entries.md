# Plan 49: Cache Warmup — Skip Fresh Entries on Restart

## Problem

On every SandVoice startup the `cache_auto_refresh` warmup unconditionally
makes live API calls (weather API + LLM) for every configured plugin, even
when the cached entry stored in SQLite is still fully fresh from the previous
run.

**Root cause**: in `plugins/weather/plugin.py` (and any other cache-aware
plugin), the cache read is guarded by `if not refresh_only`. When the warmup
calls a plugin with `refresh_only=True`, the code deliberately skips the cache
check and goes straight to the live fetch. This was correct when `refresh_only`
was introduced (its purpose is to update the cache), but it means the cache is
never *consulted* at warmup time — so a restart 2 minutes after the last run
still burns an API call.

```python
# Current behaviour — cache completely ignored during warmup
if not refresh_only and cache is not None:
    entry = cache.get(cache_key)
    ...
# Falls through to live fetch unconditionally when refresh_only=True
```

## Goal

Make warmup intelligent: if the cached entry is still **fresh** (`is_fresh()`),
skip the live fetch entirely and return early. Only perform the live fetch when
the entry is missing, expired beyond TTL (stale), or cannot be served at all.

This eliminates unnecessary API calls on restart and makes warmup nearly instant
when the cache is warm from a recent run.

## Intended Behaviour After Fix

| Cache state at warmup | Action |
|---|---|
| Entry fresh (`age ≤ ttl_s`) | Skip fetch, log debug, return immediately |
| Entry stale but servable (`ttl_s < age ≤ max_stale_s`) | Fetch live, update cache |
| Entry missing or expired (`age > max_stale_s`) | Fetch live, update cache |

The user-facing request path (`refresh_only=False`) is unchanged.

## Implementation

### `plugins/weather/plugin.py`

Add a fresh-entry early return inside the `refresh_only` branch:

```python
if refresh_only and cache is not None:
    try:
        entry = cache.get(cache_key)
        if entry is not None and cache.is_fresh(entry) and not _is_legacy_cache_entry(entry.value):
            logger.debug("Weather cache warmup skip (fresh): key=%r", cache_key)
            return None  # warmup callers ignore return values
    except Exception as e:
        logger.debug("Weather cache check failed during warmup, proceeding with fetch: %s", e)

if not refresh_only and cache is not None:
    # existing user-facing cache read ...
```

### Other cache-aware plugins

Apply the same pattern to any other plugin that checks `refresh_only` and uses
`VoiceCache`. At time of writing, only `weather` is affected, but the pattern
should be documented in `docs/PATTERNS.md` for future plugins.

### `docs/PATTERNS.md`

Add a section: **Cache-aware plugin warmup pattern** — describes the two-phase
cache check (skip-if-fresh for warmup, serve-if-can-serve for user requests).

## Acceptance Criteria

- [ ] Restarting SandVoice within the weather TTL window (default 3 h) produces
      zero weather API or LLM calls during warmup
- [ ] Restarting after the TTL has expired still triggers a live fetch
- [ ] User-facing weather queries are unaffected
- [ ] `cache_auto_refresh` warmup completes immediately when all entries are fresh
- [ ] Tests cover: warmup skip when fresh, warmup fetch when stale, warmup fetch
      when missing
- [ ] Pattern documented in `docs/PATTERNS.md`

## Notes

- The greeting plugin uses the same `refresh_only` flag; check whether it has
  the same issue and apply the fix there too.
- The `VoiceFillerCache` is a separate system (audio files + hash DB) and is
  already skip-on-hit — no changes needed there.
- No config changes required.
