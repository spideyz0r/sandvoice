# Plan 14: Adaptive Energy Pre-Filter for VAD

## Status: 📋 Backlog

## Problem Statement

WebRTC VAD at aggressiveness 3 still classifies low-level ambient noise (TV dialogue,
fan hum, distant speech, mic self-noise) as speech. The `vad_silence_duration` counter
never resets because the VAD never sees a silence frame, so SandVoice keeps recording
until `vad_timeout` fires. This causes the system to record several extra seconds of
silence/noise after the user finishes speaking, increasing latency and sometimes sending
garbage audio to the STT API.

Repro: TV on in the background, or a second person speaking more than ~2m from the mic.

## Root Cause

WebRTC VAD is a rule-based signal-processing model from ~2012. It works on spectral
features and zero-crossing rate. At aggressiveness 3 it is strict about what counts
as speech, but low-level broadband noise (TV, music, room tone) has enough energy in
speech-frequency bands to pass. An energy gate eliminates these false positives before
WebRTC ever runs.

## Goals

1. Add an adaptive noise-floor calibration phase at the start of each recording
2. Pre-filter frames whose RMS energy is below `noise_floor × multiplier` before
   passing them to WebRTC VAD
3. Keep all changes inside `common/vad_recorder.py` — no changes to wake_word.py or
   any other module
4. No new dependencies (struct math, no numpy)
5. Config toggle + tunable multiplier

## Technical Approach

### Calibration phase (pre-speech)

While `speech_detected` is False, collect the RMS of each frame. After
`vad_energy_calibration_frames` frames (default 15 × 30ms = 450ms), compute
`noise_floor = mean(rms_values)`.

Once calibrated, for every subsequent frame:

```
rms = compute_rms(pcm)
if calibrated and rms < noise_floor * multiplier:
    is_speech = False   # override — below energy gate
else:
    is_speech = vad.is_speech(pcm, sample_rate)
```

### RMS computation (no numpy)

```python
import struct, math

def _rms(pcm: bytes) -> float:
    samples = struct.unpack_from(f"{len(pcm)//2}h", pcm)
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))
```

Typical noise floor on a USB mic in a quiet room: RMS 80–200.
Typical noise floor with TV at background volume: RMS 300–600.
Speech peaks: RMS 2000–8000.
A multiplier of 2.5 gives comfortable headroom in both cases.

### Configuration

Two new config keys (both optional, both have defaults):

```yaml
vad_energy_filter: enabled           # enabled | disabled (default: enabled)
vad_energy_threshold_multiplier: 2.5 # float > 1.0 (default: 2.5)
```

`vad_energy_calibration_frames` is intentionally not exposed — 15 frames (450ms) is
the right calibration window for all real-world cases.

## Implementation Plan

### Step 1 — `common/configuration.py`
- Add `vad_energy_filter` (default `"enabled"`) and
  `vad_energy_threshold_multiplier` (default `2.5`) to `_DEFAULTS`
- Load and validate in `Config._load_config()`:
  - `vad_energy_filter`: must be `"enabled"` or `"disabled"`
  - `vad_energy_threshold_multiplier`: must be a float > 1.0

### Step 2 — `common/vad_recorder.py`
- Add module-level `_rms(pcm)` helper (struct-only, no numpy)
- In `VadRecorder.record()`:
  - Before the loop: initialise `_rms_samples = []`, `_noise_floor = None`,
    `_CALIBRATION_FRAMES = 15`
  - Read `energy_filter_enabled` and `multiplier` from `self._config`
  - In the loop, before the WebRTC call:
    - If `not speech_detected` and `len(_rms_samples) < _CALIBRATION_FRAMES`:
      append `_rms(pcm)` to `_rms_samples`
    - When `len(_rms_samples) == _CALIBRATION_FRAMES` and `_noise_floor is None`:
      set `_noise_floor = mean(_rms_samples)`, log at DEBUG
    - If `energy_filter_enabled` and `_noise_floor is not None`:
      if `_rms(pcm) < _noise_floor * multiplier`: force `is_speech = False`

### Step 3 — Tests (`tests/test_vad_recorder.py`)
- Test `_rms()` with known PCM data
- Test that a frame below the energy gate is forced to `is_speech = False`
- Test that a frame above the gate passes through to the WebRTC mock
- Test that calibration uses exactly `_CALIBRATION_FRAMES` frames
- Test that the filter is skipped when `vad_energy_filter: disabled`
- Test the `vad_energy_threshold_multiplier` validation path

### Step 4 — Docs
- Add `vad_energy_filter` and `vad_energy_threshold_multiplier` to README config table
- Add a note to `docs/raspberry-pi-setup.md` in the audio section

## Success Criteria

- [ ] VAD stops within `vad_silence_duration` after user stops speaking even with
      TV audio playing at normal background volume
- [ ] No regression in quiet-room detection (speech still detected reliably)
- [ ] `vad_energy_filter: disabled` restores previous behavior exactly
- [ ] >80% test coverage on new/modified code in `vad_recorder.py`

## Effort: Small (≈ 60 lines of code + tests)

## Dependencies

- Plan 35 (VadRecorder extraction) — ✅ completed

## Relationship

- Supersedes original Plan 14 approach (IDLE-state calibration, numpy, WakeWordMode
  changes) — new approach is simpler and self-contained within VadRecorder
- Prerequisite for: Plan 62 (Silero VAD) — energy gate remains as a lightweight
  first-stage filter even after Silero replaces WebRTC
