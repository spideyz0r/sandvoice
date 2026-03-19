# Wake Word Always-Streaming TTS

**Status**: ✅ Completed
**Priority**: 29
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Dependencies

- **Plan 08 (Streaming Responses and TTS)** — already merged; streaming TTS pipeline is the canonical path.

---

## Overview

Remove the pre-generated TTS playback path from `common/wake_word.py`. Wake-word mode already has a fully working streaming TTS pipeline (Plan 08). The pre-generated path — generate all TTS files up-front, then play sequentially — is now dead code that adds ~190 lines of complexity and four cleanup helper methods.

---

## Problem Statement

`wake_word.py` contains two TTS playback paths:

1. **Streaming path** (`_respond_streaming`): LLM deltas → TTS worker → audio queue → player worker, all concurrent. Lower latency, simpler cleanup (streaming handles it).
2. **Pre-generated path** (`_respond_pregenerated_tts`): Generate all TTS MP3 files first via `ai.text_to_speech()`, then play them one-by-one. This was the original implementation before Plan 08 landed.

Since Plan 08 merged, the pre-generated path is never the better choice. It adds ~190 lines that must be maintained, tested, and reasoned about. Four cleanup helpers (`_cleanup_remaining_tts_files`, `_cleanup_specific_tts_files`, `_cleanup_all_orphaned_tts_files`, `_schedule_orphaned_tts_cleanup`) exist solely to manage pre-generated file lifecycle.

---

## Proposed Solution

1. **Fail-fast in `_initialize()`**: if `bot_voice` is disabled or streaming (`stream_responses`, `stream_tts`) is disabled, raise `RuntimeError` with a clear message explaining wake-word mode requires streaming TTS.
2. **Delete `_respond_pregenerated_tts()`** (~75 lines).
3. **Delete the four cleanup helpers**: `_cleanup_remaining_tts_files`, `_cleanup_specific_tts_files`, `_cleanup_all_orphaned_tts_files`, `_schedule_orphaned_tts_cleanup` (~65 lines).
4. **Delete the TTS generation block in `_state_processing`**: the `if self.config.bot_voice:` block that calls `self.ai.text_to_speech()`, stores `self.tts_files`, logs, and cleans up on barge-in (~35 lines).
5. **Remove `self.tts_files` instance variable** and all assignments/references (~15 lines scattered).
6. **Simplify `_state_responding`**: remove the `elif self.tts_files:` branch and the cleanup of `self.tts_files` on exit — only the streaming call remains.

Estimated net reduction: **~190 lines** (from 1484 → ~1294).

### Configuration change

Add a startup check so users get a clear error instead of silent fallback:

```python
# In _initialize()
if not self.config.bot_voice:
    raise RuntimeError("wake-word mode requires bot_voice: enabled")
if not self.config.stream_responses:
    raise RuntimeError("wake-word mode requires stream_responses: enabled")
if not self.config.stream_tts:
    raise RuntimeError("wake-word mode requires stream_tts: enabled")
```

---

## Files to Touch

| File | Change |
|---|---|
| `common/wake_word.py` | Delete pre-generated TTS path, cleanup helpers, `self.tts_files` state, and add fail-fast checks |
| `tests/test_wake_word.py` | Remove tests for pre-generated TTS path; add tests for new fail-fast checks |

---

## Out of Scope

- No changes to `common/audio.py` or `common/ai.py`
- No changes to CLI mode or ESC-key mode
- No config key additions — only startup validation

---

## Acceptance Criteria

- [ ] `_respond_pregenerated_tts` deleted
- [ ] `_cleanup_remaining_tts_files`, `_cleanup_specific_tts_files`, `_cleanup_all_orphaned_tts_files`, `_schedule_orphaned_tts_cleanup` deleted
- [ ] `self.tts_files` instance variable removed
- [ ] TTS generation block in `_state_processing` deleted
- [ ] `_initialize()` raises `RuntimeError` if `bot_voice`, `stream_responses`, or `stream_tts` disabled
- [ ] All tests pass; >80% coverage on changed code
- [ ] `wake_word.py` reduced by ~190 lines
