# Streaming Responses (And Optional Streaming TTS)

**Status**: 📋 Backlog
**Priority**: 8

---

## Overview

SandVoice currently waits for full model responses before printing. This makes the CLI feel slower compared to tools that stream tokens as they are generated.

This plan introduces streaming text output for responses, and (optionally) a follow-up enhancement to pipeline text streaming into chunked TTS generation so voice mode can start speaking before the full response is complete.

---

## Problem Statement

Current behavior:
- `AI.generate_response()` uses non-streaming OpenAI Chat Completions
- The user sees nothing until the whole response is generated
- For voice mode, TTS starts only after the full response is available

User impact:
- Perceived latency is high, especially for longer responses

---

## Goals

- Make CLI output feel immediate by streaming response text
- Preserve existing conversation history behavior and return values
- Keep implementation small and compatible with macOS + Raspberry Pi
- Optional: enable earlier audio playback by streaming-to-TTS in chunks

---

## Non-Goals

- Migrating the entire codebase to the Responses API
- Full duplex "voice-to-voice" realtime mode (out of scope)

---

## Proposed Design

### Phase 1: Stream Text Output

- Update `AI.generate_response()` to support `stream=True`
- Print incremental deltas to stdout as they arrive
- Accumulate deltas into a final string to:
  - return the final content
  - append to `conversation_history`

Acceptance criteria:
- [ ] Response text appears progressively during generation
- [ ] Final response is identical to the non-streaming version
- [ ] Errors and retries remain user-friendly

### Phase 2 (Optional): Streaming TTS Pipeline

High-level pipeline:
- Stream text from the LLM
- Buffer until a chunk boundary is reached (sentence/paragraph or max chars)
- Call TTS per chunk (respecting the 4096-char limit; keep a safety margin)
- Play chunk audio sequentially while the model continues generating

Acceptance criteria:
- [ ] In voice mode, time-to-first-audio improves for longer responses
- [ ] If chunk TTS fails mid-stream, fall back to text-only for that response and log the error

---

## Configuration

Proposed config keys (optional):

```yaml
stream_responses: enabled
stream_tts: disabled
stream_tts_boundary: sentence  # sentence|paragraph
```

---

## Testing

- Unit test streaming assembly: given simulated deltas, final string matches expected
- Unit test chunk boundary logic for streaming-to-TTS (Phase 2)
