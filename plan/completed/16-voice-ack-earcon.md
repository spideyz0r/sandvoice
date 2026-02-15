# Voice UX: Ack Earcon (Fast Feedback)

**Status**: ✅ Completed
**Priority**: 16
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

In voice-first interactions, perceived latency matters as much as actual latency.

This plan adds a short "ack" earcon (beep/tick) that plays once per request to confirm that SandVoice heard the user and started processing.

---

## Problem Statement

Current behavior:
- In wake word mode, SandVoice may be silent between the end of user speech and the start of TTS.
- Users can be unsure if the assistant heard them, causing repeated wake words or commands.

Desired behavior:
- Provide immediate, non-verbal feedback after the user finishes speaking (or after transcription completes).
- Keep it subtle and distinct from the wake confirmation beep.

---

## Goals

- Reduce perceived latency with immediate audio feedback
- Avoid long or annoying sounds (target: 50-120ms)
- Ensure no overlap with existing TTS playback (and respect barge-in)
- Configurable and easy to disable

---

## Non-Goals

- Replacing the wake confirmation beep
- Adding spoken filler words (covered by Plan 17)

---

## Proposed Design

### When to play

- Wake word mode: play after `LISTENING` completes and before `PROCESSING` work begins.
- Optional: also play for non-wake-word voice mode (CLI/audio button flows) when `bot_voice` is enabled.

### Earcon selection

- Use a different pitch/duration from the wake confirmation beep.
- Keep it quiet-ish and short.

### Implementation

- Reuse the existing beep generator used for wake confirmation (avoid introducing new deps).
- Add a new generated audio file (cached on disk) for the ack earcon.
- Ensure playback is skipped when audio hardware is unavailable or `bot_voice` is disabled.

---

## Configuration

```yaml
voice_ack_earcon: enabled
voice_ack_earcon_freq: 600
voice_ack_earcon_duration: 0.06
```

Defaults:
- `voice_ack_earcon: disabled`

---

## Acceptance Criteria

- [x] When enabled, an ack earcon plays once per user command before processing begins
- [x] Earcon is distinct from the wake confirmation beep (different config + separate cached file)
- [x] Earcon never overlaps with TTS (skip if audio is already playing)
- [x] Works in wake word mode on macOS and Raspberry Pi
- [x] Can be disabled via config

---

## Testing

- Unit test: earcon generation cached and re-used
- Unit test: wake word flow calls `play_audio_file()` for the earcon when enabled
- Unit test: earcon is skipped when disabled
