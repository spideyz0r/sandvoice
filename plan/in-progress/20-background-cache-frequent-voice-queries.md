# Background Cache for Frequent Voice Queries

**Status**: 🚧 In Progress
**Priority**: 20
**Platforms**: macOS M1, Raspberry Pi 3B

---

## What is already done

- `common/cache.py` — `VoiceCache`: SQLite WAL, `CacheEntry(key, value, updated_at, ttl_s, max_stale_s)`, `is_fresh()`, `can_serve()`, `set_with_timestamp()` for test seeding, `last_hit_type` diagnostic
- `plugins/weather/plugin.py` — fully integrated: cache key `weather:<JSON([loc,unit])>`, caches full LLM response text, `refresh_only=True` support, legacy entry detection
- Scheduler `action_type: plugin` with `refresh_only: true` in `tasks.yaml` already works end-to-end
- `sandvoice.py` exposes `self.cache` on the `SandVoice` instance; plugins access via `getattr(s, 'cache', None)`

---

## What remains

1. **Cache `hacker_news` and `news` plugins** — same pattern as weather
2. **`cache_auto_refresh` system** — startup warmup + auto-registered interval tasks, driven by a single config list

---

## Scope

**In scope:**
- `hacker_news` and `news` cache integration
- `cache_auto_refresh` config key (startup warmup + periodic silent refresh)
- README documentation

**Out of scope:**
- `realtime` / `realtime_websearch` — real-time by design; caching defeats the purpose
- Crypto prices — not implemented, not planned
- Greeting cache — not needed

---

## Cache integration: hacker_news and news

Same three-step pattern as weather: try cache → fall through to live fetch + LLM → cache response text.

**Cache keys:**
- `hacker-news:top` — fixed; always top 5 stories
- `news:<rss_url>` — URL is the discriminator; handles multiple configured feeds cleanly

**`refresh_only` support:** when `route.get('refresh_only')` is True, run the fetch + LLM, update cache, return `None`. No TTS. No audio.

**TTL values:** plugins read `ttl_s` and `max_stale_s` from `route` (injected by the `cache_auto_refresh` system at invocation time). Fall back to plugin-defined defaults if not present.

---

## `cache_auto_refresh` design (Option B2)

A single list in `~/.sandvoice/config.yaml` drives both startup warmup and periodic background refresh. No separate file. No manual `tasks.yaml` entries for cache.

```yaml
cache_enabled: enabled

cache_auto_refresh:
  - plugin: hacker-news
    query: "hacker news"
    interval_s: 28800        # refresh every 8 hours
    ttl_s: 28800
    max_stale_s: 43200
  - plugin: news
    query: "latest news"
    interval_s: 7200         # refresh every 2 hours
    ttl_s: 7200
    max_stale_s: 14400
  - plugin: weather
    query: "weather"
    interval_s: 10800        # refresh every 3 hours
    ttl_s: 10800
    max_stale_s: 21600
```

### What happens on startup

For each entry in `cache_auto_refresh`:
1. Invoke the plugin immediately in a background thread with `refresh_only=True` and the entry's `ttl_s`/`max_stale_s` injected into the route
2. Auto-register an interval scheduler task named `cache_refresh:<plugin>` with `schedule_value=interval_s`

All background refreshes are **silent by design** — `refresh_only=True` causes the plugin to return `None`, and the scheduler's `_scheduler_invoke_plugin` skips TTS when `refresh_only` is set.

### Interaction with existing weather config keys

`cache_weather_ttl_s` and `cache_weather_max_stale_s` remain valid. If `weather` is in `cache_auto_refresh`, the entry's inline `ttl_s`/`max_stale_s` take precedence; the named config keys become the fallback for direct plugin calls that don't go through `cache_auto_refresh`.

### Auto-registered task naming and deduplication

Tasks are named `cache_refresh:<plugin>` (e.g. `cache_refresh:hacker-news`). The scheduler's `sync_tasks` dedup logic (skip active/paused tasks by name) ensures that restarting SandVoice doesn't duplicate tasks.

### Config validation

- `cache_auto_refresh` requires `cache_enabled: enabled` — warn and skip if cache is disabled
- `interval_s` must be a positive integer
- `plugin` must match a loaded plugin name (warn and skip unknown plugins)
- `ttl_s` defaults to `interval_s` if omitted; `max_stale_s` defaults to `interval_s * 1.5` if omitted

---

## Files to touch

| File | Change |
|---|---|
| `plugins/hacker_news/plugin.py` | Add cache read/write + `refresh_only` support |
| `plugins/news/plugin.py` | Add cache read/write + `refresh_only` support |
| `common/configuration.py` | Parse `cache_auto_refresh` list; validation |
| `sandvoice.py` | `_warmup_cache()`: read `cache_auto_refresh`, fire background threads, auto-register scheduler tasks |
| `tests/test_hacker_news.py` | Cache hit/miss/refresh_only coverage |
| `tests/test_news.py` | Cache hit/miss/refresh_only coverage |
| `tests/test_sandvoice.py` | Warmup and auto-task registration |
| `README.md` | Document `cache_auto_refresh` in Background Cache section |

---

## README additions (shape)

Extend the existing Background Cache section:

```
### Auto-refresh

Add `cache_auto_refresh` to config to warm a plugin's cache on startup and refresh
it silently in the background:

cache_enabled: enabled
cache_auto_refresh:
  - plugin: hacker-news
    query: "hacker news"
    interval_s: 28800
  - plugin: news
    query: "latest news"
    interval_s: 7200

On startup SandVoice fetches each plugin immediately (no audio played).
A background task then refreshes it every `interval_s` seconds — also silent.
`ttl_s` and `max_stale_s` control freshness; both default to `interval_s` and
`interval_s * 1.5` respectively if omitted.
```

---

## Acceptance criteria

- [ ] `hacker_news` plugin serves from cache on hit, falls through on miss, returns `None` on `refresh_only`
- [ ] `news` plugin same as above
- [ ] On startup with `cache_auto_refresh` configured, each listed plugin is invoked silently in a background thread
- [ ] A scheduler task named `cache_refresh:<plugin>` is auto-registered for each entry
- [ ] No audio plays during any background refresh
- [ ] Cache miss on first run triggers live fetch; subsequent requests within TTL are instant
- [ ] `cache_auto_refresh` with `cache_enabled: disabled` logs a warning and skips
- [ ] Unknown plugin name in `cache_auto_refresh` logs a warning and skips that entry
- [ ] >80% test coverage on new code
