# Wake Word Barge-In Always On

**Status**: 📋 Backlog
**Priority**: 30
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- **Plan 09 (Barge-In)** — already merged; barge-in is the feature being hardened here.
- **Plan 29 (Always-Streaming TTS)** — should be implemented first; removes the pre-generated TTS path that also contains barge-in conditional branches.

---

## Overview

Make barge-in unconditionally active in wake-word mode. Remove the `barge_in_enabled` flag checks throughout `common/wake_word.py`, and add a fail-fast check at startup if barge-in is disabled. This removes ~35 lines of conditional branching and makes the code simpler to follow.

---

## Problem Statement

Every place that starts or checks barge-in detection in `wake_word.py` is guarded by:

```python
barge_in_enabled = getattr(self.config, "barge_in", False)
if barge_in_enabled and self.porcupine:
    ...
elif barge_in_enabled and not self.porcupine:
    logger.warning(...)
```

This pattern repeats across `_state_processing`, `_state_responding`, `_respond_streaming`, and `_poll_op`. Since barge-in is a core quality-of-life feature that works today on both platforms, and wake-word mode already requires Porcupine, there is no reason to allow disabling it independently. Keeping the flag adds branches that must be tested and reasoned about.

---

## Proposed Solution

1. **Fail-fast in `_initialize()`**: if `barge_in` is not enabled in config, raise `ConfigurationError` with a message explaining that wake-word mode requires barge-in.
2. **Remove all `barge_in_enabled` local variable assignments** (~4 occurrences).
3. **Remove all `if barge_in_enabled:` / `elif barge_in_enabled:` conditional branches** — treat the enabled path as unconditional.
4. **Simplify `_poll_op`**: remove the `barge_in_thread` parameter guard; always poll for barge-in.
5. **Simplify `_respond_streaming`**: remove the `if barge_in_enabled and self.porcupine:` / `elif barge_in_enabled and not self.porcupine:` block; always start barge-in detection if not already running.

Estimated net reduction: **~35 lines**.

### Configuration change

Add to `_initialize()`:

```python
if not getattr(self.config, "barge_in", False):
    raise ConfigurationError("wake-word mode requires barge_in: enabled")
```

The `barge_in` config key is retained (users still set it explicitly), but wake-word mode will refuse to start without it.

---

## Files to Touch

| File | Change |
|---|---|
| `common/wake_word.py` | Remove `barge_in_enabled` guards; add fail-fast in `_initialize()`; simplify `_poll_op` and `_respond_streaming` |
| `tests/test_wake_word.py` | Update tests to not mock `barge_in` off; add test for new fail-fast check |

---

## Out of Scope

- No changes to CLI mode or ESC-key mode
- The `barge_in` config key is NOT removed — kept for fail-fast validation and documentation purposes
- No audio or AI layer changes

---

## Acceptance Criteria

- [ ] `_initialize()` raises `ConfigurationError` if `barge_in` is not enabled
- [ ] All `barge_in_enabled` local variables removed
- [ ] All conditional branches on `barge_in_enabled` removed
- [ ] `_poll_op` unconditionally polls barge-in
- [ ] `_respond_streaming` unconditionally starts barge-in detection if not running
- [ ] All tests pass; >80% coverage on changed code
- [ ] `wake_word.py` reduced by ~35 lines
