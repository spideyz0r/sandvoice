# Plan 59: Drop Python < 3.9 zoneinfo Fallback

## Status
📋 Backlog

## Problem
`plugins/weather/plugin.py` and `plugins/greeting/plugin.py` both guard the `zoneinfo` import with a try/except:

```python
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # Python < 3.9 fallback
```

`zoneinfo` has been in the standard library since Python 3.9 (released October 2020). Both target platforms already exceed this:

- **macOS M1** — ships Python 3.9+; current dev machine runs 3.14
- **Raspberry Pi OS Bullseye** (released 2021) and later — ships Python 3.9+

The fallback is dead code. Worse, it silently degrades: if somehow triggered, `ZoneInfo = None` causes `_resolve_tz()` to return `None` for every timezone, breaking cache key rotation without any hard error.

## Goal
Remove the fallback entirely in both plugins so the dependency is explicit and failures are loud.

## Approach

### `plugins/weather/plugin.py`
Replace:
```python
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # Python < 3.9 fallback
```
With:
```python
from zoneinfo import ZoneInfo
```

Update `_resolve_tz()` — remove the `ZoneInfo is None` guard since it can no longer be `None`:
```python
def _resolve_tz(tz_name):
    """Return a ZoneInfo for tz_name, or None if unavailable or invalid."""
    if not isinstance(tz_name, str) or not tz_name.strip():
        return None
    tz_name = tz_name.strip()
    if tz_name in _TZ_CACHE:
        return _TZ_CACHE[tz_name]
    try:
        tz = ZoneInfo(tz_name)
        _TZ_CACHE[tz_name] = tz
        return tz
    except Exception as exc:
        logger.warning(
            "Weather: timezone %r could not be resolved (%s); falling back to UTC for cache key.",
            tz_name,
            exc,
        )
        _TZ_CACHE[tz_name] = None
        return None
```

### `plugins/greeting/plugin.py`
Same change: replace the try/except with a direct import. Remove the `ZoneInfo is None` guard in `_resolve_tz()`.

### Tests
- Update any test that patches `ZoneInfo = None` or checks the `ZoneInfo is None` branch.
- Confirm all existing weather and greeting tests still pass.

## Acceptance Criteria
- [ ] `from zoneinfo import ZoneInfo` is a direct import in both plugins (no try/except)
- [ ] `_resolve_tz()` in both plugins no longer checks `ZoneInfo is None`
- [ ] All existing tests pass
- [ ] No new `ZoneInfo is None` code paths introduced elsewhere
