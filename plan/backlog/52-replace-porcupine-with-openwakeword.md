# Replace Porcupine with openWakeWord

**Status**: 📋 Planned
**Priority**: 52
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- None — this is a self-contained engine swap.

---

## Overview

Replace the Picovoice Porcupine wake word engine with
[openWakeWord](https://github.com/dscripka/openWakeWord): a fully open-source,
free-to-use wake word detection library. Porcupine requires a Picovoice account
(now company-email-only) and enforces per-device activation limits, making it
unsuitable for self-hosted deployment. openWakeWord uses pre-trained ONNX models
(no account, no limits) and provides equivalent accuracy.

The new engine is wrapped behind a Porcupine-compatible interface
(`common/openwakeword_detector.py`) so `WakeWordMode` and `BargeInDetector` need
only minimal changes: swap the import and the constructor call.

---

## Problem Statement

- Porcupine free tier now requires a company email to obtain an access key.
- Per-device activation limits block re-deployment on a new Pi without a new key.
- `pvporcupine` is a closed binary; no path to self-hosted or offline use.

openWakeWord fixes all three issues: MIT-licensed, no account, runs on-device.

---

## Proposed Solution

### New file: `common/openwakeword_detector.py`

A Porcupine-compatible wrapper around openWakeWord's `Model` class:

```python
class OpenWakeWordDetector:
    """Wraps openWakeWord to expose the Porcupine interface used by WakeWordMode
    and BargeInDetector: sample_rate, device_sample_rate, frame_length,
    process(pcm) → int, reset(), delete()."""

    def __init__(self, model_name="hey_jarvis", threshold=0.5, device_sample_rate=None):
        ...

    @property
    def frame_length(self) -> int:
        """Samples per frame at device_sample_rate (covers the same 80 ms window)."""

    def process(self, pcm) -> int:
        """Return 0 if wake word detected, -1 otherwise.
        Resamples from device_sample_rate to 16 kHz when they differ
        (using scipy.signal.resample_poly for correct non-integer ratios).
        """

    def reset(self):
        """Clear the model's internal 30-frame rolling prediction buffer.
        Call before re-entering IDLE to prevent residual TTS audio (bot's voice
        picked up by the mic) from triggering a false positive on the first frame.
        """

    def delete(self):
        """No-op — openWakeWord holds no native resources."""
```

Handles both short built-in model names (`hey_jarvis`, `alexa`, …) and absolute
`.onnx` file paths for custom models.

### Changes to `common/wake_word.py`

- Replace `import pvporcupine` with `from common.openwakeword_detector import OpenWakeWordDetector`.
- Rename `_create_porcupine_instance()` → `_create_detector_instance()`, returning
  `OpenWakeWordDetector(model_name=..., threshold=..., device_sample_rate=config.rate)`.
- Call `self.porcupine.reset()` at the top of `_state_idle()` before opening the
  PyAudio stream (clears buffer state left over from the previous TTS cycle).
- Move `_play_confirmation_beep()` to after `_cleanup_pyaudio()` in
  `_state_idle()`. On Linux, PyAudio holds exclusive `hw:` device access while
  the input stream is open; playing the beep through pygame while the stream is
  still open blocks indefinitely. Closing the stream first avoids the contention.

### Changes to `common/barge_in.py`

- Replace `import pvporcupine` with `from common.openwakeword_detector import OpenWakeWordDetector`.
- Update `_create_porcupine_instance()` to return `OpenWakeWordDetector(...)`.

### Configuration changes (`common/configuration.py`)

| Key | Default | Notes |
|-----|---------|-------|
| `openwakeword_model` | `"hey_jarvis"` | Short built-in name or absolute `.onnx` path; authoritative for detection |
| `wake_phrase` | *(derived)* | User-facing label; see interaction rules below |
| `wake_word_sensitivity` | `0.35` | Lowered from `0.5`; openWakeWord scores differ from Porcupine |

**`wake_phrase` / `openwakeword_model` interaction:**

With Porcupine, `wake_phrase` drove keyword selection. With openWakeWord the
detectable phrase is fixed by the model, so `openwakeword_model` is
authoritative. The two keys interact as follows:

- **Built-in model** (e.g. `hey_jarvis`, `alexa`): the phrase is fixed by the
  model. `wake_phrase` must match the model's phrase (e.g. `"hey jarvis"` for
  `hey_jarvis`) so UI labels, logs, and the terminal prompt are consistent with
  what the detector actually listens for. Validation at startup should warn (or
  error) if they are mismatched.
- **Custom `.onnx` path**: the phrase cannot be reliably inferred from the
  filename. `wake_phrase` is user-provided and informational only; no mismatch
  validation is possible.

For the default config, set both keys consistently:
```yaml
openwakeword_model: hey_jarvis
wake_phrase: "hey jarvis"
```

Remove `porcupine_access_key` and `porcupine_keyword_paths` from defaults
(no longer needed). Keep validation for the new keys and the
`wake_phrase`/`openwakeword_model` consistency rule.

### `requirements.txt`

- Add `onnxruntime==1.20.0` (**hard pin — do not bump without Pi 3B testing**)
- Remove `pvporcupine`
- **Do NOT add `openwakeword` to `requirements.txt`** — see platform-specific
  install section below.

### Platform-specific install handling

`openwakeword` cannot be installed via `pip install -r requirements.txt` on
Raspberry Pi because `tflite-runtime` (a transitive dependency) has no wheel
for Python 3.13 on aarch64. To support both platforms without a broken
`requirements.txt`, `openwakeword` is kept out of the shared requirements file
and documented as a separate install step per platform.

**macOS (development):**
```bash
pip install openwakeword>=0.6.0
```

**Raspberry Pi 3B:**
```bash
# Install before requirements.txt; --no-deps skips tflite-runtime
pip install openwakeword>=0.6.0 --no-deps
pip install scipy   # required transitive dep not pulled in by --no-deps
pip install -r requirements.txt
```

Document this in `docs/raspberry-pi-setup.md` (Plan 05) and in a comment in
`requirements.txt` near the `onnxruntime` pin.

### Critical Pi 3B version constraints

> These were discovered through direct testing on Pi 3B (Trixie / Debian 13,
> Python 3.13, aarch64). Both constraints must be preserved exactly.

**`onnxruntime==1.20.0`**
Versions 1.21+ crash at model load time on Pi 3B with a C++ STL vector
assertion error deep in the ONNX runtime native library:
```
Assertion failed: (index < size_), function operator[], ...
```
1.20.0 is the last version confirmed stable on armv8/aarch64 Pi 3B.
Pin it exactly; do not use `>=` or `~=`.

**`openwakeword` — platform-specific install (see above)**
Covered in the "Platform-specific install handling" section above.
Full rationale: `tflite-runtime` has no wheel for Python 3.13 on aarch64;
`--no-deps` skips it; ONNX inference backend works without it.

Document both constraints in `docs/raspberry-pi-setup.md` (Plan 05).

---

## Files to Touch

| File | Change |
|------|--------|
| `common/openwakeword_detector.py` | New file |
| `common/wake_word.py` | Swap engine; add `reset()` call in `_state_idle()` |
| `common/barge_in.py` | Swap engine |
| `common/configuration.py` | Add `openwakeword_model`; lower sensitivity default; remove Porcupine keys |
| `requirements.txt` | Add `onnxruntime==1.20.0` (hard pin); remove `pvporcupine`; **do not add `openwakeword`** (platform-specific install — see above) |
| `tests/test_openwakeword_detector.py` | New test file |
| `tests/test_wake_word.py` | Update mocks |
| `tests/test_barge_in.py` | Update mocks |

---

## Out of Scope

- Custom wake word training (use any `.onnx` model via `openwakeword_model` path)
- Acoustic echo cancellation
- Sensitivity auto-tuning

---

## Acceptance Criteria

- [ ] `common/openwakeword_detector.py` created with `OpenWakeWordDetector` class
- [ ] `process()` resamples correctly for both 44100 Hz (Mac) and 48000 Hz (Pi)
- [ ] `reset()` clears the model buffer; no false positive on first IDLE frame after TTS
- [ ] `wake_word.py` and `barge_in.py` use `OpenWakeWordDetector`; no reference to pvporcupine
- [ ] `porcupine_access_key` removed from config defaults and validation
- [ ] `openwakeword_model` config key documented
- [ ] `onnxruntime==1.20.0` pinned in `requirements.txt`
- [ ] Tests pass on macOS M1 and Raspberry Pi 3B
- [ ] >80% coverage on `openwakeword_detector.py`
