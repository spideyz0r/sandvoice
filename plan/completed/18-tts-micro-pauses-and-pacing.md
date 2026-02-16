# Voice UX: TTS Micro-Pauses and Pacing

**Status**: ✅ Completed
**Priority**: 18
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

SandVoice uses chunked TTS playback for long responses.

Chunked synthesis can reduce natural pauses between sentences, making speech sound faster and more "rushed". This plan adds configurable micro-pauses and boundary tuning to improve perceived pacing.

---

## Problem Statement

Current behavior:
- Long replies are split into multiple mp3 chunks and played back-to-back.
- The result can feel faster than expected due to missing pauses at chunk boundaries.

Desired behavior:
- Insert small, natural pauses between chunks (and optionally at sentence boundaries).
- Improve prosody without changing the spoken content.

---

## Goals

- Slow perceived speech rate slightly (more breathing room)
- Keep implementation minimal (no DSP)
- Make it configurable and easy to tune per device
- Preserve barge-in responsiveness (pauses must be interruptible)

---

## Non-Goals

- Changing TTS voice/model quality
- Real-time time-stretching of mp3 playback

---

## Proposed Design

### Inter-chunk pause

- Add an optional delay between consecutive chunk files during playback.
- Use a simple sleep/delay in `Audio.play_audio_files()` after a chunk finishes.

### Boundary-aware chunking (optional follow-up)

- Bias chunk splitting toward punctuation boundaries so the model's prosody resets naturally.
- Keep existing max char guardrails.

### Interruptibility

- If barge-in stop is requested, pause/delay should be skipped and playback must stop immediately.

---

## Configuration

```yaml
tts_inter_chunk_pause_ms: 120
```

Defaults:
- `tts_inter_chunk_pause_ms: 0`

---

## Acceptance Criteria

- [x] With pause set > 0, there is a noticeable gap between chunk files
- [x] With pause set to 0, behavior remains unchanged
- [x] Barge-in can interrupt at any time (including during the pause)
- [x] Temporary files are still cleaned up as expected

---

## Testing

- Unit test: pause function is called between chunks when enabled
- Unit test: pause is skipped when disabled
- Unit test: stop_event interrupts during pause
