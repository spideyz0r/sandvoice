# Plan 55: Telegram Channel

## Status
📋 Backlog

## Problem
SandVoice is only reachable at home, via microphone or terminal. There is no way to
interact with it from a phone or while away. A Telegram channel would make the same
brain — same plugins, same routing, same conversation history — reachable from anywhere
via a messaging app most people already have.

## Goal
Add an always-on Telegram channel that runs as a background thread alongside wake-word
mode. Text messages sent to a private bot are routed through SandVoice exactly like
voice input, and the response is sent back as text. The channel shares conversation
history with the wake-word session so context carries across channels seamlessly.

## Scope

**In scope:**
- Text in / text out only (Phase 1). Voice messages deferred to Phase 2.
- Single-user bot: `telegram_allowed_user_ids` whitelist; all other senders are silently
  ignored.
- Runs as a background thread within the existing `SandVoice` process — same instance,
  same `VoiceCache`, shared `ConversationHistory` (SQLite). `AI` is **not** shared
  directly; the Telegram thread uses a separate `AI` instance seeded from the same DB
  to avoid concurrent mutation of `AI.conversation_history`.
- Works alongside wake-word mode and CLI mode. Enabling Telegram does not affect either.

**Out of scope:**
- Voice message in / TTS audio out — deferred.
- Multi-user support — out of scope.
- Telegram groups or channels — private chat only.

## Design

### Architecture
`TelegramChannel` is a class with a single background thread, matching the `TaskScheduler`
pattern:

```python
class TelegramChannel:
    def __init__(self, config, plugins, cache, history): ...
    def start(self) -> None: ...   # launches daemon thread; creates own AI instance
    def close(self) -> None: ...   # signals thread to stop
```

`TelegramChannel` creates its own `AI` instance (via `AI.from_config(config, history=history)`)
inside the background thread, avoiding shared mutable state with the main thread's `AI`.
Both AI instances persist turns through the same `ConversationHistory` (SQLite with
`threading.Lock`, same as `VoiceCache`).

The thread runs a `polling` loop using `python-telegram-bot` in its own asyncio event
loop (`asyncio.new_event_loop()` + `loop.run_until_complete()`), isolating async code
from the sync main thread.

**Important**: `Application.run_polling()` installs signal handlers by default, which
raises `ValueError: signal only works in main thread` when called from a non-main thread.
The implementation must pass `stop_signals=()` (or `stop_signals=None`) to
`run_polling()` (or use the lower-level `initialize()`/`start()`/`updater.start_polling()`
async lifecycle methods directly) to avoid this.

### Message flow
```
Telegram message arrives
  → check sender user ID against whitelist → ignore if not allowed
  → user_input = message.text
  → route = telegram_ai.define_route(user_input)
  → route_name = route["route"]
  → if route_name in plugins: response = plugins[route_name](user_input, route, ctx)
  → else: response = telegram_ai.generate_response(user_input).content
  → bot.send_message(chat_id, response)
```

`telegram_ai` is the thread's own `AI` instance (created via `AI.from_config(config,
history=history)`). History writes happen inside `AI.append_to_history()` — the same
path as the main thread — so there is a single source of truth and no double-writes.
`ConversationHistory` uses a `threading.Lock` (same pattern as `VoiceCache`) to make
concurrent SQLite writes from both threads safe. No additional turn lock needed at the
`TelegramChannel` level.

### New config keys (`config.yaml` / `configuration.py`)
| Key | Default | Description |
|-----|---------|-------------|
| `telegram_enabled` | `"disabled"` | Enable/disable the Telegram channel |
| `telegram_bot_token` | `""` | Bot token from @BotFather |
| `telegram_allowed_user_ids` | `[]` | List of Telegram user IDs allowed to interact |

All follow the 4-step config pattern. Startup validation: if `telegram_enabled` is
`"enabled"` and `telegram_bot_token` is empty, log a warning and disable the channel.

### Startup (`sandvoice.py`)
```python
telegram = None
if config.telegram_enabled:
    if not config.history_enabled:
        logger.warning(
            "telegram_enabled requires history_enabled; disabling Telegram channel"
        )
    else:
        telegram = TelegramChannel(config, s.plugins, s.cache, history)
        telegram.start()
        atexit.register(telegram.close)
```

### New file: `common/telegram_channel.py`
Contains `TelegramChannel` class only. No plugin logic — it delegates entirely to the
existing `AI` and plugin system.

### Dependency
`python-telegram-bot>=20.0` added to `requirements.txt`.

## Acceptance Criteria
- [ ] Telegram messages from whitelisted users receive a text response
- [ ] Messages from non-whitelisted users are silently ignored
- [ ] Telegram channel shares `ConversationHistory` with the main session
- [ ] wake-word mode and CLI mode are unaffected when `telegram_enabled: disabled`
- [ ] `telegram_enabled: enabled` with empty token logs a warning and does not crash
- [ ] `telegram.close()` registered via `atexit`; thread exits cleanly on shutdown
- [ ] All new code paths covered by unit tests (>80% coverage)

## Testing Strategy
- Unit-test message dispatch: mock `AI.define_route` and plugin, assert response sent.
- Unit-test whitelist: non-allowed user ID → assert no response, no history write.
- Unit-test missing token: assert warning logged, channel disabled gracefully.
- Unit-test history write: assert `ConversationHistory.append` called for user + assistant turns.
- Integration smoke test: real bot token optional, skipped in CI via env var guard.

## Dependencies
- Plan 54 (Conversation History SQLite) — required for shared history.
- `python-telegram-bot>=20.0` — new dependency.

## Phase 2 (future)
- Voice message in: download OGG, transcribe via Whisper, same routing flow.
- TTS response: generate MP3, send as voice message via `bot.send_voice()`.
- Audio cache (Plan 53) applies naturally to the TTS step.
