# Barge-In: Stop TTS When Wake Word Is Heard

**Status**: ✅ Completed
**Priority**: 9
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

SandVoice is voice-first. When the assistant is speaking (TTS playback), users should be able to interrupt it by saying the wake word (Alexa-style barge-in).

This feature stops TTS playback immediately when the wake word is detected. After stopping, SandVoice should transition into listening/recording the user command.

---

## Problem Statement

Current behavior:
- While TTS is playing, SandVoice playback blocks and/or the app is not responsive to user interruption.
- Users cannot easily interrupt the assistant mid-sentence to issue a new command.

Desired behavior:
- While TTS is speaking, if the wake word is detected, stop speaking immediately.
- Provide a clear indication that SandVoice is now listening for the user command.

---

## Goals

- Voice-first: enable interruption of SandVoice speech via wake word
- Stop TTS quickly and reliably (target: < 250ms from wake word detection)
- Preserve existing wake word mode behavior and state machine structure
- Keep cross-platform compatibility (macOS and Raspberry Pi)

---

## Non-Goals

- Full acoustic echo cancellation (AEC)
- Interrupting external music playback (Spotify ducking/pause is a separate plan)

---

## Implementation (As Shipped)

### Architecture

- When `barge_in` is enabled, wake word mode starts a dedicated "barge-in" thread while processing/responding.
- The barge-in thread:
  - creates its own Porcupine instance
  - opens a dedicated PyAudio input stream
  - sets an event when the wake word is detected
- Wake word mode reacts to that event by:
  - stopping playback immediately (including a full mixer reset)
  - cleaning up temporary TTS chunk files
  - transitioning directly to `LISTENING`

### State Machine Integration

This shipped implementation supports barge-in across both states:

- `RESPONDING` + wake word detected => stop playback => `LISTENING`
- `PROCESSING` + wake word detected => stop any audio/beep, abandon current work => `LISTENING`

Notes:
- Long-running operations (API calls, plugin work) are not cancelled mid-flight; they may complete in background.
- For responsiveness, operations during `PROCESSING` run in a daemon thread and are polled every ~50ms for barge-in.

### Key Code Paths

- `common/audio.py`
  - `Audio.stop_playback(full_reset=True)` stops `pygame.mixer.music` and optionally `pygame.mixer.quit()` for a hard reset.
  - `Audio.play_audio_file(..., stop_event=...)` supports early stop for mid-playback interruption.
- `common/wake_word.py`
  - `_start_barge_in_detection()` / `_listen_for_barge_in()` manage the barge-in thread and event.
  - `_handle_immediate_barge_in(...)` performs stop + cleanup + transitions to `LISTENING`.
  - `_run_with_barge_in_polling(...)` provides responsive interruption during `PROCESSING`.
- Tests:
  - `tests/test_audio_playback.py` covers playback stop behavior.
  - `tests/test_wake_word.py` covers barge-in triggering transitions.

---

## Configuration

Config key:

```yaml
barge_in: enabled
```

Defaults to `disabled`.

---

## Acceptance Criteria

- [x] With wake word mode enabled, SandVoice can be interrupted mid-TTS by saying the wake word
- [x] On wake word detection during TTS, playback stops immediately
- [x] After barge-in, SandVoice begins listening for the next command (VAD recording)
- [x] If barge-in is disabled, behavior remains unchanged
- [x] Works on macOS M1 and Raspberry Pi 3B (requires real device validation if not yet done)

---

## Testing

- Unit tests: `Audio.stop_playback()` and `play_audio_file(..., stop_event=...)`
- Mocked state machine tests: wake event during responding/processing triggers stop + state transition

## Known Limitations / Follow-Ups

- No echo cancellation: the wake word may trigger on the assistant's own voice depending on speaker/mic setup.
- Some audio devices/OS setups may not allow multiple concurrent input streams; barge-in thread stream creation may fail.
- Background operations are not cancelled; they may still complete after barge-in.
