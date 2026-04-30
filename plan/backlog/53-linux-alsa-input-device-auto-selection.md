# Linux ALSA Input Device Auto-Selection

**Status**: 📋 Backlog
**Priority**: 53
**Platforms**: Raspberry Pi 3B (Linux). No change on macOS.

---

## Dependencies

- **Plan 52** — the openWakeWord engine must be in place first; this plan
  adjusts how the engine's PyAudio stream is opened, not which engine is used.

---

## Overview

On Linux, PyAudio's default input device is a virtual ALSA device (`default`,
`dmix`, or similar) that may deliver silence or low-quality audio instead of
routing to the real USB microphone. SandVoice's wake word detection and
barge-in detection both open their own PyAudio stream; without explicitly
selecting a real hardware device the mic signal is often zero and wake word
detection never fires.

This plan adds a helper `_find_hw_input_device(pa)` that scans the PyAudio
device list for the first device whose ALSA name matches `hw:N,M` and has at
least one input channel, then passes that index to `pa.open()`. On macOS the
helper returns `None` and PyAudio uses its normal default.

---

## Problem Statement

- Pi 3B with Razer Barracuda X 2.4 USB headset: PyAudio device index 7
  is the ALSA `default` virtual device — it enumerates successfully but
  delivers amplitude=0 frames.
- Device index 2 (`hw:2,0`) is the actual USB audio hardware — it works.
- Without explicit selection, `_state_idle()` logs `frame 1 max_amplitude=0`
  forever and no wake word is ever detected.
- The same issue affects `BargeInDetector._detection_loop()`.

---

## Proposed Solution

### `common/wake_word.py`

Add module-level helper (not a method — it has no dependency on `WakeWordMode`
state):

```python
def _find_hw_input_device(pa):
    """Return the index of the first real ALSA hardware input device.

    Scans PyAudio's device list for the first entry whose name contains
    'hw:N,M' and has maxInputChannels > 0. Returns None on non-Linux
    platforms or when no hw: device is found (PyAudio picks the default).
    """
    import re, platform
    if platform.system().lower() != "linux":
        return None
    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)
        if dev.get("maxInputChannels", 0) > 0 and re.search(r'hw:\d+,\d+', dev.get("name", "")):
            logger.debug("Wake word: selected hw input device index=%s name=%s", i, dev["name"])
            return i
    return None
```

Use it in `_state_idle()`:

```python
pa = pyaudio.PyAudio()
input_device_index = _find_hw_input_device(pa)
audio_stream = pa.open(
    rate=self.porcupine.device_sample_rate,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    input_device_index=input_device_index,  # None → PyAudio default on Mac
    frames_per_buffer=self.porcupine.frame_length,
)
```

### `common/barge_in.py`

Identical inline scan in `_detection_loop()` (or import and call the same
helper from `wake_word.py` if it makes sense to expose it; otherwise
duplicate the short scan to keep barge_in.py self-contained).

---

## Files to Touch

| File | Change |
|------|--------|
| `common/wake_word.py` | Add `_find_hw_input_device()`; use in `_state_idle()` |
| `common/barge_in.py` | Add equivalent hw: scan in `_detection_loop()` |
| `tests/test_wake_word.py` | Test helper returns correct index / None |
| `tests/test_barge_in.py` | Test detection loop passes correct device index |

---

## Out of Scope

- Output device selection (that is Plan 54)
- ALSA configuration files (`~/.asoundrc`)
- Multi-card setups beyond "first matching hw: input device"

---

## Acceptance Criteria

- [ ] `_find_hw_input_device()` returns `None` on macOS
- [ ] Returns the index of the first `hw:N,M` input device on Linux
- [ ] `_state_idle()` passes the returned index to `pa.open()`
- [ ] `_detection_loop()` in `barge_in.py` does the same
- [ ] Debug log emitted showing selected device name and index
- [ ] Tests pass on macOS M1 and Raspberry Pi 3B
- [ ] >80% coverage on new helper
