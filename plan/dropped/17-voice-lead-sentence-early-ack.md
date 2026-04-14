# Voice UX: One-Sentence Lead (Early Spoken Acknowledgement)

**Status**: 📋 Backlog
**Priority**: 17
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Even with an earcon, users often prefer hearing the assistant start speaking quickly.

This plan adds an optional, very short spoken "lead" (one sentence) while the main response is computed in the background.

---

## Problem Statement

Current behavior:
- The assistant speaks only after the final response text is ready and TTS is generated.

Desired behavior:
- If the response will take noticeable time, speak a short lead sentence first (e.g., "One sec, checking that now.")
- Then speak the real answer when it is available.

---

## Goals

- Reduce time-to-first-audio in voice mode
- Keep the lead safe and non-committal by default (no incorrect facts)
- Avoid talking too much (max 1 sentence)
- Ensure barge-in can interrupt both the lead and the final answer

---

## Non-Goals

- True streaming synthesis from token deltas (covered by Plan 08)
- Reading sources/citations aloud

---

## Proposed Design

### Trigger logic

- Only speak the lead if processing exceeds a small threshold (e.g., 600-900ms) to avoid unnecessary chatter.
- For very fast responses, skip the lead entirely.

### Lead styles

Two modes:

1) Fixed phrase bank (recommended initial implementation)
   - Choose a phrase randomly from a small list.
   - Optionally include light intent confirmation based on the route name (e.g., "Checking the weather.")

2) Model-generated lead (optional)
   - Use a smaller/faster model to generate a one-sentence lead.
   - Must be explicitly constrained to avoid factual claims.

### Concurrency model

- Start main work immediately (route + plugin/LLM response generation).
- In parallel, start a timer; if timer elapses and main work not finished, generate and speak the lead.
- When main work completes, speak the final response as usual.

### Safety constraints

- Default lead content should not include numbers/prices/forecasts.
- Never promise actions that might fail (avoid: "I found...")
- If barge-in triggers, stop lead and final playback immediately.

---

## Configuration

```yaml
voice_lead: enabled
voice_lead_delay_ms: 800
voice_lead_mode: fixed        # fixed|model
voice_lead_phrases:
  - "One sec."
  - "Got it - checking now."
  - "Okay - give me a moment."

# only if voice_lead_mode=model
voice_lead_model: gpt-4o-mini
```

Defaults:
- `voice_lead: disabled`
- `voice_lead_mode: fixed`

---

## Acceptance Criteria

- [ ] When enabled and response generation takes longer than the delay, the assistant speaks exactly one lead sentence
- [ ] For fast responses, no lead sentence is spoken
- [ ] Lead never contains fabricated facts (non-committal by default)
- [ ] Barge-in interrupts lead and final response
- [ ] Works on macOS and Raspberry Pi

---

## Testing

- Unit test: lead is skipped when main work completes before delay
- Unit test: lead is spoken when main work exceeds delay
- Unit test: lead spoken at most once per user request
- Unit test: barge-in stops playback during lead
