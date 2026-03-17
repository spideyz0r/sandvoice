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

### Priority 20: Background Cache for Frequent Voice Queries
**Document**: [in-progress/20-background-cache-frequent-voice-queries.md](./in-progress/20-background-cache-frequent-voice-queries.md)
**Status**: Weather plugin fully integrated (caches full response text, legacy JSON migration, background refresh). More plugins TBD.
**Description**: Opt-in background refresh of weather/crypto/common info to enable instant spoken answers with freshness hints.

---

## Backlog 📋

### Priority 5: Raspberry Pi Compatibility
**Document**: [backlog/05-raspberry-pi-compatibility.md](./backlog/05-raspberry-pi-compatibility.md)
**Description**: Full compatibility testing and documentation for Raspberry Pi 3B deployment. Setup process, dependencies, and performance validation.

### Priority 10: Speech-to-Text Task and Language
**Document**: [backlog/10-speech-to-text-task-and-language.md](./backlog/10-speech-to-text-task-and-language.md)
**Description**: Make Whisper behavior configurable (transcribe vs translate) and allow explicit language hints for better accuracy.

### Priority 11: Plugin Route Name Normalization
**Document**: [backlog/11-plugin-route-name-normalization.md](./backlog/11-plugin-route-name-normalization.md)
**Description**: Standardize plugin module naming (underscore) while supporting hyphenated route names (e.g., hacker-news) via normalization/aliases.

### Priority 13: VAD Robustness - Timeout and Tuning
**Document**: [backlog/13-vad-robustness-timeout-tuning.md](./backlog/13-vad-robustness-timeout-tuning.md)
**Description**: Make VAD more robust in noisy environments via timeout enforcement, better feedback, and tuning/presets.

### Priority 14: Energy-Based Speech Detection
**Document**: [backlog/14-energy-based-speech-detection.md](./backlog/14-energy-based-speech-detection.md)
**Description**: Add ambient noise calibration and energy thresholding to reduce false positives from constant background audio.

### Priority 15: Speech Classification (ML)
**Document**: [backlog/15-speech-classification-ml.md](./backlog/15-speech-classification-ml.md)
**Description**: Explore lightweight ML-based speech classification (e.g., Silero VAD) to distinguish user speech from background dialogue.

### Priority 17: Voice Lead Sentence
**Document**: [backlog/17-voice-lead-sentence-early-ack.md](./backlog/17-voice-lead-sentence-early-ack.md)
**Description**: Speak a one-sentence acknowledgement when processing takes long, then speak the final answer when ready.

### Priority 18: TTS Micro-Pauses and Pacing
**Document**: [backlog/18-tts-micro-pauses-and-pacing.md](./backlog/18-tts-micro-pauses-and-pacing.md)
**Description**: Add configurable pauses between TTS chunks to make speech feel less rushed.

### Priority 22: Plugin Manifest System
**Document**: [backlog/22-plugin-manifest-system.md](./backlog/22-plugin-manifest-system.md)
**Description**: Self-contained plugin folders with plugin.yaml manifests that self-register routes, config defaults, and env var requirements — eliminating manual edits to routes.yaml when adding or removing plugins.

### Priority 23: Request Timing Summary Log
**Document**: [backlog/23-request-timing-summary-log.md](./backlog/23-request-timing-summary-log.md)
**Description**: Emit a single INFO line per request summarising transcription, routing, plugin, and TTS timing plus cache status. Enables clean benchmarking without enabling `log_level: debug`. Requires Plan 28.

### Priority 25: Terminal UI
**Document**: [backlog/25-terminal-ui.md](./backlog/25-terminal-ui.md)
**Description**: Replace flat emoji-based terminal output with a high-end CLI UI: ANSI colors, animated waiting dots, in-place status line updates, inline timing per phase, and clear conversation/status separation. Pure ANSI — no external dependencies, Pi-compatible.

### Future Enhancements
**Document**: [backlog/FUTURE.md](./backlog/FUTURE.md)
**Description**: Long-term feature ideas including API Cost Management, Conversation History Management, Code Deduplication, Timers & Reminders, Music Control, Smart Home Integration, Calendar Integration, Todo List Management, Multi-User Support, and Conversation Memory.

---

## Status Legend

- ✅ **Completed** - Implemented, tested, and merged to main
- 🚧 **In Progress** - Currently being implemented
- 📋 **Backlog** - Documented, ready for implementation
- 🔮 **Future** - Long-term ideas, not yet planned

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
