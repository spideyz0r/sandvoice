# Plan 40: Greeting Plugin Cache

**Status**: 🚧 In Progress
**Priority**: 40
**Platforms**: macOS M1, Raspberry Pi 3B
**Depends on**: Plan 22 (plugin manifest system), Plan 20 (background cache)

---

## Problem

The greeting plugin (`plugins/greeting.py`) calls the weather plugin internally and
then calls the LLM to generate the final greeting text — taking ~8–10 seconds even
when the weather data is already cached. Every "bom dia" / "boa tarde" / "boa noite"
triggers a fresh LLM call.

Additionally, `greeting.py` is a legacy flat file while all cache-capable plugins
have been migrated to the folder + `plugin.yaml` manifest format (Plan 22).

---

## Goal

- Migrate `plugins/greeting.py` → `plugins/greeting/plugin.py` + `plugin.yaml`
- Cache the generated greeting text keyed by time-of-day bucket
- Wire into `cache_auto_refresh` so the cache is warm at startup

After this plan, saying "bom dia" returns an instant cached response on the second
request within the same time bucket.

---

## Cache Key

```python
def _cache_key(config=None):
    tz = _resolve_tz(config)  # uses config.timezone via ZoneInfo; falls back to local time
    hour = datetime.now(tz).hour
    if 5 <= hour < 12:
        bucket = "morning"
    elif 12 <= hour < 18:
        bucket = "afternoon"
    elif 18 <= hour < 22:
        bucket = "evening"
    else:
        bucket = "night"
    return f"greeting:{bucket}"
```

All greetings within the same time bucket share one cache entry.

---

## Behaviour

- **Cache hit (fresh or stale-but-acceptable)**: if the cached entry is within `max_stale_s`, return stored text immediately — no LLM call
- **Cache miss / too stale to serve**: run full pipeline (weather lookup + greeting LLM), store result
- **`refresh_only=True`**: run full pipeline, store result, return `None` (no TTS)

The weather comment inside the greeting may be up to `max_stale_s` seconds stale — accepted
trade-off for instant response.

---

## Configuration

Add to `~/.sandvoice/config.yaml`:

```yaml
cache_auto_refresh:
  - plugin: greeting
    query: "bom dia"
    interval_s: 3600      # regenerate every hour (time bucket changes)
    ttl_s: 3600
    max_stale_s: 5400
```

---

## Implementation

### `plugins/greeting/plugin.yaml`

```yaml
name: greeting
version: 1.0.0
route_description: "The user is greeting the bot. For example: 'Hello', 'Hi', 'Good morning', 'Bom dia', 'Boa tarde', 'Boa noite'."
```

### `plugins/greeting/plugin.py`

- Move existing logic from `plugins/greeting.py`
- Add `_cache_key(config=None)` using time-of-day bucket (timezone-aware via `config.timezone`)
- Wrap `process()` with cache read (hit → return) / write (miss → store)
- Add `refresh_only` support: skip return if `route.get('refresh_only')`
- Remove `greeting` entry from `routes.yaml` (manifest self-registers it)

---

## Tests

- `test_greeting_cache_hit` — cache has fresh entry; plugin returns it without calling LLM
- `test_greeting_cache_miss` — no cache entry; plugin calls LLM and stores result
- `test_greeting_refresh_only` — `refresh_only=True`; result stored, `None` returned
- `test_greeting_cache_key_buckets` — verify each hour maps to the correct bucket
- `test_greeting_plugin_loaded_from_folder` — folder-based plugin loads correctly

---

## Files

| File | Change |
|---|---|
| `plugins/greeting.py` | Delete |
| `plugins/greeting/plugin.yaml` | New — manifest |
| `plugins/greeting/plugin.py` | New — migrated + cache logic |
| `routes.yaml` | Remove `greeting:` entry (now in manifest) |
| `tests/test_greeting_plugin.py` | New — cache tests |

---

## Acceptance Criteria

- [ ] `greeting.py` deleted; `plugins/greeting/` folder loads correctly
- [ ] Cache hit returns instantly without LLM call
- [ ] Cache miss runs full pipeline and stores result
- [ ] `refresh_only=True` stores and returns `None`
- [ ] `_cache_key()` returns correct bucket for all 24 hours
- [ ] `cache_auto_refresh` entry warms the greeting cache at startup
- [ ] `routes.yaml` `greeting` entry removed (manifest owns it)
- [ ] >80% test coverage on new code
