# wake_word.py Refactor

**Status**: 📋 Backlog
**Priority**: 24
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

`common/wake_word.py` has grown to 1565 lines through many incremental PR rounds. The core state machine design is sound, but two methods have accumulated significant complexity and duplication. This plan cleans them up without changing any behavior.

**Read before starting:**
- `common/wake_word.py` (entire file)
- `docs/PATTERNS.md` (all sections — especially logging and threading)
- `tests/test_wake_word.py` (understand current test coverage)

---

## Problem Statement

Four concrete issues, in priority order:

### 1. Logging pattern violation (entire file)
The file uses bare `logging.info()`, `logging.warning()`, `logging.error()` throughout instead of a module-level logger. This violates `docs/PATTERNS.md`.

Also uses f-strings in log calls (e.g., `logging.info(f"Transcription: {user_input}")`) instead of lazy `%s` formatting.

### 2. `import threading` inside `_state_responding` (line 1102)
A local import at the top of a method in a file that already imports `threading` at module level. Artifact of organic growth.

### 3. `_CompositeStopEvent` defined inline inside `_state_responding`
A class defined inside a method body at ~line 1145. It is a standalone, reusable concept — it belongs at module level.

### 4. `_state_responding` is ~310 lines handling two unrelated flows
The method handles two completely different code paths:
- **Streaming TTS path** (when `self.streaming_user_input` is set): LLM delta streaming → text queue → TTS worker thread → audio queue → player worker thread.
- **Pre-generated TTS path** (when `self.tts_files` is set): play MP3 files sequentially.

Both paths share only the barge-in event check and the cleanup/transition logic at the end. They should be separate private methods.

### 5. Repeated barge-in poll pattern in `_state_processing` (~5 occurrences)
The following pattern repeats five times in `_state_processing`:
```python
if barge_in_thread:
    completed, result = self._run_with_barge_in_polling(
        lambda: some_operation(),
        "operation name"
    )
    if not completed:
        self._handle_immediate_barge_in(barge_in_thread)
        return
else:
    result = some_operation()
```
This should be a helper method that encapsulates the pattern.

### 6. `stream_default_route` check duplicated in `_state_processing`
The same three-flag boolean (bot_voice + stream_responses + stream_tts) is computed twice in `_state_processing` — once in the plugin branch and once in the direct AI branch — followed by nearly identical code in each case. Compute once, or extract the streaming shortcut into its own helper.

---

## Goals

- Zero behavior change — this is purely structural
- All existing tests continue to pass
- Each PR is independently reviewable and testable
- File is meaningfully shorter and easier to navigate

## Non-Goals

- No new features
- No changes to the state machine logic
- No changes to barge-in detection behavior
- No changes to configuration

---

## Implementation: Two PRs

Split into two PRs to keep each review small and focused.

### PR A — Non-behavioral cleanup (do first)

Changes that have zero logic impact:

1. **Fix logging pattern**
   - Add `logger = logging.getLogger(__name__)` near the top of the module (after imports, before class/function definitions).
   - Replace every `logging.info(...)`, `logging.warning(...)`, `logging.error(...)`, `logging.debug(...)` call in the file with `logger.info(...)`, `logger.warning(...)`, etc.
   - Replace f-string log arguments with lazy `%s` format: `logger.info("Transcription: %s", user_input)` instead of `logger.info(f"Transcription: {user_input}")`.
   - Exception: leave any `logging.getLogger` calls untouched if they exist.

2. **Remove local `import threading`**
   - Delete the `import threading` line inside `_state_responding` (around line 1102). `threading` is already imported at module level.

3. **Lift `_CompositeStopEvent` to module level**
   - Cut the class definition from inside `_state_responding` and paste it at module level (after imports, before the main class definition).
   - No changes to the class body.

**Testing for PR A**: Run `pytest` — all tests must pass. No new tests needed (no behavior changes).

---

### PR B — Method extraction (do after PR A is merged)

Logic-preserving structural refactors:

1. **Extract `_respond_streaming(self)` from `_state_responding`**

   Cut the entire streaming path (the `if self.streaming_user_input:` block — approximately lines 1121–1403) into a new private method `_respond_streaming()`.

   `_state_responding` calls it as:
   ```python
   if self.streaming_user_input:
       self._respond_streaming()
   ```

   The extracted method handles:
   - Setting up `text_queue` and `audio_queue`
   - Starting `tts_worker` and `player_worker` threads
   - Streaming LLM deltas via `self.ai.stream_response_deltas()`
   - Chunking text via `pop_streaming_chunk()`
   - Joining threads
   - Printing final response text
   - Resetting `self.streaming_route`, `self.tts_files`, `self.response_text`

   Note: the barge-in cleanup and state transition (IDLE vs LISTENING) remain in `_state_responding` — they apply to both paths.

2. **Extract `_respond_pregenerated_tts(self)` from `_state_responding`**

   Cut the pre-generated TTS playback path (the `if self.tts_files and len(self.tts_files) > 0:` block, approximately lines 1405–1484) into a new private method `_respond_pregenerated_tts()`.

   `_state_responding` calls it as:
   ```python
   elif self.tts_files:
       self._respond_pregenerated_tts()
   ```

   The extracted method handles:
   - Starting barge-in thread if not already running
   - Playing each file via `self.audio.play_audio_file()`
   - Checking for barge-in after each file
   - Deleting played files
   - Handling playback errors

   Note: again, cleanup and state transition remain in `_state_responding`.

3. **Extract the barge-in poll helper in `_state_processing`**

   Create a private method:
   ```python
   def _poll_op(self, operation, name, barge_in_thread):
       """Run operation with barge-in polling. Returns result or handles barge-in and returns _BARGE_IN sentinel."""
   ```

   Where `_BARGE_IN` is a module-level sentinel object (e.g., `_BARGE_IN = object()`).

   The method runs `_run_with_barge_in_polling` when `barge_in_thread` is set, otherwise calls `operation()` directly. On barge-in, calls `_handle_immediate_barge_in(barge_in_thread)` and returns the sentinel.

   Callers in `_state_processing` check:
   ```python
   result = self._poll_op(lambda: self.ai.transcribe_and_translate(...), "transcription", barge_in_thread)
   if result is _BARGE_IN:
       return
   ```

   This replaces the 5 repeated if/else blocks.

4. **Deduplicate `stream_default_route` in `_state_processing`**

   Extract a private method:
   ```python
   def _should_stream_default_route(self):
       return (
           _is_enabled_flag(getattr(self.config, "bot_voice", False)) and
           _is_enabled_flag(getattr(self.config, "stream_responses", False)) and
           _is_enabled_flag(getattr(self.config, "stream_tts", False))
       )
   ```

   Call it in both places in `_state_processing` instead of recomputing.

**Testing for PR B**:
- Run `pytest` — all tests must pass.
- If `_state_responding` did not have direct unit tests (it likely relies on integration-style tests), add focused tests for `_respond_streaming` and `_respond_pregenerated_tts` to cover the method split.
- Coverage must not drop below 80%.

---

## Acceptance Criteria

- [ ] `logger = logging.getLogger(__name__)` at module top, no bare `logging.X()` calls remain
- [ ] No f-strings in log calls (use `%s` lazy format)
- [ ] No local `import threading` inside methods
- [ ] `_CompositeStopEvent` defined at module level
- [ ] `_state_responding` delegates to `_respond_streaming()` and `_respond_pregenerated_tts()`
- [ ] Barge-in poll pattern not repeated more than once in `_state_processing`
- [ ] All existing tests pass
- [ ] Coverage >= 80%
- [ ] No behavior changes (confirmed by tests)
