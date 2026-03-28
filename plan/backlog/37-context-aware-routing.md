# Plan 37: Context-Aware Routing

## Problem

The route classifier (`AI.define_route`) is stateless — it receives only the current
utterance with no knowledge of the preceding conversation. Follow-up clarifications are
therefore misrouted. Example from production:

> **Turn 1** — "When is the first game of the World Cup?" → `realtime_websearch` ✅
> **Turn 2** — "Of course, I'm talking about the Soccer World Cup, the FIFA." → `news` ❌ (should be `realtime_websearch`)

Without context, turn 2 reads as a news topic rather than a clarification of turn 1.

## Goal

Pass the last N conversation turns to `define_route` so the routing LLM can resolve
follow-up utterances correctly, without breaking stateless callers (scheduler, greeting
plugin) that have no history.

## Approach

### 1. Add `history` parameter to `define_route`

```python
def define_route(self, user_input, model=None, extra_routes=None, history=None):
```

- `history`: optional list of recent conversation strings (same format as
  `self.conversation_history`, e.g. `["User: ...", "Sandbot: ..."]`). When provided,
  prepended as `{"role": "user", ...}` messages before the current input.
- Default: `None` (stateless, current behaviour preserved for all existing callers).

### 2. Wake-word and CLI callers pass history

In `wake_word.py` and `sandvoice.py`, pass the last 4 entries from
`self.ai.conversation_history` (2 full turns) to `define_route`:

```python
route = self.ai.define_route(
    user_input,
    extra_routes=...,
    history=self.ai.conversation_history[-4:],
)
```

Capping at 4 entries keeps the routing prompt small and avoids sending stale context
from much earlier in the session.

### 3. Scheduler and greeting plugin stay stateless

`_scheduler_route_message` and `greeting.py` call `define_route` without `history`
(default `None`) — their routing is already correct because they always send
self-contained queries.

### 4. Update `_SchedulerContext.route_message` — no change needed

The scheduler uses its own dedicated AI instance with no conversation history, so
passing `history=None` is correct.

## Acceptance Criteria

- [ ] Follow-up clarification in wake-word mode routes to the same plugin as the
      preceding turn when the clarification alone is ambiguous
- [ ] First-turn routing behaviour is unchanged
- [ ] Stateless callers (scheduler, greeting plugin) are unaffected
- [ ] `define_route` unit tests cover both `history=None` and `history=[...]` cases
- [ ] No increase in routing latency beyond the extra tokens sent

## Notes

- Keep history depth configurable if it proves useful: `route_history_depth: 4` in
  `config.yaml` (default 4, can be 0 to disable).
- History entries are plain strings; convert to `{"role": "user", "content": msg}`
  inside `define_route` — callers don't need to know the message format.
