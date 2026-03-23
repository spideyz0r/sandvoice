# Wake Word Streaming Responder Extraction

**Status**: ✅ Completed
**Priority**: 36
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- **Plan 35** — complete VAD recorder extraction first to keep PRs focused.

---

## Overview

Extract the streaming response pipeline from `WakeWordMode._respond_streaming()` into a
dedicated `common/streaming_responder.py` module. The method is **265 lines** and
contains three nested worker functions (text queue producer, TTS worker, audio player
worker) that manage threaded queues — concerns orthogonal to the wake-word state machine.

Estimated net reduction in `wake_word.py`: **~240 lines**.

---

## Problem Statement

`_respond_streaming()` is the single largest method in the codebase. It manages:

1. **LLM streaming**: collecting deltas from `ai.stream_response_deltas()`, chunking text via
   `pop_streaming_chunk()`, putting chunks onto a text queue.
2. **TTS worker thread**: consuming text chunks, calling `ai.text_to_speech()`, writing audio
   files, putting file paths onto an audio queue.
3. **Audio player worker thread**: consuming audio file paths, acquiring the audio lock,
   playing files, deleting temp files.
4. **Barge-in polling**: checking `self.barge_in.is_triggered` between iterations.
5. **`_CompositeStopEvent`**: combining barge-in event + done event for clean shutdown.

Responsibilities 1–3 (and the threading plumbing) have no dependency on `WakeWordMode`
state beyond `self.ai`, `self.audio`, `self.barge_in`, and `self._audio_lock` — all of
which can be injected at construction time.

---

## Proposed Solution

### New file: `common/streaming_responder.py`

```python
class StreamingResponder:
    def __init__(self, ai, audio, audio_lock, barge_in, pop_chunk_fn):
        """
        Args:
            ai:           AI instance (stream_response_deltas, text_to_speech).
            audio:        Audio instance (play_audio_queue with audio_lock/stop_event pattern).
            audio_lock:   threading.Lock acquired around audio playback.
            barge_in:     BargeInDetector instance (polled for interruption).
            pop_chunk_fn: The standalone `pop_streaming_chunk` function imported from
                          `common.ai`. Injected rather than called via `ai` because it is
                          a module-level function, not an instance method.
        """

    def respond(self, user_input=None, response_text=None):
        """
        Stream a response to the user.

        If response_text is provided, stream it directly to TTS (pre-computed text).
        Otherwise, stream from the LLM via ai.stream_response_deltas() using user_input.
        user_input may be None when a pre-computed plugin response is provided via
        response_text.

        Barge-in interruption is communicated via barge_in.is_triggered (set by the
        BargeInDetector thread). StreamingResponder must not clear or stop the barge-in
        event — _state_responding() checks it after respond() returns to decide whether
        to transition to LISTENING.
        """
```

Internally `respond()` manages the text queue, TTS worker thread, audio player worker
thread, and barge-in polling. `_CompositeStopEvent` moves into this module (or
`common/events.py`).

### Changes to `WakeWordMode`

- Add `self.responder = StreamingResponder(self.ai, self.audio, self._audio_lock, self.barge_in, pop_streaming_chunk)`
  in `_initialize()` (where `pop_streaming_chunk` is the function already imported from `common.ai` at the top of `wake_word.py`).
- Replace the body of `_respond_streaming()` with a thin wrapper (keeping its no-arg
  signature so `_state_responding()` call sites stay unchanged):

```python
def _respond_streaming(self):
    user_input = self.streaming_user_input
    self.streaming_user_input = None
    precomputed_text = self.streaming_response_text
    self.streaming_response_text = None
    self.responder.respond(user_input, precomputed_text)
```

- `_state_responding()` call site remains unchanged (`self._respond_streaming()`).
- Barge-in handling (beep + state transition) stays in `_state_responding()`, which already
  checks `self.barge_in.is_triggered` after `_respond_streaming()` returns — no change needed.

---

## Files to Touch

| File | Change |
|---|---|
| `common/streaming_responder.py` | New file — `StreamingResponder` class, `_CompositeStopEvent` |
| `common/wake_word.py` | Replace `_respond_streaming()` body; add `self.responder`; remove `_CompositeStopEvent` |
| `tests/test_streaming_responder.py` | New test file for `StreamingResponder` in isolation |
| `tests/test_wake_word.py` | Replace `_respond_streaming` tests to mock `StreamingResponder` |

---

## Out of Scope

- No behavior changes
- No config changes
- Barge-in detection itself stays in `common/barge_in.py` (Plan 33)

---

## Acceptance Criteria

- [x] `common/streaming_responder.py` created with `StreamingResponder` class
- [x] `StreamingResponder.respond()` handles both LLM-stream and pre-computed paths
- [x] `_respond_streaming()` reduced to ~10 lines
- [x] `_CompositeStopEvent` moved out of `wake_word.py`
- [x] `tests/test_streaming_responder.py` covers `StreamingResponder` in isolation (>80% coverage)
- [x] All existing tests pass
- [x] `wake_word.py` reduced by ~240 lines
