---
name: development-guidelines
description: Enforce SandVoice development guidelines, coding standards, and best practices. Use when implementing features, reviewing code, validating pull requests, or checking adherence to project standards.
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
user-invocable: true
disable-model-invocation: false
argument-hint: [feature-name|file-path]
---

# SandVoice Development Guidelines

Enforce development standards for SandVoice implementation. All code must follow these guidelines.

## When to use this skill

- Implementing features from plan/ directory
- Creating pull requests (ALWAYS create PR with Copilot review)
- Reviewing code against project standards
- Validating pull requests before merge
- Creating new plugins
- Adding configuration options
- Writing tests
- Ensuring platform compatibility

## Core Principles

1. **Simplicity First** - Solve the current problem, don't over-engineer
2. **Code Quality** - >80% test coverage, readable code, comprehensive error handling
3. **Platform Compatibility** - Work on Mac M1 AND Raspberry Pi 3B
4. **User Experience** - Clear error messages, sensible defaults

---

## Git Workflow

### Branch Strategy
- Create feature branch from latest main: `git checkout main && git pull && git checkout -b feature/<name>`
- Branch naming: `feature/<name>`, `fix/<name>`, `docs/<name>`
- Rebase on main before PR: `git fetch origin main && git rebase origin/main`

### Commit Messages
**CRITICAL: Never mention "Claude" or "AI" in commit messages**

Format:
```
Add feature description (50 chars or less)

- Bullet point details if needed
- Focus on what changed and why
- Use imperative mood (Add, Fix, Update, Remove)
```

Good examples:
- `Add error handling for OpenAI API calls`
- `Fix audio channel detection on macOS`
- `Update wake word sensitivity configuration`

Bad examples:
- `Claude helped me add error handling`
- `Fixed stuff`
- `WIP`

### Pull Requests
- Reference planning doc: "Implements plan/01-error-handling.md"
- Update plan/INDEX.md status when feature completed
- Clear description with testing checklist
- Self-review before requesting review

---

## Code Style

### Match Existing Patterns
- Study existing code before implementing
- Follow patterns in common/ and plugins/
- Consistency over personal preference
- Simple and readable over clever

### Python Style
```python
# Good - clear, simple, readable
def transcribe_audio(audio_file_path):
    """Convert audio file to text using Whisper API."""
    try:
        with open(audio_file_path, 'rb') as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcript.text
    except FileNotFoundError:
        return "Audio file not found"
    except openai.APIError as e:
        return "Unable to transcribe audio. Please try again."

# Bad - over-engineered
class AudioTranscriptionService:
    def __init__(self, client, model="whisper-1"):
        self._client = client
        self._model = model

    def transcribe(self, path, format="mp3", **kwargs):
        # Too complex for our needs
```

### Naming Conventions
- **Files**: `snake_case.py` (e.g., `audio.py`, `configuration.py`)
- **Classes**: `PascalCase` (e.g., `Audio`, `Config`)
- **Functions**: `snake_case` (e.g., `transcribe_audio`, `load_config`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT`)
- **Variables**: `descriptive_names` (e.g., `user_input`, NOT `ui` or `x`)

### Function Guidelines
- Keep functions small and focused (one responsibility)
- Max 50 lines per function (guideline, not hard rule)
- Use early returns to reduce nesting
- Max 3 levels of nesting

```python
# Good - early return, clear logic
def process_user_input(user_input):
    if not user_input:
        return "Please provide input"

    route = ai.define_route(user_input)
    if route["route"] not in plugins:
        return ai.generate_response(user_input)

    return plugins[route["route"]](user_input, route, self)

# Bad - deeply nested
def process_user_input(user_input):
    if user_input:
        route = ai.define_route(user_input)
        if route["route"] in plugins:
            return plugins[route["route"]](user_input, route, self)
        else:
            return ai.generate_response(user_input)
    else:
        return "Please provide input"
```

### Comments
- Code should be self-documenting
- Only comment where logic isn't obvious
- Explain "why", not "what"
- Keep comments updated with code

```python
# Good - explains why
# Retry with exponential backoff to handle transient network issues
time.sleep(2 ** attempt)

# Bad - explains what (obvious from code)
# Call the API
response = openai_client.chat.completions.create(...)
```

---

## Error Handling (CRITICAL)

### Always Wrap External Calls
- OpenAI API calls
- File I/O operations
- Network requests (weather, news, web scraping)
- Audio hardware operations

### Pattern to Follow
```python
def call_external_service():
    try:
        # External call here
        return result
    except SpecificError as e:
        if config.debug:
            logging.error(f"Error details: {e}")
        return "User-friendly error message"
    except AnotherSpecificError as e:
        # Handle differently if needed
        return "Different user-friendly message"
```

### Retry Logic for APIs
```python
def retry_with_backoff(func, max_attempts=3):
    """Retry function with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return func()
        except (NetworkError, TimeoutError) as e:
            if attempt == max_attempts - 1:
                raise
            delay = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(delay)
```

### Error Messages
**User-facing messages must be friendly:**
- Good: "Unable to reach OpenAI API. Check your internet connection and try again."
- Bad: "requests.exceptions.ConnectionError: HTTPSConnectionPool(host='api.openai.com')"

---

## Testing Requirements

### Coverage Target
- >80% code coverage for ALL new code
- Run: `pytest --cov --cov-report=term-missing`
- Verify before submitting PR

### Test Structure
```
tests/
├── conftest.py              # Shared fixtures
├── test_configuration.py
├── test_ai.py
├── test_audio.py
├── test_plugins.py
└── plugins/
    ├── test_echo.py
    └── test_weather.py
```

### Mocking External Dependencies
```python
# Always mock external APIs
def test_generate_response_api_failure(mock_openai_client):
    mock_openai_client.chat.completions.create.side_effect = openai.APIError("Network error")
    ai = AI(config)
    response = ai.generate_response("test")
    assert "unable to reach" in response.lower()
```

### Test Requirements
- Tests pass on Mac M1 AND Raspberry Pi 3B
- No flaky tests
- Fast suite (<30 seconds)
- Clear failure messages

---

## Platform Compatibility

### Target Platforms
- macOS M1/M2/M3 (development)
- Raspberry Pi 3B (deployment target)

### Platform Detection
```python
import platform

# Good - auto-detect
if platform.system() == 'Darwin':
    # macOS-specific code
elif platform.system() == 'Linux':
    # Linux/Pi-specific code

# Bad - hardcoded
if os.path.exists('/Users/'):
    # macOS - WRONG!
```

### Audio Platform Differences
- **macOS**: CoreAudio, mono (1 channel), no ALSA
- **Raspberry Pi**: ALSA, detect optimal channels, USB audio devices

### Test on Both Platforms
Before PR:
1. Test on Mac M1 (primary development)
2. Test on Raspberry Pi 3B (if available)
3. Use platform-agnostic paths (`pathlib.Path` or `os.path.join`)

---

## Configuration Management

### Adding Config Options
1. Add to `config.yaml` with comment
2. Add to `configuration.py` defaults dict
3. Add property in `Config.load_config()`
4. Validate at startup
5. Document in feature planning doc

Example:
```yaml
# Error handling settings
api_timeout: 10  # seconds - timeout for OpenAI API calls
api_retry_attempts: 3  # number of retry attempts
enable_error_logging: false  # true for detailed debug logs
```

```python
# In configuration.py defaults
self.defaults = {
    "api_timeout": 10,
    "api_retry_attempts": 3,
    "enable_error_logging": False,
}

# In load_config()
self.api_timeout = self.get("api_timeout")
self.api_retry_attempts = self.get("api_retry_attempts")
self.enable_error_logging = self.get("enable_error_logging").lower() == "enabled"
```

---

## Plugin Development

### Plugin Pattern (REQUIRED)
```python
def process(user_input, route, s):
    """
    Process user input for this plugin.

    Args:
        user_input: User's text input
        route: Dict with route info from AI (route name, parameters, reason)
        s: SandVoice instance (access config, ai, etc.)

    Returns:
        str: Response to user
    """
    try:
        # Plugin logic here
        result = do_something()
        return s.ai.generate_response(user_input, result)
    except Exception as e:
        if s.config.debug:
            print(f"Error in plugin: {e}")
        return "Sorry, I encountered an error processing your request."
```

### Plugin Checklist
- [ ] Follows process(user_input, route, s) signature
- [ ] Has error handling
- [ ] Returns user-friendly string
- [ ] Added route to routes.yaml
- [ ] Has test file in tests/plugins/
- [ ] Documented at top of file

### Plugin Best Practices
- Keep focused on one task
- Reuse shared utilities (avoid duplicating web scraping logic)
- Handle errors gracefully
- Return friendly messages

---

## Documentation

### Always Update
- `README.md` - for user-facing features
- `config.yaml` - when adding options (with comments)
- `plan/INDEX.md` - when starting/completing features
- Planning doc - if requirements change

### Documentation Style
- Clear and concise
- Assume technical user new to SandVoice
- Provide examples
- Update in same PR as code

---

## Implementation Workflow

### Starting Implementation

1. **Read planning document** in `plan/` directory
2. **Update status**: Change `plan/INDEX.md` to 🚧 In Progress
3. **Create branch**: `git checkout -b feature/<name>`
4. **Study existing code**: Understand patterns before coding
5. **Plan approach**: Think before typing

### During Development

1. **Write tests as you code** (not after)
2. **Run tests frequently**: `pytest`
3. **Check coverage**: `pytest --cov`
4. **Commit frequently** with clear messages
5. **Test on Mac M1**

### Before Pull Request

- [ ] All tests pass: `pytest`
- [ ] Coverage >80%: `pytest --cov`
- [ ] Tested on Raspberry Pi 3B (if available)
- [ ] Rebased on main: `git fetch origin main && git rebase origin/main`
- [ ] Updated `plan/INDEX.md` to ✅ Completed
- [ ] README updated (if user-facing)
- [ ] Config documented (if added options)
- [ ] Self-reviewed code
- [ ] Commit messages don't mention Claude

### Creating Pull Request

**CRITICAL: Always create a PR and request Copilot review when implementing features**

1. **Push branch to remote**:
```bash
git push -u origin feature/<name>
```

2. **Create PR with proper description**:
```bash
gh pr create --title "Brief feature title" --body "$(cat <<'EOF'
## Summary
Brief description of what was implemented

## Planning Document
Implements plan/XX-feature-name.md

## Changes
- Key change 1
- Key change 2
- Key change 3

## Testing
- [x] All tests pass
- [x] Coverage >80%
- [x] Tested on Mac M1
- [ ] Tested on Pi 3B

## Configuration Changes
List new config.yaml options (if any)
EOF
)" --base main
```

3. **Request Copilot review** (REQUIRED):
```bash
gh pr edit <PR_NUMBER> --add-reviewer "copilot-pull-request-reviewer[bot]"
```

4. **Confirm to user**:
- Provide PR URL
- Confirm Copilot reviewer added
- Let user know review is in progress

---

## What to Avoid

❌ **Over-engineering**
- Don't create abstractions until 3+ similar cases
- Don't add hypothetical features
- Don't optimize prematurely

❌ **Breaking Changes**
- Don't change existing behavior without discussion
- Don't remove features
- Don't change config format without migration

❌ **Poor Error Handling**
- No bare `except:` clauses
- No unhandled exceptions
- No stack traces to users

❌ **Platform-Specific Code**
- No hardcoded paths
- No platform assumptions
- Test on both Mac and Pi

❌ **Unclear Code**
- No single-letter variables (except i, j in loops)
- No deep nesting (>3 levels)
- No giant functions (>50 lines)

---

## Checklist Before PR

- [ ] Feature branch from latest main
- [ ] Implements planning doc requirements
- [ ] All acceptance criteria met
- [ ] Code matches existing style
- [ ] No over-engineering
- [ ] Comprehensive error handling
- [ ] All tests pass
- [ ] Coverage >80%
- [ ] Tested on Mac M1
- [ ] Tested on Pi 3B (when applicable)
- [ ] Config changes documented
- [ ] README updated (if user-facing)
- [ ] plan/INDEX.md updated
- [ ] Commits don't mention Claude
- [ ] PR created with proper description
- [ ] PR references planning doc
- [ ] Copilot reviewer added to PR

---

## Quick Reference

**Read planning docs first**: `plan/01-error-handling.md`, etc.

**Code patterns**: Study `common/ai.py`, `plugins/echo.py`

**Platform detection**:
```python
platform.system() == 'Darwin'  # Mac
platform.system() == 'Linux'   # Pi
```

**Test coverage**:
```bash
pytest --cov --cov-report=term-missing
```

**When in doubt**:
1. Check existing code
2. Review planning docs
3. Prioritize simplicity
4. Test on both platforms
