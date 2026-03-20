# Wake Word Route Always Required

**Status**: ✅ Completed
**Priority**: 31
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Remove the dead-code `else` branch in `_state_processing` that handles a `None` `route_message` callback. `sandvoice.py` always provides `route_message`; the `None` path has never been reachable in production. Removing it simplifies `_state_processing` by ~30 lines.

---

## Problem Statement

In `_state_processing`, response generation is guarded by:

```python
if self.route_message is not None:
    route = self._poll_op(lambda: self.ai.define_route(user_input), ...)
    # ... plugin routing, streaming, pre-generated TTS ...
else:
    # Fallback: no routing, just generate a response directly
    response = self._poll_op(lambda: self.ai.generate_response(user_input), ...)
    # ... ~20 lines of fallback handling ...
```

`self.route_message` is set in `__init__` from the `route_message` parameter. `sandvoice.py` always passes this callback. The `else` branch exists only as a theoretical fallback that no caller uses.

Dead code that looks like a real code path is a maintenance hazard — it must be kept in sync and tested, and it creates the false impression that wake-word mode can work without routing.

---

## Proposed Solution

1. **Fail-fast in `__init__`**: if `route_message` is `None`, raise `ValueError("route_message is required")`.
2. **Remove the `if self.route_message is not None:` / `else:` wrapper** in `_state_processing` — make the routing block unconditional.
3. **Remove the `else` fallback block** (~20 lines of direct `generate_response` call, response handling, and barge-in checks).

Estimated net reduction: **~30 lines**.

### Change to `__init__`

```python
def __init__(self, config, ai_instance, audio_instance, route_message, plugins=None, audio_lock=None):
    if route_message is None:
        raise ValueError("route_message is required for wake-word mode")
    self.route_message = route_message
    ...
```

---

## Files to Touch

| File | Change |
|---|---|
| `common/wake_word.py` | Remove `if self.route_message is not None:` wrapper in `_state_processing`; add guard in `__init__` |
| `tests/test_wake_word.py` | Remove tests for the `None` route_message path; add test for `ValueError` on `None` |

---

## Out of Scope

- No changes to `sandvoice.py` — it already passes `route_message` correctly
- No config changes
- No audio or AI layer changes

---

## Acceptance Criteria

- [x] `__init__` raises `ValueError` if `route_message` is `None`
- [x] `if self.route_message is not None:` / `else:` removed from `_state_processing`
- [x] `else` fallback block deleted
- [x] All tests pass; >80% coverage on changed code
- [x] `wake_word.py` reduced by ~30 lines
