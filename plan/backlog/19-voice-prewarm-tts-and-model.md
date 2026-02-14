# Voice UX: Pre-Warm (TTS and Model)

**Status**: 📋 Backlog
**Priority**: 19
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

First-response latency is often worse than steady-state latency due to cold starts (model spin-up, network, client init).

This plan adds an optional pre-warm step to reduce time-to-first-audio for the first user request.

---

## Problem Statement

Current behavior:
- On startup, the first TTS generation can take noticeably longer than subsequent calls.
- The first model call can also be slower.

Desired behavior:
- Optionally perform a low-cost pre-warm on startup so the first real user request is faster.

---

## Goals

- Improve perceived responsiveness for the first interaction
- Ensure pre-warm never speaks audio to the user
- Keep pre-warm costs predictable and opt-in

---

## Non-Goals

- Running periodic background warm-ups indefinitely
- Warming every possible model/plugin

---

## Proposed Design

### Pre-warm targets

- TTS: generate a tiny mp3 from a short input (e.g., ".") and delete it immediately.
- LLM: make a minimal request (very short prompt, max tokens small) and discard the output.

### When to pre-warm

- Run once after config and OpenAI client initialization.
- Skip if audio is disabled or `fallback_to_text_on_audio_error` suggests staying text-only.

---

## Configuration

```yaml
prewarm: enabled
prewarm_tts: enabled
prewarm_llm: enabled
prewarm_llm_model: gpt-4o-mini
prewarm_tts_text: "."
```

Defaults:
- `prewarm: disabled`

---

## Acceptance Criteria

- [ ] When enabled, startup performs the pre-warm steps without user-visible output
- [ ] Pre-warm artifacts (tmp files) are cleaned up
- [ ] Pre-warm is skipped on failures without breaking the app
- [ ] Measurable improvement in time-to-first-TTS on typical networks

---

## Testing

- Unit test: prewarm does not call playback
- Unit test: prewarm cleans up temp file
- Unit test: failures do not crash startup when fallback-to-text is enabled
