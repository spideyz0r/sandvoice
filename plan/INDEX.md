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

### Priority 8: Streaming Responses (And Optional Streaming TTS)
**Document**: [backlog/08-streaming-responses-and-tts.md](./backlog/08-streaming-responses-and-tts.md)
**Description**: Stream LLM responses to stdout for lower perceived latency; optional follow-up to pipeline streaming text into chunked TTS for earlier voice playback.

### Future Enhancements
**Document**: [backlog/FUTURE.md](./backlog/FUTURE.md)
**Description**: Long-term feature ideas including:
- API Cost Management
- Conversation History Management
- Code Deduplication
- Timers & Reminders
- Music Control
- Smart Home Integration
- Calendar Integration
- Todo List Management
- Multi-User Support
- Conversation Memory

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
- Custom wake word documentation available in `docs/CUSTOM_WAKE_WORDS.md`
