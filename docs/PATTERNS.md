# SandVoice Code Patterns

Single source of truth for how things are done in this codebase. Every agent, every
contributor, every skill reads this before writing or reviewing code. When a new pattern
is established (e.g. from a Copilot review round), add it here so it is never missed again.

---

## Logging

Library modules (`common/*.py`) declare a module-level logger and use it exclusively.

```python
import logging

logger = logging.getLogger(__name__)

# Usage
logger.info("Scheduler started (poll_interval=%ds)", self._poll_interval)
logger.error("Task '%s' failed: %s", task.name, e)
logger.debug("Due tasks fetched: %d", len(due))
logger.warning("Thread did not exit within %s seconds", timeout)
```

**Rules:**
- Always `logger = logging.getLogger(__name__)` at module top — never `logging.info()` /
  `logging.error()` directly (those write to the root logger with no module context)
- Use `%s` / `%d` style formatting in logger calls, not f-strings — the logging module
  skips formatting when the log level is inactive
- Never use `print()` for diagnostic output in library modules
- Never guard log calls with `if self.config.debug:` — the framework filters at the threshold

**Log level assignment** (Plan 28 — applies when removing `if self.config.debug:` guards):

| What it logs | Level |
|---|---|
| Module startup / shutdown | `INFO` |
| User-triggered events (barge-in, wake word) | `INFO` |
| Phase milestones visible to operators (N TTS files, scheduler tick) | `INFO` |
| Config state at startup (VAD disabled, feature flags) | `INFO` |
| Internal setup details, file paths, parameters | `DEBUG` |
| Internal loop events (timeout, silence, VAD frame) | `DEBUG` |
| Internal thread / state-machine transitions | `DEBUG` |
| Cleanup details, temporary file names | `DEBUG` |
| Config warnings, deprecated keys | `WARNING` |
| Recoverable errors (fallback used) | `WARNING` |
| Unrecoverable errors | `ERROR` |

When a log argument requires non-trivial construction (list comprehension, glob), guard the
whole block with `if logger.isEnabledFor(logging.DEBUG):` so the work is skipped entirely:

```python
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Cleanup: %s", [os.path.basename(f) for f in files])
```

**User-facing output** (always shown, not gated) uses `print()` directly — this is intentional
and correct for top-level / plugin code:

```python
print(f"You: {user_input}")
print("Warning: audio hardware not found.")
```

**Plugins** follow the same logger rule if they have a class; for standalone `process()`
functions, `logging.error()` is acceptable since plugins are simpler and have fewer log points.

---

## Error Handling

### User-facing messages

Never expose raw exceptions or stack traces to the user. Always convert to a friendly string.
Use helpers from `common/error_handling.py`:

```python
from common.error_handling import handle_api_error, handle_file_error

# API / network errors
error_msg = handle_api_error(e, service_name="OpenWeatherMap")

# File I/O errors
error_msg = handle_file_error(e, operation="read", filename="recording.wav")
```

For novel error types not covered by the helpers, use `format_user_error()`:

```python
from common.error_handling import format_user_error

return format_user_error("Service Error", "Unable to reach X. Try again.", str(e))
```

### Wrapping external calls

Every call to an external API, file system, or network resource is wrapped:

```python
try:
    result = external_call()
    return result
except SpecificError as e:
    error_msg = handle_api_error(e, service_name="X")
    logger.error("Detail: %s", e)
    print(error_msg)
    raise   # or return error_msg, depending on whether the caller handles it
except Exception as e:
    error_msg = handle_api_error(e, service_name="X")
    logger.error("Unexpected error: %s", e)
    print(f"Error: {error_msg}")
    raise
```

### Transient vs permanent errors

Distinguish — wrong treatment causes silent hangs or silent data loss:

| Type | Behaviour | Examples |
|---|---|---|
| Transient | Retry; if task, keep active | Network timeout, rate limit, temporary API error |
| Permanent | Stop immediately; log clearly | Bad JSON, missing required field, unknown type |

For scheduled tasks: a one-shot (`once`) task that fails transiently stays `active` for retry
on the next tick. A permanent config error sets status to `completed` immediately.

Non-retryable exceptions (never retried by `retry_with_backoff`):
`FileNotFoundError`, `PermissionError`, `ValueError`, `KeyError`, `json.JSONDecodeError`

---

## Retry Logic

Use the `@retry_with_backoff` decorator for all OpenAI API calls. Do not roll your own retry loop.

```python
from common.error_handling import retry_with_backoff

@retry_with_backoff(max_attempts=3, initial_delay=1)
def call_openai(self, ...):
    ...
```

The decorator reads `config.api_retry_attempts` at call time (overrides the decorator param),
uses exponential backoff (1s → 2s → 4s), and skips retry for non-transient exceptions.

Do **not** apply `@retry_with_backoff` to streaming calls — retry semantics are ambiguous
when partial output has already been emitted.

---

## Configuration Additions

Every new config option follows exactly these four steps. Missing any step is a defect.

1. **Add to `defaults` dict** in `common/configuration.py` with an inline comment:
   ```python
   "scheduler_poll_interval": 30,   # seconds between scheduler ticks
   ```

2. **Add property in `load_config()`**:
   ```python
   raw_poll = self.get("scheduler_poll_interval")
   try:
       self.scheduler_poll_interval = max(1, int(raw_poll)) if raw_poll is not None else 30
   except (TypeError, ValueError):
       self.scheduler_poll_interval = 30
   ```

3. **Add validation in `validate_config()`** with a descriptive error message:
   ```python
   if not isinstance(self.scheduler_poll_interval, int) or self.scheduler_poll_interval < 1:
       errors.append("scheduler_poll_interval must be an integer >= 1")
   ```

4. **Document in README.md** under "Configuration options" with type, valid values, and default.

Boolean-like config values from YAML need special handling (YAML parses `enabled`/`disabled`
as strings, but `true`/`false` as booleans). Use this pattern:

```python
raw = self.get("some_flag")
if isinstance(raw, bool):
    self.some_flag = raw
else:
    self.some_flag = str(raw or "disabled").strip().lower() in ("enabled", "true", "yes", "1", "on")
```

File path config values: always `os.path.expanduser()` and always `os.path.join()`.

---

## File Paths

No exceptions.

```python
# Correct
config_file = os.path.join(os.path.expanduser("~"), ".sandvoice", "config.yaml")

# Wrong — never do this
config_file = os.environ['HOME'] + "/.sandvoice/config.yaml"
config_file = f"~/.sandvoice/config.yaml"
```

---

## Plugin Structure

Signature is fixed — do not change it:

```python
def process(user_input, route, s):
    """
    Args:
        user_input: User's text input (str)
        route: Dict from AI router — always has 'route' key, may have extras (location, unit, query...)
        s: SandVoice instance — access s.ai, s.config, s.plugins
    Returns:
        str: Response to the user
    """
    try:
        data = fetch_something(s.config)
        return s.ai.generate_response(user_input, str(data)).content
    except ValueError as e:
        logger.error("Plugin config error: %s", e)
        return "Unable to complete request. Please check your configuration."
    except Exception as e:
        logger.error("Plugin error: %s", e)
        return "Unable to complete request. Please try again."
```

Rules:
- Always returns a `str` — never `None`, never raises to the caller
- `s.ai` is the interactive AI instance; do not use it from scheduler context
  (the scheduler provides its own AI via `_SchedulerContext`)
- Check required env vars at class init or at the top of `process()`, not inside helper methods
- Add route to `routes.yaml` (or future `plugin.yaml`) — plugin without a route is unreachable

---

## Threading

### Stop signalling

```python
# Correct
self._stop_event = threading.Event()

def stop(self):
    self._stop_event.set()

def _loop(self):
    while not self._stop_event.wait(self._poll_interval):
        self._tick()

# Wrong — boolean flags are not thread-safe
self._running = True
def stop(self): self._running = False
```

### Shared state

Lock every read **and** write of shared mutable state — not just writes:

```python
self._lock = threading.Lock()

def get_value(self):
    with self._lock:          # lock on reads too
        return self._value

def set_value(self, v):
    with self._lock:
        self._value = v
```

### Thread lifecycle

```python
def start(self):
    if self._thread is not None and self._thread.is_alive():
        return                # guard against double-start
    self._stop_event.clear()  # reset so it can run again after a previous stop
    self._thread = threading.Thread(target=self._loop, daemon=True)
    self._thread.start()

def stop(self, timeout=None):
    self._stop_event.set()
    if timeout == 0:
        return                # non-blocking; safe for signal handlers
    if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
        self._thread.join(timeout=timeout)

def close(self, timeout=5.0):
    """Stop thread and release resources (DB connections, file handles, etc.)"""
    self.stop(timeout=timeout)
    # release resources only after thread has exited
    self._db.close()
```

Rules:
- `daemon=True` on all background threads — prevents blocking interpreter exit
- `stop(timeout=0)` in signal handlers — blocking in a signal handler deadlocks
- Separate `stop()` (signals) and `close()` (signals + releases resources)
- Register `close()` with `atexit` for normal exits

---

## SQLite / Database

```python
import sqlite3, threading

class SomeDB:
    def __init__(self, db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def insert(self, data):
        # Validate before persisting — never write invalid data to the DB
        if not isinstance(data.get("name"), str) or not data["name"].strip():
            raise ValueError("name must be a non-empty string")
        with self._lock:
            self._conn.execute("INSERT INTO ...", (...,))
            self._conn.commit()

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
```

Rules:
- `check_same_thread=False` always, paired with an explicit `threading.Lock()`
- `row_factory = sqlite3.Row` so columns are accessible by name
- Validate payload **before** inserting — do not write then validate
- Index every column used in `WHERE` clauses
- `close()` method; register with `atexit`
- `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` — schema init is idempotent

---

## Audio and TTS

### Temp file cleanup

TTS generates temp files. Always clean up — on success AND on failure:

```python
output_files = []
try:
    for chunk in chunks:
        path = os.path.join(self.config.tmp_files_path, f"tts-{uuid.uuid4().hex}.mp3")
        generate_audio(chunk, path)
        output_files.append(path)
    return output_files
except Exception:
    for f in output_files:         # clean up what was already created
        try:
            if os.path.exists(f):
                os.remove(f)
        except OSError:
            pass                   # best-effort: never raise from cleanup
    raise
```

In debug mode, preserve failed files for inspection (`if self.config.debug: skip_delete = True`).

### Audio locking

Playback uses pygame mixer, which is not thread-safe. All playback calls acquire
`self._ai_audio_lock` (a `threading.Lock` on the `SandVoice` instance):

```python
with self._ai_audio_lock:
    success, failed_file, error = audio.play_audio_files(tts_files)
```

### Lazy initialisation

`Audio` objects that are only needed in specific paths (e.g., scheduler voice output)
are initialised on first use, not at startup:

```python
if self._scheduler_audio is None:
    self._scheduler_audio = Audio(self.config)
```

---

## Code Style

| Element | Convention | Example |
|---|---|---|
| Functions / methods | `snake_case` | `calc_next_run`, `load_plugins` |
| Classes | `PascalCase` | `TaskScheduler`, `SchedulerDB` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TTS_MAX_CHARS` |
| Variables | Descriptive | `user_input`, `poll_interval_s` — not `ui`, `p`, `x` |

Function guidelines:
- ≤50 lines per function (guideline, not hard rule — long is a signal to split)
- ≤3 nesting levels — use early returns to flatten:

```python
# Good
def process(user_input, route, s):
    if not user_input:
        return "Please provide input."
    data = fetch(s.config)
    if data is None:
        return "Service unavailable."
    return s.ai.generate_response(user_input, str(data)).content

# Bad — unnecessary nesting
def process(user_input, route, s):
    if user_input:
        data = fetch(s.config)
        if data is not None:
            return s.ai.generate_response(user_input, str(data)).content
        else:
            return "Service unavailable."
    else:
        return "Please provide input."
```

---

## Testing

### Structure

One test file per module: `tests/test_<module_name>.py`.

### Mocking

Never touch real APIs, real audio hardware, or real filesystem in tests.

```python
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.debug = False
    config.api_retry_attempts = 1
    config.gpt_response_model = "gpt-3.5-turbo"
    return config

def test_something(mock_config):
    with patch("common.ai.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.return_value = ...
        ai = AI(mock_config)
        result = ai.generate_response("hello")
        assert result.content == "expected"
```

### Required test cases (minimum per function)

- Happy path
- Empty / `None` / zero input
- Invalid type input
- Expected exception with correct message text

**Config additions additionally:**
- Default loads when key is absent from config file
- Custom value overrides default
- Invalid value raises `ValueError` with descriptive message

**Threading additionally:**
- Start → stop → thread exits
- Double-start does not crash or spawn extra threads
- Stop before start does not crash

**DB operations additionally:**
- Inserted data is retrievable
- Query filters work correctly (status, time comparisons)

### Coverage

```bash
pytest --cov --cov-report=term-missing
```

Target: >80% for every new file. Check before every PR.

---

## Commit Messages

Format: imperative mood, 50 chars or less for the subject line.

```
Add scheduler poll interval configuration
Fix audio lock not acquired on scheduler playback
Update weather plugin to handle missing location
```

**Never mention Claude, AI, or any AI tool in commit messages.**

Good: `Fix thread safety in SchedulerDB`
Bad: `Claude fixed thread safety issues`
