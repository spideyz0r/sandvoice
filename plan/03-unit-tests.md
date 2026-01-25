# Unit Tests

**Status**: 📋 Planned
**Priority**: 3
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Establish comprehensive test suite covering core SandVoice functionality. Target >80% code coverage while maintaining simple, readable test code that matches the project's style. Mock external dependencies (OpenAI APIs, audio hardware, network calls) to enable fast, reliable testing.

---

## Problem Statement

Current state:
- Zero tests exist
- No way to verify changes don't break existing functionality
- Refactoring is risky without test safety net
- No confidence in cross-platform compatibility
- Manual testing is time-consuming and error-prone

---

## User Stories

**As a developer**, I want automated tests that verify core functionality, so I can refactor with confidence.

**As a contributor**, I want clear test examples to follow, so I know how to test new features.

**As a maintainer**, I want >80% code coverage, so most code paths are verified.

**As a user**, I want confidence that releases work correctly, so I don't encounter preventable bugs.

---

## Acceptance Criteria

### Test Infrastructure
- [ ] pytest configured with appropriate plugins
- [ ] Test directory structure established
- [ ] Mocking strategy documented
- [ ] Coverage reporting configured

### Coverage Goals
- [ ] >80% overall code coverage
- [ ] Achieve 100% where reasonably possible

### Test Categories
- [ ] Unit tests for all core modules
- [ ] Integration tests for plugin system
- [ ] Mock-based tests for external APIs
- [ ] Configuration loading tests
- [ ] Error handling tests

---

## Technical Requirements

### Test Framework

Use **pytest** with these plugins:
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Simplified mocking
- `pytest-asyncio` - If async code added later

### Directory Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_configuration.py    # Config loading tests
├── test_ai.py               # AI module tests (mocked OpenAI)
├── test_audio.py            # Audio tests (mocked hardware)
├── test_plugins.py          # Plugin loading tests
├── test_routing.py          # Route detection tests
├── plugins/
│   ├── test_echo.py
│   ├── test_weather.py
│   ├── test_news.py
│   ├── test_greeting.py
│   ├── test_technical.py
│   ├── test_realtime.py
│   └── test_hacker_news.py
└── integration/
    └── test_end_to_end.py   # Full workflow tests
```

### Mocking Strategy

**Mock External APIs:**
- OpenAI client (all methods: chat, transcribe, TTS)
- OpenWeatherMap API
- Google search
- RSS feeds
- Web requests (BeautifulSoup scraping)

**Mock Hardware:**
- PyAudio (audio recording/playback)
- pygame mixer
- Keyboard listener

**Don't Mock:**
- File I/O (use temp directories)
- YAML parsing
- JSON parsing
- String manipulation

### Fixtures (conftest.py)

Common fixtures to create:
- Mock OpenAI client
- Mock config object
- Mock SandVoice instance
- Temporary config files
- Sample API responses (JSON)

### Example Test Coverage

**What to Test:**
- Configuration loading and defaults
- Plugin discovery and loading
- AI routing logic
- Error handling paths
- Text extraction and cleaning
- Audio encoding/decoding (mocked)
- Plugin process functions
- API retry logic
- Fallback behaviors

**What Not to Test:**
- Third-party library internals (OpenAI SDK, PyAudio, etc.)
- Python standard library

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_configuration.py

# Run and show coverage report
pytest --cov --cov-report=html
open htmlcov/index.html
```

---

## Configuration Changes

Add `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    --cov=common
    --cov=plugins
    --cov=sandvoice
    --cov-report=term-missing
    --cov-report=html
    --verbose
```

Add to `requirements.txt`:
```
pytest>=7.0.0
pytest-cov>=4.0.0
pytest-mock>=3.10.0
```

---

## Testing Requirements

Tests must pass on both Mac M1 and Raspberry Pi 3B.

---

## Dependencies

- **Depends on**: Error Handling (Priority 1) - need error paths to test
- **Depends on**: Platform Auto-Detection (Priority 2) - need to test detection logic

---

## Out of Scope

- Performance/load testing
- Security testing
- UI/UX testing (no GUI)
- Real API integration tests (too expensive)
- CI/CD setup (future enhancement)

---

## Success Metrics

- >80% code coverage achieved
- All tests pass on Mac M1
- All tests pass on Raspberry Pi 3B
- Test suite runs in <30 seconds
- Zero flaky tests
- Clear test failure messages
