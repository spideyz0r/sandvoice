# SandVoice Development Plan

## Overview
This directory contains planning documentation for SandVoice features and improvements. Plans are organized by status to track development progress.

## Directory Structure

```
plan/
├── completed/       # Implemented and tested features
├── in-progress/     # Currently being implemented
├── backlog/         # Planned for future development
└── INDEX.md         # This file
```

## Development Environment
- **Primary Development**: Mac M1
- **Target Platforms**: macOS (M1) and Raspberry Pi 3B
- **Testing Goal**: >80% code coverage
- **Code Style**: Simple, readable, matching existing patterns

---

## Completed Features ✅

### Priority 1: Error Handling
**Document**: [completed/01-error-handling.md](./completed/01-error-handling.md)
**Description**: Comprehensive error handling for API calls, network failures, and hardware issues. Graceful degradation and user-friendly error messages.

### Priority 2: Platform Auto-Detection
**Document**: [completed/02-platform-auto-detection.md](./completed/02-platform-auto-detection.md)
**Description**: Automatic platform detection (macOS/Linux) and audio settings configuration. Eliminates manual configuration issues.

### Priority 3: Unit Tests
**Document**: [completed/03-unit-tests.md](./completed/03-unit-tests.md)
**Description**: Comprehensive test suite with >80% code coverage. Mocked external dependencies (OpenAI, audio hardware).

### Priority 6: TTS Chunked Playback
**Document**: [completed/06-tts-chunked-playback.md](./completed/06-tts-chunked-playback.md)
**Description**: Split long responses into safe TTS chunks to avoid 4096-character input limit. Sequential playback for smooth voice output.

### Priority 7: Hacker News API-Only Summaries
**Document**: [completed/07-hacker-news-api-only.md](./completed/07-hacker-news-api-only.md)
**Description**: Hacker News plugin uses only free Firebase API fields (no external HTML fetch/parsing), preserving the podcast-style output while improving reliability and cost.

### Priority 8: Streaming Responses and TTS
**Document**: [completed/08-streaming-responses-and-tts.md](./completed/08-streaming-responses-and-tts.md)
**Description**: Stream LLM responses to stdout for lower perceived latency; pipeline streaming text into chunked TTS for earlier voice playback.

### Priority 9: Barge-In (Stop TTS on Wake Word)
**Document**: [completed/09-barge-in-stop-tts-on-wake-word.md](./completed/09-barge-in-stop-tts-on-wake-word.md)
**Description**: Allow users to interrupt SandVoice speech by saying the wake word, stopping TTS immediately and transitioning into command listening.

### Priority 12: Route Definitions Default Route Alignment
**Document**: [completed/12-route-definitions-default-route-alignment.md](./completed/12-route-definitions-default-route-alignment.md)
**Description**: Fix default-rote typo and align default route naming across routes.yaml and routing fallbacks.

### Priority 16: Voice Ack Earcon
**Document**: [completed/16-voice-ack-earcon.md](./completed/16-voice-ack-earcon.md)
**Description**: Play a short ack earcon once per request (after recording, before processing) to reduce perceived latency in voice mode.

### Priority 21: Task Scheduler
**Document**: [completed/21-task-scheduler.md](./completed/21-task-scheduler.md)
**Description**: Lightweight SQLite-backed in-process scheduler supporting cron, interval, and one-shot tasks. Powers Plan 20 periodic cache refresh and future timers/reminders.

### Priority 27: Scheduled Tasks File and Lifecycle Management
**Document**: [completed/27-tasks-file-and-lifecycle.md](./completed/27-tasks-file-and-lifecycle.md)
**Description**: Move scheduled task definitions to a dedicated `~/.sandvoice/tasks.yaml` file and make it the sole source of truth — tasks removed from the file are automatically deleted from the DB on startup. `tasks.yaml` replaces the `tasks:` key in `config.yaml` with no backwards compatibility.

### Priority 24: Wake Word Refactor
**Document**: [completed/24-wake-word-refactor.md](./completed/24-wake-word-refactor.md)
**Description**: Structural cleanup of `common/wake_word.py`: lift `_CompositeStopEvent` to module level, extract `_respond_streaming()` and `_respond_pregenerated_tts()` from `_state_responding`, add `_poll_op()` to deduplicate the barge-in polling pattern, and add `_should_stream_default_route()` to replace a duplicated three-flag boolean.

### Priority 26: Configuration Audit and Simplification
**Document**: [completed/26-config-audit-simplification.md](./completed/26-config-audit-simplification.md)
**Description**: Removed 15 config keys — deprecated keys, internal streaming/TTS knobs, beep/earcon fine-tuning, and VAD internals — hardcoding their former defaults at call sites. No behavior change. ~30% reduction in user-facing config surface.

### Priority 28: Logging Level Refactor
**Document**: [completed/28-logging-level-refactor.md](./completed/28-logging-level-refactor.md)
**Description**: Replace `debug: enabled/disabled` with a standard `log_level: warning|info|debug` config key and remove ~200 scattered `if self.config.debug: logger.*()` guards — the logging framework is the filter, not the code. Prerequisite for Plan 23 (timing summary).

### Priority 29: Wake Word Always-Streaming TTS
**Document**: [completed/29-wake-word-always-streaming-tts.md](./completed/29-wake-word-always-streaming-tts.md)
**Description**: Remove the pre-generated TTS playback path from `common/wake_word.py` — streaming TTS (Plan 08) supersedes it. Deletes `_respond_pregenerated_tts`, four cleanup helpers, `self.tts_files` state, and the TTS generation block in `_state_processing`. ~190 lines removed.

### Priority 30: Wake Word Barge-In Always On
**Document**: [completed/30-wake-word-barge-in-always-on.md](./completed/30-wake-word-barge-in-always-on.md)
**Description**: Remove the `barge_in` config key entirely and all `barge_in_enabled` conditional branches throughout `wake_word.py`. ~35 lines removed.

### Priority 31: Wake Word Route Always Required
**Document**: [completed/31-wake-word-route-always-required.md](./completed/31-wake-word-route-always-required.md)
**Description**: Remove the dead-code `else` branch in `_state_processing` that handles a `None` route_message. sandvoice.py always provides this callback; the fallback path is unreachable. Fail-fast in `__init__` if None. ~30 lines removed.

### Priority 32: Wake Word Dead Code and Duplicate Extraction
**Document**: [completed/32-wake-word-dead-code-and-duplicates.md](./completed/32-wake-word-dead-code-and-duplicates.md)
**Description**: Remove `self.streaming_route` (never read) and `_should_stream_default_route()` (always returns True). Extract four repeated patterns into helpers: `_cleanup_pyaudio()`, `_cleanup_barge_in()`, `_play_confirmation_beep()`, `_reset_streaming_state()`. ~95 lines removed, no behavior change.

### Priority 33: Wake Word Barge-In Detector Extraction
**Document**: [completed/33-wake-word-barge-in-extractor.md](./completed/33-wake-word-barge-in-extractor.md)
**Description**: Extract the five barge-in detection methods from `WakeWordMode` into a dedicated `common/barge_in.py` module with a `BargeInDetector` class (start/stop/is_triggered/run_with_polling). ~200 lines removed from wake_word.py. Requires Plan 32.

### Priority 34: Wake Word Quick Wins — Config Validation and File Cleanup
**Document**: [completed/34-wake-word-quick-wins.md](./completed/34-wake-word-quick-wins.md)
**Description**: Extract `_require_config_enabled()` to replace 4 repetitive config validation blocks in `_initialize()`, and `_remove_recorded_audio()` to replace 3 duplicated file-cleanup blocks. ~15 net lines removed, no behavior change. Requires Plan 33.

### Priority 35: Wake Word VAD Recorder Extraction
**Document**: [completed/35-wake-word-vad-recorder-extraction.md](./completed/35-wake-word-vad-recorder-extraction.md)
**Description**: Extract VAD-based audio recording from `_state_listening()` into `common/vad_recorder.py` with a `VadRecorder` class. Also introduces `common/utils.py` for shared `_is_enabled_flag`. ~130 lines removed from wake_word.py, 95% test coverage on VadRecorder. Requires Plan 34.

### Priority 36: Wake Word Streaming Responder Extraction
**Document**: [completed/36-wake-word-streaming-responder-extraction.md](./completed/36-wake-word-streaming-responder-extraction.md)
**Description**: Extract the 265-line `_respond_streaming()` pipeline (text queue, TTS worker, audio player worker, barge-in polling) into `common/streaming_responder.py` with a `StreamingResponder` class. `_CompositeStopEvent` moved out of wake_word.py. ~240 lines removed, >80% test coverage on StreamingResponder. Requires Plan 35.

### Priority 11: Plugin Route Name Normalization
**Document**: [completed/11-plugin-route-name-normalization.md](./completed/11-plugin-route-name-normalization.md)
**Description**: Standardized plugin modules to underscore form (`hacker_news.py`). Added `normalize_plugin_name()`, `resolve_plugin_route_name()`, and hyphen aliases so route names like `hacker-news` dispatch correctly. Both forms registered in the plugin dict; invalid filenames logged with a rename hint.

### Priority 10: Speech-to-Text Task and Language
**Document**: [completed/10-speech-to-text-task-and-language.md](./completed/10-speech-to-text-task-and-language.md)
**Description**: Make Whisper behavior configurable (transcribe vs translate) and allow explicit language hints for better accuracy. `speech_to_text_task`, `speech_to_text_language`, `speech_to_text_translate_provider`, and `speech_to_text_translate_model` config keys implemented and validated.

### Priority 22: Plugin Manifest System
**Document**: [completed/22-plugin-manifest-system.md](./completed/22-plugin-manifest-system.md)
**Description**: Self-contained plugin folders with plugin.yaml manifests that self-register routes, config defaults, and env var requirements — eliminating manual edits to routes.yaml when adding or removing plugins.

### Priority 23: Request Timing Summary Log
**Document**: [completed/23-request-timing-summary-log.md](./completed/23-request-timing-summary-log.md)
**Description**: Emit a single INFO line per request summarising transcription, routing, plugin, and TTS timing plus cache status. Enables clean benchmarking without enabling `log_level: debug`. Per-request `_req_cache_hit_type` snapshot isolates summary from concurrent scheduler-thread cache reads. Requires Plan 28. Extended in PR #113 to include optional `filler@Xs` tag showing when the voice filler phrase finished relative to plugin start.

### Priority 20: Background Cache for Frequent Voice Queries
**Document**: [completed/20-background-cache-frequent-voice-queries.md](./completed/20-background-cache-frequent-voice-queries.md)
**Description**: SQLite-backed `VoiceCache` with TTL/max_stale freshness model. Cache integration for weather, hacker-news, and news plugins. `cache_auto_refresh` config drives startup warmup threads and periodic scheduler tasks per plugin.

### Priority 38: README Modernization
**Document**: [completed/38-readme-modernization.md](./completed/38-readme-modernization.md)
**Description**: Updated README to reflect the plugin manifest system, correct model defaults (`gpt-5-mini`, `gpt-4.1-nano`), `tmp_files_path` trailing-slash requirement, `~` expansion notes for config paths, quoted string config values, and consistent `./sandvoice.py` invocation throughout.

### Priority 25: Terminal UI
**Document**: [completed/25-terminal-ui.md](./completed/25-terminal-ui.md)
**Description**: ANSI terminal UI for wake-word mode: in-place status line, animated ●●● spinner, and formatted conversation output. Falls back to plain print() on non-TTY / TERM=dumb. Wired into WakeWordMode and StreamingResponder.

### Priority 39: Blocking Cache Warmup with Timeout and Retries
**Document**: [completed/39-blocking-cache-warmup.md](./completed/39-blocking-cache-warmup.md)
**Description**: Block SandVoice startup until `cache_auto_refresh` warmup completes (or times out), so the first user query hits cache unless warmup times out. Configurable timeout (`cache_warmup_timeout_s`, default 15s) and per-plugin retries (`cache_warmup_retries`, default 3). Warmup runs under the terminal UI spinner (integrated in Plan 40).

### Priority 40: Greeting Plugin Cache
**Document**: [completed/40-greeting-plugin-cache.md](./completed/40-greeting-plugin-cache.md)
**Description**: Migrate `plugins/greeting.py` to a folder-based manifest plugin and add time-bucket caching (`greeting:morning/afternoon/evening/night`). Wired into `cache_auto_refresh` so the greeting is warm at startup — instant response for "bom dia", "boa tarde", "boa noite". Cache warmup now runs under the terminal UI warm spinner alongside voice filler warm-up.

---

## In Progress 🚧

### Priority 4: Wake Word Mode
**Document**: [in-progress/04-wake-word-mode.md](./in-progress/04-wake-word-mode.md)
**Status**: Phases 1-5 completed (macOS), Phase 6 pending (Raspberry Pi testing)
**Description**: Hands-free voice activation mode with "hey sandvoice" wake phrase. Voice activity detection for automatic speech end detection.

**Completed Phases:**
- ✅ Phase 1: Infrastructure Setup (Dependencies, Config, Beeps)
- ✅ Phase 2: Wake Word Detection (Porcupine Integration)
- ✅ Phase 3: Voice Activity Detection (VAD Recording)
- ✅ Phase 4: State Machine Integration (Connect All States)
- ✅ Phase 5: Mode Isolation & CLI Integration

**Pending:**
- ⏸️ Phase 6: Raspberry Pi Testing (CPU usage, compatibility validation)

---

## Backlog 📋

### Priority 5: Raspberry Pi Compatibility
**Document**: [backlog/05-raspberry-pi-compatibility.md](./backlog/05-raspberry-pi-compatibility.md)
**Description**: Full compatibility testing and documentation for Raspberry Pi 3B deployment. Setup process, dependencies, and performance validation.

### Priority 14: Energy-Based Speech Detection
**Document**: [backlog/14-energy-based-speech-detection.md](./backlog/14-energy-based-speech-detection.md)
**Description**: Add ambient noise calibration and energy thresholding to reduce false positives from constant background audio.

### Priority 17: Voice Lead Sentence
**Document**: [backlog/17-voice-lead-sentence-early-ack.md](./backlog/17-voice-lead-sentence-early-ack.md)
**Description**: Speak a one-sentence acknowledgement when processing takes long, then speak the final answer when ready. Lead audio files pre-generated at startup and cached in ~/.sandvoice/voice_lead/.

### Priority 18: TTS Micro-Pauses and Pacing
**Document**: [backlog/18-tts-micro-pauses-and-pacing.md](./backlog/18-tts-micro-pauses-and-pacing.md)
**Description**: Add configurable pauses between TTS chunks to make speech feel less rushed.

### Priority 37: Context-Aware Routing
**Document**: [backlog/37-context-aware-routing.md](./backlog/37-context-aware-routing.md)
**Description**: Pass the last N conversation turns to `define_route` so the routing LLM can correctly resolve follow-up utterances. Fixes misrouting of clarifications (e.g. "I mean the FIFA World Cup" after a realtime_websearch query routing to `news`).


### Priority 41: Provider Interface ABCs
**Document**: [backlog/41-provider-abcs.md](./backlog/41-provider-abcs.md)
**Description**: Define `LLMProvider`, `TTSProvider`, and `STTProvider` abstract base classes in `common/providers/base.py`. Purely additive — no existing code changed. Foundation for Plans 42 and 43.

### Priority 42: OpenAI Provider Implementations
**Document**: [backlog/42-openai-provider-implementations.md](./backlog/42-openai-provider-implementations.md)
**Description**: Implement `OpenAILLMProvider`, `OpenAITTSProvider`, and `OpenAISTTProvider` in `common/providers/`. Logic moved from `AI` class; `AI` is unchanged in this plan. Requires Plan 41.

### Priority 43: AI Facade Migration
**Document**: [backlog/43-ai-facade-migration.md](./backlog/43-ai-facade-migration.md)
**Description**: Refactor `AI` into a thin facade: owns `conversation_history`, delegates capabilities to provider instances, and exposes `AI.from_config(config)` factory. Adds `llm_provider`, `tts_provider`, `stt_provider` config keys (all default to `openai`). Runtime method call sites (`generate_response`, `text_to_speech`, etc.) remain unchanged; only construction changes to `AI.from_config(config)`. Requires Plans 41 and 42.

### Future Enhancements
**Document**: [backlog/FUTURE.md](./backlog/FUTURE.md)
**Description**: Long-term feature ideas including API Cost Management, Conversation History Management, Code Deduplication, Timers & Reminders, Music Control, Smart Home Integration, Calendar Integration, Todo List Management, Multi-User Support, and Conversation Memory.

---

## Dropped 🗑️

### Priority 13: VAD Robustness - Timeout and Tuning
**Document**: [dropped/13-vad-robustness-timeout-tuning.md](./dropped/13-vad-robustness-timeout-tuning.md)
**Reason**: VadRecorder extraction (Plan 35) supersedes the internal complexity this addressed. Current VAD behavior is acceptable.

### Priority 15: Speech Classification (ML)
**Reason**: Silero VAD and similar models are not viable on Pi 3B in real-time. Dropped without a plan document.

---

## Status Legend

- ✅ **Completed** - Implemented, tested, and merged to main
- 🚧 **In Progress** - Currently being implemented
- 📋 **Backlog** - Documented, ready for implementation
- 🔮 **Future** - Long-term ideas, not yet planned
- 🗑️ **Dropped** - Consciously decided against; see `dropped/` for rationale

---

## Development Workflow

1. Each feature gets a feature branch: `feature/<feature-name>`
2. Create PR to main with clear description
3. Code review (including Copilot PR reviews)
4. Merge to main after approval
5. Move plan document to appropriate folder
6. Update this INDEX

---

## Notes

- All features must maintain compatibility with both Mac M1 and Raspberry Pi 3B
- Code style should remain simple and readable
- Test coverage target: >80% for all new code
- Document configuration changes in each feature plan
- Custom wake word documentation available in docs/CUSTOM_WAKE_WORDS.md
