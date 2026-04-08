# Plan 39: Blocking Cache Warmup with Timeout and Retries

**Status**: 📋 Backlog
**Priority**: 39
**Platforms**: macOS M1, Raspberry Pi 3B
**Depends on**: Plan 20 (merged)

---

## Problem

`_warmup_cache()` fires all warmup threads as fire-and-forget daemons and returns
immediately. If the user asks about weather or news right after startup, the cache is
not yet populated and they get a live (slow) fetch instead of an instant cached response.

The intended benefit of `cache_auto_refresh` — instant answers — is not realised on cold
starts.

---

## Goal

Block SandVoice startup until the cache warmup completes (or times out), so the first
user query hits cache unless warmup times out. Mirror the Alexa model: the device is
silent for a few seconds on startup, then announces it is ready.

---

## Behaviour

1. All warmup threads are launched as before (in parallel).
2. The main thread waits for all of them to finish, up to `cache_warmup_timeout_s`
   total wall-clock time.
3. Each warmup thread retries the plugin call up to `cache_warmup_retries` times on
   failure, with a short fixed delay between attempts (`cache_warmup_retry_delay_s`).
4. When all threads have finished (or the timeout is reached), startup continues
   normally. Any thread that did not finish in time keeps running in the background and
   will populate the cache when it completes.
5. A startup message is printed while waiting so the user knows why SandVoice is not
   yet ready (e.g. `"Warming up cache (news, weather, hacker-news)..."`).
6. On completion: `"Ready."` (or equivalent in the user's language if feasible).

---

## Configuration

Three new optional config keys, all with sensible defaults:

| Key | Default | Description |
|---|---|---|
| `cache_warmup_timeout_s` | `15` | Max seconds to wait for all warmup threads |
| `cache_warmup_retries` | `3` | Max attempts per plugin before giving up |
| `cache_warmup_retry_delay_s` | `2` | Seconds between retry attempts |

Setting `cache_warmup_timeout_s: 0` disables blocking (reverts to current fire-and-forget
behaviour) for users who prefer the old behaviour.

---

## Implementation

### `sandvoice.py` — `_warmup_cache()`

- Collect `threading.Thread` objects instead of discarding them.
- After launching all threads, `join` each one with a deadline derived from
  `cache_warmup_timeout_s` (track wall-clock elapsed, subtract from remaining budget for
  each successive join).
- Print `"Warming up cache ({plugins})..."` before the join loop.
- Print `"Ready."` after (whether all succeeded or timed out).

### `_run_warmup()` closure

- Wrap the plugin call in a retry loop: attempt up to `cache_warmup_retries` times.
- On exception, sleep `cache_warmup_retry_delay_s` and retry.
- After exhausting retries, log a WARNING.

### `common/configuration.py`

Add and validate the three new keys following the standard four-step config pattern.

---

## What does NOT change

- The scheduler periodic tasks registered by `_warmup_cache()` are unaffected.
- Fire-and-forget behaviour is preserved when `cache_warmup_timeout_s: 0`.
- No change to plugin interfaces or cache key logic.

---

## Tests

- `test_warmup_blocks_until_threads_finish` — threads complete before timeout; main
  continues after all finish.
- `test_warmup_continues_after_timeout` — threads take longer than timeout; main
  continues, threads keep running.
- `test_warmup_retries_on_failure` — plugin raises on first call, succeeds on second;
  assert called twice.
- `test_warmup_gives_up_after_max_retries` — plugin always raises; assert called
  `cache_warmup_retries` times, WARNING logged.
- `test_warmup_timeout_zero_fires_and_forgets` — timeout=0 skips join entirely.
- Config tests: default loads, custom overrides, invalid values fall back to defaults.

---

## Notes

- On Raspberry Pi 3B, network fetches can be slow — 15s default timeout should be
  adequate for 3 parallel fetches with up to 3 retries each.
- The print output uses `print()` directly (user-facing startup UX, not a diagnostic log).
- `cache_warmup_timeout_s` is a wall-clock budget across all plugins combined, not
  per-plugin — simpler config and implementation.
