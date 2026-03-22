# Wake Word Quick Wins: Config Validation and File Cleanup

**Status**: ✅ Completed
**Priority**: 34
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- **Plan 33** — should be completed first (already done ✅)

---

## Overview

Two small, low-risk consolidations inside `common/wake_word.py` that remove repetitive
boilerplate with no behavior changes. Estimated net reduction: **~55 lines**.

---

## Problem Statement

### 1. Repetitive Config Validation in `_initialize()` (~40 lines)

Five nearly-identical blocks check a config flag and raise `RuntimeError` if it is not
`"enabled"`:

```python
if not _is_enabled_flag(getattr(self.config, "vad_enabled", False)):
    error_msg = "Wake-word mode requires VAD ... set 'vad_enabled: enabled'"
    print(f"Error: {error_msg}")
    raise RuntimeError(error_msg)
```

The pattern repeats for `vad_enabled`, `barge_in`, `wake_confirmation_beep`, and two
more flags. Only the flag value, log message, and config key hint differ. Extracting a
helper reduces 5 × ~8 lines to 5 × 2 lines.

### 2. Duplicated Recorded-Audio Cleanup Pattern (~25 lines)

The pattern:

```python
if self.recorded_audio_path and os.path.exists(self.recorded_audio_path):
    try:
        os.remove(self.recorded_audio_path)
        self.recorded_audio_path = None
    except OSError as e:
        logger.debug("Failed to remove recorded audio: %s", e)
```

appears **4 times** in `wake_word.py` (in `_state_listening`, `_handle_immediate_barge_in`,
`_state_processing`, `_state_responding`). Extracting a helper reduces each to a
single call.

---

## Proposed Solution

### 1. Extract `_require_config_enabled(flag_value, flag_name, detail)`

```python
def _require_config_enabled(self, flag_value, flag_name, detail=""):
    """Raise RuntimeError if flag_value is not considered enabled by _is_enabled_flag()."""
    if not _is_enabled_flag(flag_value):
        msg = f"Wake-word mode requires {flag_name} to be enabled. {detail}".strip()
        print(f"Error: {msg}")
        raise RuntimeError(msg)
```

Replace each of the five validation blocks with a single call:

```python
self._require_config_enabled(
    getattr(self.config, "vad_enabled", False),
    "VAD",
    "Set 'vad_enabled: enabled' in your config.",
)
```

### 2. Extract `_remove_recorded_audio()`

```python
def _remove_recorded_audio(self):
    """Remove the temporary recorded audio file if it exists."""
    if not self.recorded_audio_path:
        return
    if os.path.exists(self.recorded_audio_path):
        try:
            os.remove(self.recorded_audio_path)
        except OSError as e:
            logger.debug("Failed to remove recorded audio: %s", e)
    self.recorded_audio_path = None
```

Replace each of the four duplicated blocks with `self._remove_recorded_audio()`.

---

## Files to Touch

| File | Change |
|---|---|
| `common/wake_word.py` | Add 2 helpers; replace 5 validation blocks and 4 cleanup blocks |
| `tests/test_wake_word.py` | Add unit tests for both new helpers |

---

## Out of Scope

- No module splits
- No logic changes
- No config changes

---

## Acceptance Criteria

- [x] `_require_config_enabled()` replaces all 5 config validation blocks in `_initialize()`
- [x] `_remove_recorded_audio()` replaces all 4 duplicated file-cleanup blocks
- [x] All tests pass; >80% coverage on changed code
- [x] `wake_word.py` reduced by ~55 lines
