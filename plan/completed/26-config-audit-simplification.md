# Configuration Audit and Simplification

**Status**: 📋 Backlog
**Priority**: 26
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

The config file has grown to ~50 keys. Many of them are internal implementation knobs that typical users will never touch, a few are already deprecated, and some expose technical audio/threading details that have perfectly good hardcoded defaults. This plan audits every key, removes or internalizes the ones that don't belong in user config, and leaves a leaner surface that's easier to document and maintain.

**Read before starting:**
- `common/configuration.py` (entire file — this is the source of truth for all keys)
- `~/.sandvoice/config.yaml` (the user's actual config — shows what's actively used in practice)
- `docs/PATTERNS.md`
- Grep the codebase for each key proposed for removal to confirm it's not referenced outside `configuration.py`

---

## Problem Statement

Current config has three kinds of clutter:

1. **Already deprecated keys** still parsed and handled — they just generate a warning.
2. **Internal implementation knobs** exposed as config: thread timeouts, queue sizes, audio sample rates, beep frequencies. These are not user decisions — they're engineering tradeoffs with good fixed defaults.
3. **Redundant toggles** where the underlying feature they guard is also controlled by a higher-level toggle (e.g., earcon freq/duration only matter if earcon is enabled — the user doesn't need to tune Hz values).

The result: a config file that intimidates new users, generates review feedback when any key is added, and requires validators, normalizers, and type coercions for values no one should be setting.

---

## Goals

- Reduce user-facing config surface by ~30-40%
- All removed keys get hardcoded defaults equal to the current default values (no behavior change for users who don't set them)
- Keys that users have set in their YAML are silently ignored after removal (the `{**defaults, **data}` merge means unknown keys do no harm)
- `validate_config()` shrinks in proportion — remove validation for removed keys
- Existing tests pass; update any tests that reference removed keys

## Non-Goals

- No changes to how any retained key works
- No new features
- No changes to wake_word.py or other consumers beyond removing the `.config.X` attribute accesses for removed keys

---

## Proposed Removals

For each key below: remove from `self.defaults`, remove from `load_config()`, remove from `validate_config()`, hardcode the value wherever it was used.

### Category A: Already deprecated — remove completely

| Key | Current default | Action |
|-----|----------------|--------|
| `linux_warnings` | `"enabled"` | Already prints a deprecation warning in `load_config()`. Remove the key, the warning, and the `self.linux_warnings` attribute. Grep for uses across the codebase and remove. |
| `enable_error_logging` | `"disabled"` | Audit: grep `common/`, `plugins/`, `sandvoice.py` for `enable_error_logging`. If only referenced in `configuration.py`, remove entirely. |
| `error_log_path` | `~/.sandvoice/error.log` | Same audit — remove if unused outside `configuration.py`. |
| `fallback_to_text_on_audio_error` | `"enabled"` | Audit uses. If no code branches on this flag, remove and leave the fallback behavior permanently on (which is the current default). |

### Category B: Internal streaming knobs — hardcode the defaults

These are thread timeout and queue tuning parameters. Users shouldn't be setting them; they exist for debugging edge cases. Hardcode the current defaults directly in the code that uses them.

| Key | Current default | Hardcode as |
|-----|----------------|-------------|
| `stream_tts_buffer_chunks` | `2` | `2` |
| `stream_tts_first_chunk_target_s` | `6` | `6` |
| `stream_tts_tts_join_timeout_s` | `30` | `30` |
| `stream_tts_player_join_timeout_s` | `60` | `60` |

After removal: replace all `getattr(self.config, "stream_tts_buffer_chunks", 2)` style calls in `common/wake_word.py` with the literal value. Remove the keys from `configuration.py` defaults, `load_config()`, `validate_config()`, and the float normalization section.

### Category C: Audio feedback fine-tuning — keep the on/off toggle, remove Hz/duration

Users care whether the confirmation beep plays. They do not need to tune its frequency in Hz or duration in seconds.

| Key | Action |
|-----|--------|
| `wake_confirmation_beep_freq` | Remove. Hardcode `800` wherever consumed (likely `common/beep_generator.py`). |
| `wake_confirmation_beep_duration` | Remove. Hardcode `0.1`. |
| `voice_ack_earcon_freq` | Remove. Hardcode `600`. |
| `voice_ack_earcon_duration` | Remove. Hardcode `0.06`. |

Keep: `wake_confirmation_beep` (on/off), `voice_ack_earcon` (on/off).

### Category D: VAD internals — remove engineering knobs

Users may want to tune how long silence must last before recording stops (`vad_silence_duration`) and the hard timeout (`vad_timeout`). They should not need to know about webrtcvad's frame duration or aggressiveness level.

| Key | Action |
|-----|--------|
| `vad_aggressiveness` | Remove. Hardcode `3` (current default, highest sensitivity). |
| `vad_frame_duration` | Remove. Hardcode `30` ms (current default). |

Keep: `vad_silence_duration`, `vad_timeout`, `vad_enabled`.

### Category E: Debug-only flag that duplicates `debug`

| Key | Action |
|-----|--------|
| `stream_print_deltas` | Remove. Gate the behavior on `self.config.debug` instead. When `debug: enabled`, streaming deltas print to stdout automatically. No need for a separate toggle. |

---

## Keys to Keep (do not change)

Everything else stays as-is:

**Identity / locale**: `botname`, `timezone`, `location`, `unit`, `language`, `verbosity`

**Core toggles**: `debug`, `bot_voice`, `barge_in`, `push_to_talk`, `cli_input`

**Streaming toggles**: `stream_responses`, `stream_tts`, `stream_tts_boundary`

**Models**: `gpt_summary_model`, `gpt_route_model`, `gpt_response_model`, `speech_to_text_model`, `text_to_speech_model`, `bot_voice_model`, `speech_to_text_translate_model`

**STT behavior**: `speech_to_text_task`, `speech_to_text_language`, `speech_to_text_translate_provider`

**News/search plugins**: `rss_news`, `rss_news_max_items`, `summary_words`, `search_sources`

**Wake word**: `porcupine_access_key`, `wake_phrase`, `porcupine_keyword_paths`, `wake_word_sensitivity`, `wake_confirmation_beep`

**VAD**: `vad_enabled`, `vad_silence_duration`, `vad_timeout`

**Audio feedback**: `voice_ack_earcon`

**Audio / system**: `channels`, `bitrate`, `rate`, `chunk`, `tmp_files_path`, `api_timeout`, `api_retry_attempts`

**Scheduler**: `scheduler_enabled`, `scheduler_poll_interval`, `scheduler_db_path`, `tasks`

**Cache**: `cache_enabled`, `cache_weather_ttl_s`, `cache_weather_max_stale_s`

---

## Notes on Backward Compatibility

- YAML files with removed keys will continue to load without errors — unknown keys are silently ignored by the `{**defaults, **data}` merge.
- Users who have set any removed key in their config.yaml will see no behavior change, since the hardcoded value matches the old default.
- For keys that some users might have actively tuned (`stream_tts_buffer_chunks`, `vad_aggressiveness`), add a one-time startup warning: check if the key exists in the loaded YAML dict and print a single deprecation line so users know they can clean up their config.

---

## Implementation Steps

1. **Audit each Category A key** — grep `common/`, `plugins/`, `sandvoice.py` for the attribute name. Confirm it's only used in `configuration.py` or has trivially removable references.
2. **Remove keys** from `defaults`, `load_config()`, and `validate_config()` one category at a time.
3. **Hardcode values** at the call sites in `common/wake_word.py` and any other consumer.
4. **Update tests** — remove or update any test that sets or asserts a removed config key.
5. **Run `pytest --cov`** — coverage must stay >= 80%.
6. **Update `README.md`** if it documents any removed keys.

---

## Acceptance Criteria

- [ ] `linux_warnings`, `enable_error_logging`, `error_log_path`, `fallback_to_text_on_audio_error` removed (after auditing each is safe to remove)
- [ ] `stream_tts_buffer_chunks`, `stream_tts_first_chunk_target_s`, `stream_tts_tts_join_timeout_s`, `stream_tts_player_join_timeout_s` removed; values hardcoded at use sites
- [ ] `wake_confirmation_beep_freq`, `wake_confirmation_beep_duration`, `voice_ack_earcon_freq`, `voice_ack_earcon_duration` removed; values hardcoded
- [ ] `vad_aggressiveness`, `vad_frame_duration` removed; values hardcoded
- [ ] `stream_print_deltas` removed; behavior gated on `debug`
- [ ] `validate_config()` updated — no validation for removed keys
- [ ] All existing tests pass
- [ ] Coverage >= 80%
- [ ] A YAML config containing removed keys still loads without errors
- [ ] No behavior change for any setting that was at its default value
