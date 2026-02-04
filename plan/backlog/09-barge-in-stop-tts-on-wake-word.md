# Barge-In: Stop TTS When Wake Word Is Heard

**Status**: 📋 Backlog
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

## Proposed Design

### Architecture

- Introduce a lightweight, always-on wake word listener that can run while TTS playback is active.
- When wake word is detected:
  - stop TTS playback (e.g., `pygame.mixer.music.stop()`)
  - transition into the existing LISTENING state (VAD recording)

### State Machine Integration

In wake word mode, the state machine already includes `RESPONDING` and `IDLE`.
We should allow wake word detection to preempt `RESPONDING`:

- RESPONDING + wake_word_detected => stop playback => LISTENING

### Implementation Notes

- Ensure audio playback is stoppable (provide a `stop_playback()` method on `Audio`).
- Ensure wake word detection runs concurrently with playback:
  - simplest: a dedicated thread that monitors Porcupine frames and sets an event
- Avoid resource contention:
  - consider using a separate PyAudio stream for wake word detection
  - keep CPU usage low when idle

---

## Configuration

Proposed config key:

```yaml
barge_in_enabled: enabled
```

---

## Acceptance Criteria

- [ ] With wake word mode enabled, SandVoice can be interrupted mid-TTS by saying the wake word
- [ ] On wake word detection during TTS, playback stops immediately
- [ ] After barge-in, SandVoice begins listening for the next command (VAD recording)
- [ ] If barge-in is disabled, behavior remains unchanged
- [ ] Works on macOS M1 and Raspberry Pi 3B

---

## Testing

- Unit test: stopping playback calls mixer stop
- Integration test (mocked): wake event during responding triggers stop + state transition
