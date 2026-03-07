# Scheduled Tasks File and Lifecycle Management

**Status**: 📋 Backlog
**Priority**: 27
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Move scheduled task definitions out of `config.yaml` into a dedicated `~/.sandvoice/tasks.yaml` file, making that tasks file (referenced from `config.yaml` via `tasks_file_path`) the authoritative source of truth for the DB — tasks removed from the file are automatically removed from the DB on startup.

---

## Problem Statement

Today scheduled tasks live under a `tasks:` key in `config.yaml` alongside ~50 unrelated keys (audio settings, model names, TTS config). Two concrete issues:

1. **No lifecycle management** — removing a task from config leaves it running in SQLite forever. The only fix is a manual `sqlite3` command.
2. **Concern mixing** — "what the bot does on a schedule" is a different concern from "how audio is configured". They don't belong in the same file.

This was discovered in practice: the `scheduler-test` task kept firing after being removed from config and required a manual DB delete to stop it.

---

## Proposed Solution

### 1. Dedicated `~/.sandvoice/tasks.yaml`

```yaml
# ~/.sandvoice/tasks.yaml

- name: weather-refresh
  schedule_type: interval
  schedule_value: "300"
  action_type: plugin
  action_payload:
    plugin: weather
    location: Stoney Creek, Ontario, Canada
    unit: metric
    refresh_only: true

- name: morning-news
  schedule_type: cron
  schedule_value: "0 8 * * *"
  action_type: speak
  action_payload:
    text: "Good morning. Your news briefing is ready."
```

- Loaded on startup by `Config` class
- If the file does not exist, no tasks are registered (no tasks will be registered)
- Path configurable via `tasks_file_path` in `config.yaml` (default: `~/.sandvoice/tasks.yaml`)

### 2. Config-as-source-of-truth sync on startup

On startup, after loading `tasks.yaml`, the scheduler syncs the DB:

```
tasks_in_file = {t.name for t in loaded_tasks}
tasks_in_db   = {t.name for t in db.get_all_tasks()}

to_register = tasks_in_file - tasks_in_db       # new → insert
to_remove   = tasks_in_db - tasks_in_file        # removed → delete
to_skip     = tasks_in_file & tasks_in_db        # existing → leave alone
```

Tasks removed from `tasks.yaml` are **deleted from the DB** on next startup. No manual sqlite3 needed.

---

## Configuration Changes

Add one new key to `config.yaml`:

```yaml
tasks_file_path: ~/.sandvoice/tasks.yaml   # default
```

Follow the 4-step config pattern from `docs/PATTERNS.md`:
1. Add to `defaults` dict
2. Add property in `load_config()` with `os.path.expanduser()`
3. Add validation (path must be a string)
4. Document in README

---

## Files to Touch

| File | Change |
|---|---|
| `common/configuration.py` | Add `tasks_file_path` config key; load and parse `tasks.yaml` |
| `common/scheduler.py` | Add `sync_tasks(loaded_tasks)` method: register new, delete removed |
| `sandvoice.py` | Pass loaded tasks to `scheduler.sync_tasks()` on startup |
| `tests/test_configuration.py` | Test `tasks_file_path` default and custom value |
| `tests/test_scheduler.py` | Test `sync_tasks`: new tasks registered, removed tasks deleted, existing tasks untouched |
| `README.md` | Document `tasks_file_path` and `tasks.yaml` format |

---

---

## Out of Scope

- Hot-reload (detecting changes to `tasks.yaml` without restart) — future enhancement
- Voice or CLI commands to add/remove tasks at runtime — future enhancement
- Task history or run logs — future enhancement

---

## Acceptance Criteria

- [ ] Tasks defined in `~/.sandvoice/tasks.yaml` are registered on startup
- [ ] Tasks removed from `tasks.yaml` are deleted from DB on next startup
- [ ] Tasks in DB but not in file are cleaned up automatically
- [ ] `tasks_file_path` is configurable
- [ ] If `tasks.yaml` does not exist, startup proceeds normally with no tasks
- [ ] >80% test coverage on new code
- [ ] README documents the new file format and migration path
