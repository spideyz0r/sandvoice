# SandVoice Development Plan

## Overview
This directory contains planning documentation for SandVoice features and improvements. Each feature has its own document with user stories, acceptance criteria, and technical requirements.

## Development Environment
- **Primary Development**: Mac M1
- **Target Platforms**: macOS (M1) and Raspberry Pi 3B
- **Testing Goal**: >80% code coverage
- **Code Style**: Simple, readable, matching existing patterns

## Current Priority Features

### Priority 1: Error Handling
**Status**: ✅ Completed
**Document**: [01-error-handling.md](./01-error-handling.md)
**Description**: Add comprehensive error handling for API calls, network failures, and hardware issues. Ensure graceful degradation and user-friendly error messages instead of crashes.

### Priority 2: Platform Auto-Detection
**Status**: ✅ Completed
**Document**: [02-platform-auto-detection.md](./02-platform-auto-detection.md)
**Description**: Automatically detect platform (macOS/Linux) and configure audio settings appropriately. Eliminate manual configuration footguns like `linux_warnings` and `channels`.

### Priority 3: Unit Tests
**Status**: ✅ Completed
**Document**: [03-unit-tests.md](./03-unit-tests.md)
**Description**: Establish comprehensive test suite with >80% code coverage. Mock external dependencies (OpenAI, audio hardware) and test core business logic.

### Priority 4: Wake Word Mode
**Status**: 📋 Planned
**Document**: [04-wake-word-mode.md](./04-wake-word-mode.md)
**Description**: Add always-on listening mode activated by "Hey Sandvoice" wake phrase. Include voice activity detection to automatically detect when user stops speaking.

### Priority 5: Raspberry Pi Compatibility
**Status**: 📋 Planned
**Document**: [05-raspberry-pi-compatibility.md](./05-raspberry-pi-compatibility.md)
**Description**: Ensure full compatibility with Raspberry Pi 3B. Document setup process, dependencies, and testing procedures for Pi deployment.

### Priority 6: TTS Chunked Playback
**Status**: 📋 Planned
**Document**: [06-tts-chunked-playback.md](./06-tts-chunked-playback.md)
**Description**: Split long responses into safe TTS chunks and play sequentially to avoid the 4096-character TTS input limit.

## Future Enhancements

See [FUTURE.md](./FUTURE.md) for detailed descriptions of planned future features:

- **API Cost Management**: Track and limit OpenAI API usage to prevent unexpected bills
- **Conversation History Management**: Implement smart truncation to prevent unbounded growth and token limit errors
- **Code Deduplication**: Refactor duplicated web scraping and plugin logic into shared utilities
- **Timers & Reminders**: "Remind me in 10 minutes to check the oven"
- **Music Control**: Integration with Spotify or local music playback
- **Smart Home Integration**: Control lights, thermostats via HomeAssistant or similar
- **Calendar Integration**: "What's on my calendar today?"
- **Todo List Management**: "Add milk to shopping list"
- **Multi-User Support**: Voice recognition for personalized responses per user
- **Conversation Memory**: Persistent memory of important facts across sessions

## Status Legend

- 📋 **Planned** - Documented, not started
- 🚧 **In Progress** - Currently being implemented
- ✅ **Completed** - Implemented and tested
- 🔮 **Future** - Planned for later iteration

## Development Workflow

1. Each feature gets a feature branch: `feature/<feature-name>`
2. Create PR to main with clear description
3. Code review and testing
4. Merge to main after approval
5. Update feature status in this INDEX

## Notes

- All features must maintain compatibility with both Mac M1 and Raspberry Pi 3B
- Code style should remain simple and readable
- Test coverage target: >80% for all new code
- Document configuration changes in each feature doc
