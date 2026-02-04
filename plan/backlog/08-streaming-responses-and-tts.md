# Streaming Responses (And Optional Streaming TTS)

**Status**: 📋 Backlog
**Priority**: 8

---

## Overview

SandVoice is voice-first. Today, it typically waits for the full model response before generating any audio, which makes the experience feel slow even when the model is working normally.

This plan introduces a "buffer then play" approach (similar to Spotify): stream the model output, quickly form a first speakable chunk (targeting ~1-10 seconds of audio), start playback as soon as that first chunk is ready, and continue generating/playing subsequent chunks while the model keeps streaming.

Streaming text output to the terminal is a secondary benefit (useful for debug/CLI), not the primary goal.

---

## Problem Statement

Current behavior:
- `AI.generate_response()` uses non-streaming OpenAI Chat Completions
- The user sees nothing until the whole response is generated
- For voice mode, TTS starts only after the full response is available

User impact:
- Perceived latency is high, especially for longer responses
- Voice mode feels unresponsive even when the model could begin speaking earlier

---

## Goals

- Voice-first: reduce time-to-first-audio by starting speech before the full response is complete
- Keep audio playing smoothly once it starts (avoid gaps by staying ahead of playback)
- Stream text output as a secondary benefit (useful for debug/CLI)
- Preserve existing conversation history behavior and return values
- Keep implementation small and compatible with macOS + Raspberry Pi

---

## Non-Goals

- Migrating the entire codebase to the Responses API
- Full duplex "voice-to-voice" realtime mode (out of scope)

---

## Proposed Design

### Phase 1: Streaming Text Assembly (Foundation)

- Update `AI.generate_response()` to support `stream=True`
- As deltas arrive, accumulate into a final string for:
  - conversation history
  - any non-voice pathways
- (Optional) print deltas to stdout when `debug` is enabled

Acceptance criteria:
- [ ] When streaming is enabled, output text can be assembled deterministically from deltas
- [ ] Final response text matches the non-streaming version for the same prompt/model
- [ ] Errors and retries remain user-friendly

### Phase 2: Voice-First Buffer Then Play (Primary Deliverable)

High-level pipeline:
- Stream text from the LLM
- Maintain a buffer of unspoken text
- As soon as the buffer contains a "first chunk" worth speaking (target ~1-10 seconds of audio), generate TTS and start playback
- Continue producing subsequent chunks (sentence/paragraph boundaries, plus max char limit) and enqueue them so playback stays ahead

Chunking strategy:
- First chunk: prefer 1-2 complete sentences; fallback to a short character threshold if no punctuation
- Subsequent chunks: re-use the existing TTS-safe splitting rules (<=4096 chars with margin)

Acceptance criteria:
- [ ] Time-to-first-audio improves (goal: start speaking within ~1-10 seconds for typical responses)
- [ ] Playback continues smoothly for long answers (no long gaps between chunks)
- [ ] If any chunk fails TTS, stop voice for that response, fall back to text-only, and log the error
- [ ] Temporary chunk files are cleaned up (unless debug preservation is enabled)

---

## Configuration

Proposed config keys (optional):

```yaml
stream_responses: enabled
stream_tts: enabled
stream_tts_boundary: sentence      # sentence|paragraph
stream_tts_first_chunk_target_s: 6 # target 1-10 seconds of initial audio
stream_tts_buffer_chunks: 2        # how many chunks to keep ahead of playback
```

---

## Testing

- Unit test streaming assembly: given simulated deltas, final string matches expected
- Unit test chunk boundary logic for streaming-to-TTS (Phase 2)
- Mocked integration test: TTS failure mid-queue falls back to text-only and cleans up temp files
