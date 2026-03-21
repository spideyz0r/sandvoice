# Wake Word Dead Code and Duplicate Extraction

**Status**: ✅ Completed
**Priority**: 32
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Remove two pieces of dead code from `common/wake_word.py` and consolidate four repeated
patterns into private helper methods. No behavior changes. Estimated net reduction: **~95 lines**.

---

## Problem Statement

### Dead Code

**1. `self.streaming_route`**
Set once at `_state_processing()` but **never read**. Only ever reset to `None`.
An artifact of the pre-generated TTS path that was removed in Plan 29.

**2. `_should_stream_default_route()`**
The entire method body is `return True` — streaming has been unconditional since Plan 29.
Called once; the call site can be simplified to the remaining condition.

### Duplicated Patterns

| Pattern | Occurrences | ~Lines |
|---|---|---|
| PyAudio stream + instance cleanup | 3× (`_state_idle`, `_state_listening`, `_listen_for_barge_in`) | 25 |
| Barge-in thread cleanup (stop flag → join → clear refs) | 3× (`_handle_immediate_barge_in`, `_state_processing` except handler, `_state_responding`) | 25 |
| Confirmation beep playback (lock + exists check + play) | 4× (`_state_idle`, `_handle_immediate_barge_in`, `_state_responding`, `_respond_streaming`) | 30 |
| Response/streaming state reset | 2× (`_state_processing`, `_respond_streaming`) | 5 |

---

## Proposed Solution

### 1. Remove `self.streaming_route`

Delete the attribute assignment in `__init__` and `_state_processing`, and the reset in
`_respond_streaming`. No callers read the value.

### 2. Remove `_should_stream_default_route()`

Delete the method. Replace the one call site:

```python
# Before:
stream_default_route = (
    self._should_stream_default_route()
    and (self.plugins is not None)
    and (route.get("route") not in self.plugins)
)

# After:
stream_default_route = (
    (self.plugins is not None)
    and (route.get("route") not in self.plugins)
)
```

### 3. Extract `_cleanup_pyaudio(stream, pa)`

```python
def _cleanup_pyaudio(self, stream, pa):
    if stream is not None:
        with contextlib.suppress(Exception):
            stream.stop_stream()
            stream.close()
    if pa is not None:
        with contextlib.suppress(Exception):
            pa.terminate()
```

Replace the three duplicated try/except blocks with a single call each.

### 4. Extract `_cleanup_barge_in(timeout=0.3)`

```python
def _cleanup_barge_in(self, timeout=0.3):
    if self.barge_in_stop_flag:
        self.barge_in_stop_flag.set()
    if self.barge_in_thread and self.barge_in_thread.is_alive():
        with contextlib.suppress(RuntimeError):
            self.barge_in_thread.join(timeout=timeout)
    self.barge_in_thread = None
    self.barge_in_event = None
    self.barge_in_stop_flag = None
```

### 5. Extract `_play_confirmation_beep()`

```python
def _play_confirmation_beep(self):
    if not (getattr(self.config, "wake_confirmation_beep", False) and self.confirmation_beep_path):
        return
    if not os.path.exists(self.confirmation_beep_path):
        return
    try:
        with (self._audio_lock or contextlib.nullcontext()):
            self.audio.play_audio_file(self.confirmation_beep_path)
    except Exception as e:
        logger.warning("Failed to play confirmation beep: %s", e)
```

### 6. Extract `_reset_streaming_state()`

```python
def _reset_streaming_state(self):
    self.response_text = None
    self.streaming_response_text = None
    self.streaming_user_input = None
```

---

## Files to Touch

| File | Change |
|---|---|
| `common/wake_word.py` | Remove dead code; add 4 helper methods; replace call sites |
| `tests/test_wake_word.py` | Add unit tests for new helpers; remove tests that covered dead code |

---

## Out of Scope

- No file splits (that's Plan 33)
- No logic changes
- No config changes

---

## Acceptance Criteria

- [ ] `self.streaming_route` removed (attribute + all assignments/resets)
- [ ] `_should_stream_default_route()` removed; call site simplified
- [ ] `_cleanup_pyaudio()` replaces all 3 duplicated PyAudio cleanup blocks
- [ ] `_cleanup_barge_in()` replaces all 3 duplicated barge-in thread cleanup blocks
- [ ] `_play_confirmation_beep()` replaces all 4 duplicated beep playback blocks
- [ ] `_reset_streaming_state()` replaces both duplicated state reset blocks
- [ ] All tests pass; >80% coverage on changed code
- [ ] `wake_word.py` reduced by ~95 lines
