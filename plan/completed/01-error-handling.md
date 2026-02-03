# Error Handling

**Status**: 📋 Planned
**Priority**: 1
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Currently, SandVoice has minimal error handling. When API calls fail, network drops, or hardware issues occur, the application crashes with unhelpful stack traces. Users need graceful error handling with clear messages and automatic recovery where possible.

---

## Problem Statement

The current codebase lacks error handling in critical areas:
- OpenAI API calls (Whisper, GPT, TTS) can timeout or fail
- Network connectivity issues cause crashes
- Audio hardware unavailability crashes the app
- External APIs (weather, news) can return errors
- File I/O operations lack error handling

Users experience:
- Cryptic Python tracebacks instead of helpful messages
- Application exits unexpectedly
- No way to recover from transient failures
- No feedback when something goes wrong

---

## User Stories

**As a user**, I want clear error messages when something goes wrong, so I understand what happened and what to do next.

**As a user**, I want the app to retry failed API calls automatically, so temporary network issues don't interrupt my interaction.

**As a user**, I want the app to continue working in degraded mode when non-critical features fail, so I can still use basic functionality.

**As a user**, I want audio-only error notifications when in voice mode, so I don't need to look at the terminal.

---

## Acceptance Criteria

### API Error Handling
- [ ] All OpenAI API calls wrapped in try/except blocks
- [ ] Network timeouts handled gracefully (10-second timeout for API calls)
- [ ] Automatic retry with exponential backoff (3 attempts max)
- [ ] User-friendly error messages instead of stack traces
- [ ] Fallback behavior when APIs unavailable

### Audio Error Handling
- [ ] Detect when audio hardware is unavailable
- [ ] Provide helpful message with troubleshooting steps
- [ ] Fall back to text-only mode if audio fails
- [ ] Handle recording interruptions gracefully

### External Service Errors
- [ ] Weather API failures don't crash the app
- [ ] News feed parsing errors handled
- [ ] Web scraping failures caught and reported
- [ ] Invalid RSS feeds handled gracefully

### User Experience
- [ ] All errors logged to file for debugging (when debug mode enabled)
- [ ] Error messages appropriate for end users (not developers)
- [ ] Voice mode announces errors audibly
- [ ] Text mode prints errors clearly formatted

### Configuration Errors
- [ ] Missing config file creates default
- [ ] Invalid config values trigger warnings with defaults
- [ ] Missing API keys detected at startup with clear instructions

---

## Technical Requirements

### Error Categories

**Recoverable Errors** (retry, fallback, continue):
- Network timeouts
- API rate limits
- Temporary service unavailability
- Audio device busy

**Fatal Errors** (exit gracefully with message):
- Missing required API keys (OPENAI_API_KEY)
- Audio hardware completely unavailable (no fallback to text mode)
- Corrupt configuration file

**Degraded Mode Errors** (warn and continue with reduced functionality):
- TTS unavailable (fall back to text-only responses)
- Optional API keys missing (weather, news still work without those plugins)
- Single plugin failure (other plugins continue working)

### Retry Logic

API calls should implement exponential backoff:
1. First retry: 1 second delay
2. Second retry: 2 seconds delay
3. Third retry: 4 seconds delay
4. After 3 failures: report error to user, continue if possible

### Error Messages

**Good example**: "Unable to reach OpenAI API. Check your internet connection and try again."

**Bad example**: "requests.exceptions.ConnectionError: HTTPSConnectionPool(host='api.openai.com', port=443)"

### Logging

- Errors logged to `~/.sandvoice/error.log` when debug enabled
- Include timestamp, error type, full traceback
- User-facing messages kept simple

---

## Configuration Changes

Add to `config.yaml`:
```yaml
# Error handling settings
api_timeout: 10  # seconds
api_retry_attempts: 3
enable_error_logging: false  # set to true for debug mode
error_log_path: ~/.sandvoice/error.log
fallback_to_text_on_audio_error: true
```

---

## Testing Requirements

### Unit Tests
- Mock API failures and verify retry logic
- Test each error category (recoverable, fatal, degraded)
- Verify error messages are user-friendly
- Test fallback behaviors

### Integration Tests
- Disconnect network and verify graceful handling
- Kill audio device and verify text fallback
- Remove API key and verify startup error

### Manual Testing
- Test on Mac M1 and Raspberry Pi 3B
- Verify error messages are clear on both platforms
- Test with various failure scenarios

---

## Dependencies

None - this is foundational work that enables other features.

---

## Out of Scope

- Retry logic for audio recording (if recording fails, just fail - don't retry)
- Automatic API key rotation
- Error reporting to external service (no telemetry)
- GUI error dialogs (CLI only)

---

## Success Metrics

- Zero unhandled exceptions in normal operation
- All error paths have tests
- Error messages reviewed for clarity
- Manual testing confirms graceful degradation works
