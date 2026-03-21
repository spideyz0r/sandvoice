# Wake Word Barge-In Detector Extraction

**Status**: 📋 Backlog
**Priority**: 33
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- **Plan 32** — should be completed first to reduce noise before the structural split.

---

## Overview

Extract the barge-in detection subsystem from `common/wake_word.py` into a dedicated
`common/barge_in.py` module with a `BargeInDetector` class. The class has a clean,
minimal interface (start / stop / is_triggered) and encapsulates ~230 lines of Porcupine
thread management that has nothing to do with the state machine itself.

Estimated net reduction in `wake_word.py`: **~200 lines**.

---

## Problem Statement

Five methods in `WakeWordMode` are exclusively concerned with barge-in detection and
have no dependency on state machine state:

| Method | Lines | Responsibility |
|---|---|---|
| `_listen_for_barge_in()` | ~66 | The actual detection thread body |
| `_start_barge_in_detection()` | ~29 | Creates Porcupine instance + starts thread |
| `_check_barge_in_interrupt()` | ~13 | Polls barge-in event (used by `_poll_op`) |
| `_run_with_barge_in_polling()` | ~69 | Wraps any operation with 50ms poll loop |
| `_handle_immediate_barge_in()` | ~55 | Stops detection, plays beep, cleans up |

These only touch `self.porcupine` (the main instance) for access-key reuse, and
`self.barge_in_thread / barge_in_event / barge_in_stop_flag` which are purely internal.

---

## Proposed Solution

### New file: `common/barge_in.py`

```python
class BargeInDetector:
    def __init__(self, access_key, keyword_paths, sensitivity, audio_lock, audio, config):
        ...

    def start(self):
        """Start background detection thread. No-op if already running."""

    def stop(self, timeout=0.3):
        """Signal thread to stop and join it. Clears internal state."""

    @property
    def is_triggered(self):
        """True if the barge-in wake word has been detected."""

    def clear(self):
        """Reset the triggered flag (rearm for next use)."""

    def run_with_polling(self, operation, name):
        """
        Run operation() in a background thread, polling for barge-in every 50ms.
        Returns the operation result, or _BARGE_IN sentinel if interrupted.
        """
```

The `_BARGE_IN` sentinel moves to `common/barge_in.py` (or a shared `common/sentinels.py`).

### Changes to `WakeWordMode`

- Remove the five barge-in methods listed above.
- Add `self.barge_in = BargeInDetector(...)` in `__init__`.
- Replace all call sites:
  - `self._start_barge_in_detection()` → `self.barge_in.start()`
  - `self._handle_immediate_barge_in(thread)` → `self.barge_in.stop(); self._play_confirmation_beep()` (beep stays in wake_word.py)
  - `self._poll_op(op, name)` → `self.barge_in.run_with_polling(op, name)`
  - `self.barge_in_event.is_set()` checks → `self.barge_in.is_triggered`

`_poll_op` is a thin wrapper on `barge_in.run_with_polling` — it can be kept in
`wake_word.py` if the `_BARGE_IN` sentinel needs to stay local, or removed entirely.

---

## Files to Touch

| File | Change |
|---|---|
| `common/barge_in.py` | New file — `BargeInDetector` class |
| `common/wake_word.py` | Remove 5 barge-in methods; add `self.barge_in`; update call sites |
| `tests/test_barge_in.py` | New test file for `BargeInDetector` in isolation |
| `tests/test_wake_word.py` | Remove barge-in method tests now covered by `test_barge_in.py` |

---

## Out of Scope

- No VAD/recording split (that's a future plan)
- No streaming pipeline split (that's a future plan)
- No behavior changes
- No config changes

---

## Acceptance Criteria

- [ ] `common/barge_in.py` created with `BargeInDetector` class
- [ ] `BargeInDetector` has `start()`, `stop()`, `is_triggered`, `clear()`, `run_with_polling()`
- [ ] Five barge-in methods removed from `WakeWordMode`
- [ ] All call sites in `wake_word.py` updated to use `self.barge_in.*`
- [ ] `tests/test_barge_in.py` covers `BargeInDetector` in isolation (>80% coverage)
- [ ] All existing tests pass
- [ ] `wake_word.py` reduced by ~200 lines
