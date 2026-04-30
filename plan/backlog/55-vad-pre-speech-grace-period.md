# VAD Pre-Speech Grace Period

**Status**: 📋 Planned
**Priority**: 55
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- None — standalone change to `common/vad_recorder.py`.

---

## Overview

After the wake word fires and the confirmation beep plays, `VadRecorder` opens the
microphone and immediately starts counting silence. The user has at most
`vad_silence_duration` seconds (default 1.5 s) to start speaking before the
recording is cut short and sent for transcription as near-empty audio — wasting
an API call and giving the impression the assistant didn't hear anything.

This plan adds a `speech_detected` flag to the VAD loop. The silence countdown
only starts once at least one speech frame has been seen. Before any speech, the
loop waits up to `vad_timeout` (default 30 s) for the user to begin talking.

---

## Problem Statement

Current VAD loop logic (simplified):

```python
if is_speech:
    silence_start = None
else:
    if silence_start is None:
        silence_start = time.time()          # ← starts immediately on first silent frame
    elif time.time() - silence_start >= vad_silence_duration:
        break                                 # ← cuts off before user speaks
```

After the beep, the first frames are silence (the user is still composing their
thought). The timer starts, reaches 1.5 s, and the loop exits — recording 1.5 s
of near-silence and sending `User: ` (empty) to the LLM.

---

## Proposed Solution

Add a `speech_detected` boolean, initialized to `False`. Only enter the silence
countdown branch once `speech_detected` is `True`.

```python
speech_detected = False

...

if is_speech:
    speech_detected = True
    silence_start = None
else:
    if speech_detected:                      # ← only count silence after speech starts
        if silence_start is None:
            silence_start = time.time()
        elif time.time() - silence_start >= vad_silence_duration:
            logger.debug("Silence detected (%.2fs)", time.time() - silence_start)
            break
```

**Effect**:
- Before the user speaks: loop continues until `vad_timeout` (30 s). User can
  take as long as they need to start talking.
- After the user speaks and stops: the 1.5 s silence window closes the recording
  exactly as before.
- Empty-input behavior: if the user never speaks, the full `vad_timeout` elapses
  and the recording is discarded (existing behavior for truly silent recordings).

No config changes required. Existing `vad_silence_duration` and `vad_timeout`
semantics are preserved.

---

## Files to Touch

| File | Change |
|------|--------|
| `common/vad_recorder.py` | Add `speech_detected` flag; gate silence countdown on it |
| `tests/test_vad_recorder.py` | Add tests for pre-speech silence (no early cutoff) and post-speech silence (normal cutoff) |

---

## Out of Scope

- Changing `vad_silence_duration` or `vad_timeout` defaults
- Acoustic noise detection or energy thresholding (Plan 14)

---

## Acceptance Criteria

- [ ] `VadRecorder.record()` does not cut off before the first speech frame is seen
- [ ] After speech is detected, silence of `vad_silence_duration` still ends the recording
- [ ] `vad_timeout` still terminates the recording if the user never speaks
- [ ] No config changes required
- [ ] Tests cover: starts speaking immediately, starts speaking after 2 s delay,
      never speaks (timeout), speaks then pauses
- [ ] All existing tests pass
- [ ] >80% coverage
