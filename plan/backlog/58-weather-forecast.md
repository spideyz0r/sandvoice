# Plan 58: Weather Forecast — 5-Day / Future Date Queries

## Status
📋 Backlog

## Problem
The weather plugin (`plugins/weather/plugin.py`) only queries the OpenWeatherMap **current weather** endpoint (`/data/2.5/weather`). When a user asks "what will the weather be like on Thursday?" or "will it rain this weekend?", the plugin returns today's conditions — which is misleading.

## Goal
Extend the weather plugin to route future-date questions to the OpenWeatherMap **5-day / 3-hour forecast** endpoint (`/data/2.5/forecast`), so users can ask about weather up to 5 days ahead and get accurate answers.

## Approach

### Routing changes (`plugins/weather/plugin.yaml`)
The weather plugin's routing metadata lives in `plugins/weather/plugin.yaml`, not `routes.yaml`. Update it to support `days_ahead`:

- Add `days_ahead` to `route_extra_keys` so the router includes it in the JSON output.
- Update `route_description` to cover both current and future weather questions, instructing the model to:
  - Omit `days_ahead` (or set it to `0`) for present-tense queries.
  - Set `days_ahead` to an integer from `1` to `5` for future-date queries.
  - Values above `5` are outside the API range — the plugin returns a graceful degradation message.

The AI sets `days_ahead` to `0` (or omits it) for present-tense queries, and to a positive integer for future queries. Values above 5 are outside the API's range and will receive a graceful degradation message (see Acceptance Criteria).

### Plugin logic (`plugins/weather/plugin.py`)
1. Read `route.get('days_ahead', 0)` after existing location/unit defaults.
2. If `days_ahead == 0`: use existing `OpenWeatherReader.get_current_weather()` path unchanged.
3. If `1 <= days_ahead <= 5`: call a new `OpenWeatherReader.get_forecast(days_ahead)` method:
   - Hits `/data/2.5/forecast?q=<location>&appid=<key>&units=<unit>&cnt=40` — always fetch all 40 slots (the API maximum). Using `cnt = days_ahead * 8` risks missing the target date when the request is made late in the day, since `cnt` counts slots from "now" rather than calendar days. Fetching 40 slots ensures the target date is always covered.
   - Filters the returned `list` to entries whose forecast date matches `today + days_ahead` in the location's timezone. Use the `city.timezone` offset from the payload (seconds east of UTC) to derive both the target date and to interpret each slot's `dt` field, avoiding off-by-one-day errors around midnight.
   - Returns the filtered list (or the full list if timezone-based filtering produces nothing — graceful fallback).
4. If `days_ahead > 5`: return a friendly message without calling the API (e.g. "I can only forecast up to 5 days ahead.").
5. Cache key includes `days_ahead` to avoid collisions between current and forecast entries: `weather:<JSON([loc,unit,days_ahead])>`.
6. TTL for forecast entries is shorter (configurable, default 1 h) because forecasts change faster than current-conditions summaries.
7. The LLM prompt for forecast queries asks the model to summarize the day's expected conditions rather than giving a point-in-time reading.

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
- [ ] "Will it rain on Saturday?" returns forecast for the correct day (up to 5 days out)
- [ ] Forecast responses are cached separately from current-weather responses
- [ ] Cache TTL/max-stale for forecast entries is independently configurable
- [ ] Graceful degradation: if `days_ahead > 5` (beyond API limit), return a friendly message without calling the API
- [ ] Graceful degradation: if forecast fetch fails for any reason, return a friendly error message
- [ ] All new code paths covered by unit tests (>80% coverage)
- [ ] No regression in existing current-weather tests

## Testing Strategy
- Unit-test `get_forecast()` with mocked `requests.get` returning a realistic 40-slot forecast payload.
- Unit-test `_cache_key()` with `days_ahead` variants to confirm key separation.
- Unit-test the `days_ahead >= 1` branch in `process()` end-to-end with mocked `OpenWeatherReader`.
- Unit-test timezone-aware date filtering with a payload whose `city.timezone` offset places the target date differently than UTC.
- Unit-test `days_ahead > 5` returns the friendly degradation message without making an API call.
- Verify that `days_ahead=0` still exercises the original code path (no regression).

## Out of Scope
- Hourly forecasts (user asks "what time will the rain start?") — separate plan if needed.
- Weather alerts / severe weather warnings.
- Caching warm-up for forecast entries (scheduler would need a per-day-ahead variant).
- Forecasts beyond 5 days (would require a different API tier or provider).

## Dependencies
- Existing `VoiceCache` infrastructure (Plan 20) — already in production.
- OpenWeatherMap free tier includes the 5-day/3-hour forecast endpoint.
