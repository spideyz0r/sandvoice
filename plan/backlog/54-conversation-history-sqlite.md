# Plan 54: Conversation History Persistence (SQLite)

## Status
📋 Backlog

## Problem
`AI.conversation_history` is an in-memory list that is lost on every restart. This
means SandVoice has no memory of prior sessions. It also blocks multi-channel sharing:
a Telegram channel running in the same process cannot safely read/write a list owned
by the main thread, and there is no way to reconstruct context after a crash.

## Goal
Persist each conversation turn to SQLite. On startup, load the last N turns so the
session resumes naturally. All channels (wake-word, Telegram) read and write the same
table, giving them a shared, durable conversation history.

## Scope

**In scope:**
- Persist every appended turn to a `conversation_history` SQLite table in the existing
  DB file (shared with `VoiceCache` and `SchedulerDB`).
- Load the last `history_max_entries` turns on startup to seed the in-memory list.
- New config keys: `history_enabled`, `history_max_entries`.

**Out of scope:**
- Cross-process sharing — this plan targets in-process use only. Separate processes
  reading the same SQLite file are covered by Plan 55's Telegram design.
- History search, export, or summarisation — future work.
- Pruning old entries beyond the startup load window — simple mtime/rowid pruning on
  startup is sufficient.

## Design

### Schema
New table in the existing DB file:

```sql
CREATE TABLE IF NOT EXISTS conversation_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    role      TEXT NOT NULL,   -- "user" or "assistant"
    content   TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
```

`role` mirrors the OpenAI message role so the table can be queried directly for
context injection if needed in future.

### VoiceCache / DB changes (`common/db.py` or `common/history.py`)
A new `ConversationHistory` class (same pattern as `VoiceCache`):

```python
class ConversationHistory:
    def append(self, role: str, content: str) -> None: ...
    def load_recent(self, limit: int) -> list[str]: ...
    def close(self) -> None: ...
```

`load_recent` returns the last `limit` entries as plain strings in the existing
`"User: ..."` / `"Assistant: ..."` prefix format so `AI.conversation_history` stays
unchanged.

### AI changes (`common/ai.py`)
`AI.__init__` accepts an optional `history: ConversationHistory | None` parameter.
When present:
- `conversation_history` is seeded from `history.load_recent(config.history_max_entries)`
  on init.
- Every call to `append_to_history(role, content)` also calls `history.append(role, content)`.

`append_to_history` is extracted from the inline list appends scattered across `ai.py`
into a single method, making the persistence hook a one-liner.

### New config keys (`config.yaml` / `configuration.py`)
| Key | Default | Description |
|-----|---------|-------------|
| `history_enabled` | `"disabled"` | Enable SQLite-backed history |
| `history_max_entries` | `20` | Turns loaded on startup and kept in memory |

All follow the 4-step config pattern.

### Startup (`sandvoice.py`)
```python
history = None
if config.history_enabled:
    history = ConversationHistory(config.db_path)
    atexit.register(history.close)
ai = AI(config, openai_client, history=history)
```

## Acceptance Criteria
- [ ] Each user/assistant turn is written to `conversation_history` table after it completes
- [ ] On startup with `history_enabled: enabled`, last `history_max_entries` turns are loaded
- [ ] On startup with `history_enabled: disabled`, behaviour is identical to today
- [ ] DB file and table created automatically on first use
- [ ] `history.close()` registered via `atexit`
- [ ] All new code paths covered by unit tests (>80% coverage)

## Testing Strategy
- Unit-test `ConversationHistory.append` and `load_recent` with a temp DB.
- Unit-test `AI` init with a mock history: assert `conversation_history` seeded correctly.
- Unit-test turn append: assert `history.append` called after each response.
- Unit-test `history_enabled: disabled`: assert no DB writes, no behaviour change.

## Dependencies
- `VoiceCache` / `SchedulerDB` pattern (`common/db.py`) — same WAL SQLite setup.
- Required by Plan 55 (Telegram channel) for cross-channel history sharing.
