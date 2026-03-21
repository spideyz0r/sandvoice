# Wake Word VAD Recorder Extraction

**Status**: 📋 Backlog
**Priority**: 35
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- **Plan 34** — complete quick wins first to reduce noise before the structural split.

---

## Overview

Extract the VAD-based audio recording subsystem from `WakeWordMode._state_listening()`
into a dedicated `common/vad_recorder.py` module with a `VadRecorder` class. The class
encapsulates sample rate negotiation, frame processing, silence detection, and WAV file
writing — concerns that are orthogonal to the wake-word state machine.

Estimated net reduction in `wake_word.py`: **~130 lines**.

---

## Problem Statement

`_state_listening()` is **161 lines** and handles two distinct responsibilities:

1. **VAD recording** (the bulk): opening a PyAudio stream at the right sample rate,
   running the VAD frame loop, detecting speech/silence transitions, writing the WAV
   file, playing the ack earcon.
2. **State machine integration** (thin): deciding what to do with the result (transition
   to PROCESSING, handle errors).

The recording logic has no dependency on `WakeWordMode` state beyond reading a handful
of config values and writing `self.recorded_audio_path`. This mirrors exactly the
pattern used to extract `BargeInDetector` in Plan 33.

---

## Proposed Solution

### New file: `common/vad_recorder.py`

```python
class VadRecorder:
    def __init__(self, config, audio, audio_lock, ack_earcon_path=None):
        """
        Args:
            config:          Config instance (reads rate, vad_aggressiveness,
                             vad_frame_duration, vad_timeout, voice_ack_earcon, etc.)
            audio:           Audio instance (used to play ack earcon).
            audio_lock:      threading.Lock acquired around audio playback calls.
            ack_earcon_path: Path to the ack earcon file, or None if not configured.
                             Created once in WakeWordMode._initialize() and injected here
                             so VadRecorder does not recreate it on every recording.
        """

    def record(self) -> str | None:
        """
        Open mic, run VAD loop, detect speech, save WAV.

        Returns:
            Path to the recorded WAV file on success.
            None if no audio frames were captured (non-error; caller should
            return to IDLE without processing).

        Raises:
            RuntimeError: if no suitable sample rate is found or a stream
            open/read/write failure occurs.
        """
```

Internally `record()` handles:
- Sample rate negotiation (`_negotiate_sample_rate()`)
- PyAudio stream lifecycle (`_open_stream()`, `_cleanup_stream()`)
- VAD frame loop + silence detection
- WAV file writing
- Ack earcon playback after recording

### Changes to `WakeWordMode`

- Add `self.vad_recorder = VadRecorder(self.config, self.audio, self._audio_lock, self.ack_earcon_path)` in
  `_initialize()` (after `self.ack_earcon_path` is set up).
- Replace the body of `_state_listening()` with:

```python
def _state_listening(self):
    logger.debug("State: LISTENING")
    try:
        self.recorded_audio_path = self.vad_recorder.record()
        if self.recorded_audio_path:
            self.state = State.PROCESSING
        else:
            logger.warning("No audio frames captured; returning to IDLE")
            self.state = State.IDLE
    except Exception as e:
        logger.error("Recording failed: %s", e)
        self.state = State.IDLE
```

---

## Files to Touch

| File | Change |
|---|---|
| `common/vad_recorder.py` | New file — `VadRecorder` class |
| `common/wake_word.py` | Replace `_state_listening()` body; add `self.vad_recorder` |
| `tests/test_vad_recorder.py` | New test file for `VadRecorder` in isolation |
| `tests/test_wake_word.py` | Replace listening-state tests to mock `VadRecorder` |

---

## Out of Scope

- No streaming pipeline split (that's Plan 36)
- No behavior changes
- No config changes

---

## Acceptance Criteria

- [ ] `common/vad_recorder.py` created with `VadRecorder` class
- [ ] `VadRecorder.record()` handles full VAD loop (sample rate negotiation, frame loop,
      silence detection, WAV writing, ack earcon)
- [ ] `_state_listening()` reduced to ~10 lines (just calls `self.vad_recorder.record()`)
- [ ] `tests/test_vad_recorder.py` covers `VadRecorder` in isolation (>80% coverage)
- [ ] All existing tests pass
- [ ] `wake_word.py` reduced by ~130 lines
