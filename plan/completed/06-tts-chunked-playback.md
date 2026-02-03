# TTS Chunked Playback (Streaming-Like Voice)

**Status**: ✅ Completed
**Priority**: 6
**Platforms**: macOS M1 ✅, Raspberry Pi 3B ✅

---

## Overview

Long GPT responses currently fail in voice mode because OpenAI TTS rejects inputs larger than ~4096 characters (`string_too_long`). SandVoice should support long responses by splitting text into safe chunks and generating/playing TTS sequentially (a streaming-like experience), while still printing the full response to the terminal.

---

## Problem Statement

Current behavior:
- `AI.text_to_speech()` sends the full response as a single TTS request
- When the response is long, OpenAI returns `400 string_too_long`
- The user gets text output but voice mode breaks

User impact:
- Voice mode is unreliable for longer answers
- Failures are confusing (TTS fails after GPT succeeds)

---

## User Stories

**As a user**, I want long answers to still be spoken, so I can keep using voice mode for big responses.

**As a user**, I want the terminal to still show the full response even if voice playback fails, so I never lose the content.

**As a developer**, I want the solution to be simple and robust without real-time audio streaming complexity.

---

## Acceptance Criteria

### Chunking
- [ ] If the response exceeds TTS input limits, split it into chunks that fit
- [ ] Prefer chunk boundaries on paragraph breaks, then sentence endings, then whitespace; avoid splitting mid-word when possible
- [ ] Never produce empty chunks

### Playback
- [ ] Generate TTS for each chunk and play sequentially in order
- [ ] Use separate output filenames per chunk (do not overwrite input recording audio)
- [ ] Clean up chunk files after playback (unless debug/keep flag enabled)

### Failure Handling
- [ ] If any chunk fails TTS, stop voice playback and fall back to text-only for that response
- [ ] Log the error and include useful context (chunk index/size, exception details)
- [ ] If `debug` is enabled, print a clear message: "Something went wrong while generating voice. Showing text only." plus the chunk failure details

### UX
- [ ] Always print the full response to the terminal regardless of TTS success
- [ ] Do not attempt audio playback if no playable TTS audio was produced

---

## Technical Requirements

### Chunking Helper

Create a helper that splits text for TTS:
- Input: full response text, max chars
- Output: list of chunks (in order)
- Strategy: paragraphs -> sentences -> whitespace -> hard cut fallback
- Use a safety margin (e.g., 3800 chars) to avoid edge cases

### Audio Output Lifecycle

- Use a distinct output path from the input recording path
- Generate chunk MP3s with deterministic ordering (e.g., `response-<id>-chunk-001.mp3`)
- Ensure files are removed after playback unless configured otherwise

---

## Configuration Changes

Add to `config.yaml`:

```yaml
# TTS chunking
tts_chunking: enabled
tts_max_chars: 3800
tts_keep_chunk_files: disabled
```

---

## Testing Requirements

### Unit Tests

- Splitter produces chunks under the limit
- Splitter avoids empty chunks and preserves order
- Splitter handles long text with no punctuation

### Mocked Integration Tests

- Simulate OpenAI TTS rejecting a chunk and verify fallback behavior
- Verify chunk filenames do not overwrite recording input

---

## Dependencies

- **Depends on**: Error Handling (Priority 1) - consistent logging and user-friendly messaging

---

## Out of Scope

- Real-time audio streaming from the API
- Word-level timing / subtitles
- Changing the existing interaction modes (ESC key voice mode and CLI mode remain)

---

## Success Metrics

- Long responses can be spoken without hitting TTS length limits
- Clear fallback when chunk TTS fails
- No broken playback attempts when TTS output is missing
