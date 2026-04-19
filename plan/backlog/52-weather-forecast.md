# Plan 52: Weather Forecast — 7-Day / Future Date Queries

## Status
📋 Backlog

## Problem
The weather plugin (`plugins/weather/plugin.py`) only queries the OpenWeatherMap **current weather** endpoint (`/data/2.5/weather`). When a user asks "what will the weather be like on Thursday?" or "will it rain this weekend?", the plugin returns today's conditions — which is misleading.

## Goal
Extend the weather plugin to route future-date questions to the OpenWeatherMap **5-day / 3-hour forecast** endpoint (`/data/2.5/forecast`), so users can ask about weather up to 7 days ahead and get accurate answers.

## Approach

### Routing changes (`routes.yaml`)
Add a `days_ahead` parameter to the weather route so the AI can signal that a future date was requested:

```yaml
- name: weather
  description: "Answer questions about current or future weather conditions"
  parameters:
    location: string (optional, defaults to configured location)
    unit: string (optional, defaults to configured unit)
    days_ahead: integer (optional, 0 = today/current, 1–7 = forecast N days from now)
```

The AI sets `days_ahead` to `0` (or omits it) for present-tense queries, and to a positive integer for future queries.

### Plugin logic (`plugins/weather/plugin.py`)
1. Read `route.get('days_ahead', 0)` after existing location/unit defaults.
2. If `days_ahead == 0`: use existing `OpenWeatherReader.get_current_weather()` path unchanged.
3. If `days_ahead >= 1`: call a new `OpenWeatherReader.get_forecast(days_ahead)` method:
   - Hits `/data/2.5/forecast?q=<location>&appid=<key>&units=<unit>&cnt=<slots>` where `cnt = min(days_ahead * 8, 40)` (8 three-hour slots per day, API max 40).
   - Filters the returned `list` to entries whose `dt_txt` date matches `today + days_ahead`.
   - Returns the filtered list (or the full list if filtering produces nothing — graceful fallback).
4. Cache key includes `days_ahead` to avoid collisions between current and forecast entries: `weather:<JSON([loc,unit,days_ahead])>`.
5. TTL for forecast entries is shorter (configurable, default 1 h) because forecasts change faster than current-conditions summaries.
6. The LLM prompt for forecast queries asks the model to summarise the day's expected conditions rather than giving a point-in-time reading.

### New config keys (`config.yaml` / `configuration.py`)
| Key | Default | Description |
|-----|---------|-------------|
| `cache_weather_forecast_ttl_s` | `3600` (1 h) | TTL for forecast cache entries |
| `cache_weather_forecast_max_stale_s` | `7200` (2 h) | Max-stale window for forecast cache entries |

Both follow the existing 4-step config pattern (defaults dict → `load_config()` assignment → validation → documented in `config.yaml`).

### Cache key helper
Update `_cache_key(location, unit, days_ahead=0)` to encode all three values:
```python
def _cache_key(location, unit, days_ahead=0):
    encoded = json.dumps([location, unit, days_ahead], separators=(",", ":"))
    return f"weather:{encoded}"
```
Legacy entries (encoded without `days_ahead`) are automatically separate — no migration needed.

## Acceptance Criteria
- [ ] "What's the weather today?" routes to current endpoint (unchanged behavior)
- [ ] "What will the weather be like tomorrow?" returns next-day forecast data
- [ ] "Will it rain on Saturday?" returns forecast for the correct day (up to 7 days out)
- [ ] Forecast responses are cached separately from current-weather responses
- [ ] Cache TTL/max-stale for forecast entries is independently configurable
- [ ] Graceful degradation: if `days_ahead > 5` (API limit) or forecast fetch fails, return a friendly message
- [ ] All new code paths covered by unit tests (>80% coverage)
- [ ] No regression in existing current-weather tests

## Testing Strategy
- Unit-test `get_forecast()` with mocked `requests.get` returning a realistic 40-slot forecast payload.
- Unit-test `_cache_key()` with `days_ahead` variants to confirm key separation.
- Unit-test the `days_ahead >= 1` branch in `process()` end-to-end with mocked `OpenWeatherReader`.
- Verify that `days_ahead=0` still exercises the original code path (no regression).

## Out of Scope
- Hourly forecasts (user asks "what time will the rain start?") — separate plan if needed.
- Weather alerts / severe weather warnings.
- Caching warm-up for forecast entries (scheduler would need a per-day-ahead variant).

## Dependencies
- Existing `VoiceCache` infrastructure (Plan 20) — already in production.
- OpenWeatherMap free tier includes the 5-day/3-hour forecast endpoint.
