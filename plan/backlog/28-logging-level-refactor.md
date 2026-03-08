# Logging Level Refactor

**Status**: 📋 Backlog
**Priority**: 28
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Replace the binary `debug: enabled/disabled` config with a standard three-level `log_level: warning|info|debug` key, and remove the ~200 scattered `if self.config.debug: logger.*()` guards from production code. The logging framework is the filter — code should not be.

---

## Problem Statement

Today there are two problems:

1. **No INFO level** — the log level jumps from silent (`debug: disabled`) to extremely noisy (`debug: enabled`). There is no middle ground. `logger.info()` calls are invisible unless debug is on, making Plan 23's timing summary unusable at default settings.

2. **Manual filtering everywhere** — because `setup_error_logging()` only installs a console handler when `debug: enabled`, every logger call in the codebase is wrapped in a guard:

```python
# Current — repeated ~200 times across 8 files
if self.config.debug:
    logger.debug("Scheduler tick: %d due tasks", len(due))
```

This is redundant. The logging framework already skips formatting and emission for levels below the configured threshold. The guards add noise, increase nesting depth, and make it hard to see what's actually being logged.

---

## Proposed Solution

### 1. New config key: `log_level`

```yaml
log_level: warning   # default — quiet, only warnings and errors
log_level: info      # milestones: timing summaries, task completions, startup events
log_level: debug     # everything — for development
```

Migration in `load_config()`: if the old `debug: enabled` is present and `log_level` is absent, treat it as `log_level: debug`. `debug: disabled` becomes `log_level: warning`.

`config.debug` becomes a read-only property so existing behavioral guards (file preservation, stream_print_deltas) keep working without changes:

```python
@property
def debug(self) -> bool:
    return self.log_level == "debug"
```

### 2. Simplified `setup_error_logging()`

Always install the console handler. Level controls what's emitted:

```python
def setup_error_logging(config):
    level = {
        "debug":   logging.DEBUG,
        "info":    logging.INFO,
        "warning": logging.WARNING,
    }.get(getattr(config, "log_level", "warning"), logging.WARNING)

    root = logging.getLogger()
    root.setLevel(level)

    # Find existing console handler or create one (idempotent + level-update safe)
    console = next((h for h in root.handlers if getattr(h, "_sandvoice_console", False)), None)
    if console is None:
        console = logging.StreamHandler()
        console._sandvoice_console = True
        root.addHandler(console)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))

    # File handler (enable_error_logging / error_log_path) — unchanged from today
    _setup_file_handler_if_configured(config, root)
```

Always installs the console handler; re-calling with a different level updates it in place. File logging path left intact. ~60 lines → ~25 lines.

### 3. Remove all `if self.config.debug: logger.*()` guards

Every instance of:

```python
if self.config.debug:
    logger.debug("...")
```

becomes:

```python
logger.debug("...")
```

The framework filters at the configured level. Nothing else changes.

**Keep** guards that control *behaviour*, not logging:

```python
# Keep — this controls TTS file preservation, not logging
if self.config.debug:
    print(f"Preserving TTS file '{failed_file}' for debugging.")

# Keep — this controls print output, not a logger call
if self.config.debug and stream_print_deltas:
    print(delta, end="", flush=True)
```

### 4. Assign correct log levels to existing calls

While removing guards, assign the right level:

| What it logs | Level |
|---|---|
| Internal loop iterations, byte counts, frame indices | `DEBUG` |
| Phase transitions, cache hits, scheduler ticks | `DEBUG` |
| Request timing summary (Plan 23), startup info | `INFO` |
| Config warnings, deprecated keys | `WARNING` |
| Unrecoverable errors | `ERROR` |

---

## Configuration Changes

Add one new key, deprecate `debug:`:

```yaml
log_level: warning    # warning | info | debug  (default: warning)
```

Old `debug: enabled` in existing configs continues to work via migration in `load_config()` with a one-time deprecation warning printed to stdout.

---

## Files to Touch

| File | Change |
|---|---|
| `common/configuration.py` | Add `log_level` key; `config.debug` property; migrate `debug:` |
| `common/error_handling.py` | Simplify `setup_error_logging()` — always install handler |
| `common/wake_word.py` | Remove ~100 `if self.config.debug: logger.*()` guards |
| `common/audio.py` | Remove ~40 guards |
| `common/ai.py` | Remove ~25 guards |
| `plugins/weather.py`, `plugins/news.py`, `plugins/hacker-news.py` | Remove guards |
| `sandvoice.py` | Remove logger guards; keep behavioural guards |
| `tests/test_configuration.py` | Test `log_level` default, custom value, migration from `debug:` |
| `tests/test_error_handling.py` | Test handler always installed; test level mapping |
| `README.md` | Document `log_level`; note `debug: enabled` is deprecated |

---

## Out of Scope

- Structured logging (JSON output) — future enhancement
- Per-module log level overrides — overkill for this project
- File-based logging (`enable_error_logging`) — leave as-is for now

---

## Acceptance Criteria

- [ ] `log_level: warning|info|debug` works in `config.yaml`
- [ ] Default is `warning` — startup is silent unless something is wrong
- [ ] `log_level: info` shows timing summaries and important milestones without debug noise
- [ ] `log_level: debug` shows everything (same as `debug: enabled` today)
- [ ] Old `debug: enabled` in config still works with a deprecation notice
- [ ] `config.debug` property returns `True` when `log_level: debug`
- [ ] All `if self.config.debug: logger.*()` guards removed from production code
- [ ] `setup_error_logging()` is ≤25 lines
- [ ] >80% test coverage on changed code
- [ ] README documents `log_level`
