# Task Scheduler

**Status**: 📋 Backlog
**Priority**: 21
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

A lightweight in-process task scheduler that allows the main app and plugins to register scheduled work — recurring (cron or interval) or one-shot (once).

Modeled after nanoclaw's task-scheduler approach: a simple SQLite-backed poll loop with three schedule types. Small, auditable, no heavy dependencies.

This plan is a **prerequisite for Plan 20** (background cache periodic refresh) and the future **Timers & Reminders** feature.

---

## Problem Statement

Current behavior:
- No way for plugins or the app to schedule recurring or delayed work.
- Plan 20's background refresh needs a scheduler to function.
- User requests like "remind me in 10 minutes" have no mechanism to execute.

Desired behavior:
- App and plugins can register tasks with cron expressions, fixed intervals, or one-time timestamps.
- The scheduler runs tasks in the background, producing voice output or triggering plugin calls.
- Tasks persist across restarts via SQLite.

---

## Goals

1. Three schedule types: `cron`, `interval`, `once`
2. Tasks survive restarts (SQLite-backed)
3. Two action types: `plugin` (invoke plugin) and `speak` (TTS a fixed message)
4. Clean shutdown — no tasks run after stop
5. Configurable poll interval (default 30s)
6. Pause/resume/cancel tasks programmatically

---

## Non-Goals

- No user-facing voice commands for creating tasks (that's Timers & Reminders, a future plan)
- No complex task chaining or dependencies
- No distributed execution or multi-process coordination

---

## Design

### Schedule Types

| Type | `schedule_value` example | Behavior |
|------|--------------------------|----------|
| `cron` | `"0 9 * * 1-5"` | Runs on matching times (cron expression) |
| `interval` | `"300"` (seconds) | Runs every N seconds |
| `once` | `"2026-03-01T09:00:00"` | Runs once at given ISO timestamp, then completes |

### Action Types

| Type | Payload | Behavior |
|------|---------|----------|
| `plugin` | `{"plugin": "weather", "query": "weather update", "refresh_only": true}` | Invokes plugin, optionally suppresses voice output |
| `speak` | `{"text": "Time to check the oven"}` | Speaks fixed text via TTS |

`refresh_only: true` is used by cache-warming tasks (Plan 20) to update the cache without speaking. Tasks without `refresh_only` speak their result normally.

### Database Schema

One new table in the existing SQLite database (same DB used by Plan 20):

```sql
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    schedule_type  TEXT NOT NULL CHECK(schedule_type IN ('cron', 'interval', 'once')),
    schedule_value TEXT NOT NULL,
    action_type    TEXT NOT NULL CHECK(action_type IN ('plugin', 'speak')),
    action_payload TEXT NOT NULL,   -- JSON
    next_run    TEXT NOT NULL,      -- ISO 8601 UTC
    last_run    TEXT,
    last_result TEXT,
    status      TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active', 'paused', 'completed')),
    created_at  TEXT NOT NULL
);
```

### Scheduler API (conceptual)

```python
# Registration (used by app and plugins at startup or on demand)
scheduler.add_task(
    name="weather-cache-refresh",
    schedule_type="interval",
    schedule_value="300",
    action_type="plugin",
    action_payload={"plugin": "weather", "refresh_only": True}
)

scheduler.add_task(
    name="oven-reminder",
    schedule_type="once",
    schedule_value="2026-03-01T14:30:00",
    action_type="speak",
    action_payload={"text": "Time to check the oven"}
)

# Lifecycle
scheduler.pause_task(task_id)
scheduler.resume_task(task_id)
scheduler.cancel_task(task_id)
scheduler.stop()  # clean shutdown
```

### Poll Loop

```python
# In common/scheduler.py
import threading, time

class TaskScheduler:
    def __init__(self, db, poll_interval_s=30):
        self._db = db
        self._poll_interval = poll_interval_s
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _loop(self):
        while not self._stop_event.wait(self._poll_interval):
            self._tick()

    def _tick(self):
        due = self._db.get_due_tasks()  # WHERE next_run <= now AND status = 'active'
        for task in due:
            self._run(task)

    def _run(self, task):
        try:
            result = self._dispatch(task)
        except Exception as e:
            result = str(e)
        self._db.update_after_run(task, result)

    def _dispatch(self, task):
        payload = json.loads(task.action_payload)
        if task.action_type == 'speak':
            tts_and_play(payload['text'])
        elif task.action_type == 'plugin':
            invoke_plugin(payload['plugin'], payload.get('query', ''),
                         refresh_only=payload.get('refresh_only', False))
```

### Next-Run Calculation

```python
def calc_next_run(task) -> datetime | None:
    now = datetime.now(timezone.utc)
    if task.schedule_type == 'interval':
        return now + timedelta(seconds=int(task.schedule_value))
    elif task.schedule_type == 'cron':
        from croniter import croniter
        return croniter(task.schedule_value, now).get_next(datetime)
    elif task.schedule_type == 'once':
        return None  # task will be marked completed
```

---

## Implementation Phases

### Phase 1: Core Scheduler
- `common/scheduler.py` — `TaskScheduler` class
- `common/db.py` — add `scheduled_tasks` table + CRUD
- Poll loop with `threading.Event` for clean shutdown
- `calc_next_run()` for all three schedule types
- `croniter` added to `requirements.txt`

### Phase 2: Action Dispatch
- `plugin` action: call existing plugin dispatch logic, suppress TTS if `refresh_only`
- `speak` action: call TTS + audio playback pipeline

### Phase 3: Integration
- Scheduler starts in `sandvoice.py` alongside main loop
- Clean shutdown on SIGINT/SIGTERM
- Plan 20 registers its cache-refresh tasks via scheduler on startup

### Phase 4: Tests
- Unit: `calc_next_run()` for all three types
- Unit: due tasks query (mock DB, frozen time)
- Unit: once task transitions to `completed`
- Integration: scheduler tick dispatches plugin action

---

## Configuration

```yaml
scheduler_enabled: true
scheduler_poll_interval: 30   # seconds
```

Default: enabled with 30s poll interval.

---

## Dependencies

- `croniter` — cron expression parsing (pure Python, lightweight, Pi-friendly)
- SQLite — already used by Plan 20

---

## Acceptance Criteria

- [ ] `cron`, `interval`, and `once` tasks execute at correct times
- [ ] `once` tasks transition to `completed` after executing
- [ ] Tasks survive a restart (read from DB on startup)
- [ ] `refresh_only` plugin tasks do not produce voice output
- [ ] `speak` tasks produce voice output via existing TTS pipeline
- [ ] Scheduler shuts down cleanly on SIGINT with no tasks mid-flight

---

## Effort: Small-Medium

---

## Dependencies

- Plan 20 is the first consumer (background cache refresh)
- Timers & Reminders (future plan) is the second consumer

## Relationship

- Prerequisite for: Plan 20 (periodic cache refresh), future Timers & Reminders
- Builds on: existing SQLite infrastructure (Plan 20), existing TTS pipeline
