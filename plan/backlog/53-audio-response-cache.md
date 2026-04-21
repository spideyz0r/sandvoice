# Plan 53: Audio Response Cache

## Status
📋 Backlog

## Problem
Every text cache hit (weather, greeting) still makes a full TTS API call. The text is
identical across hits within the same TTL window, so the resulting audio is also identical.
There is no reason to call TTS more than once per unique (text, voice, model) combination.

## Goal
Cache the generated MP3 alongside the text response. On a cache hit, if a valid audio
file already exists, play it directly and skip the TTS call entirely. Audio files are
stored in a configurable directory and keyed by a hash of (text, voice, tts_model).

## Scope

**In scope:**
- Non-streaming playback path only (CLI mode and wake-word mode when `stream_responses` is
  disabled). Streaming TTS pipelines LLM deltas directly into audio; that path is excluded.
- Plugins that already use `VoiceCache` for text: `weather` and `greeting` today; any
  future plugin that opts in.

**Out of scope:**
- Streaming TTS path (`stream_tts`) — deferred.
- Conversational (non-cached) responses — no value; those are unique per request.

## Design

### Hash function
A SHA-256 digest of a canonical JSON serialization of `(text, voice, tts_model, tts_provider)`
uniquely identifies an audio file. Including the provider prevents cross-provider collisions
when the same `(voice, model)` strings are used with different TTS backends. If any of the
four inputs change, the hash changes and the old file is ignored.

```python
import hashlib
import json

def _audio_hash(text, voice, tts_model, tts_provider):
    payload = json.dumps(
        {"text": text, "voice": voice, "tts_model": tts_model, "tts_provider": tts_provider},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

The audio file is stored as `<audio_cache_dir>/<hash>.mp3`. The filename is the hash,
so no separate index is needed to track freshness. Writers must generate the MP3 at a
temporary path in the same directory and atomically rename it into place once complete.
Readers should treat a cached file as a hit only if the expected file exists and passes
a minimal validation check (non-zero size and/or a decodable MP3 header).

### VoiceCache changes (`common/cache.py`)
Add an optional `audio_hash` column to the `voice_cache` SQLite table:

```sql
-- Only run if the column does not already exist (idempotent migration):
-- check via PRAGMA table_info(voice_cache) and skip if audio_hash is present.
ALTER TABLE voice_cache ADD COLUMN audio_hash TEXT;
```

`VoiceCache.set()` accepts an optional `audio_hash` argument and persists it alongside
the text value. `VoiceCache.get()` returns the `audio_hash` field in `CacheEntry` so
callers can verify the file.

### Playback path (`common/audio.py` or call site)
After a text cache hit:

1. Retrieve `entry.audio_hash` from the cache.
2. Compute expected hash: `_audio_hash(entry.value, config.bot_voice_model, config.text_to_speech_model, config.tts_provider)`.
3. Build path: `os.path.join(config.audio_cache_dir, f"{expected_hash}.mp3")`.
4. If the file exists and `entry.audio_hash == expected_hash`: play the file, skip TTS.
5. Otherwise: call TTS normally, save the resulting MP3 to the path, call `cache.set()`
   again with the new `audio_hash`.

Hash mismatch means the cached text was refreshed with new content since the audio was
generated. The old file is not deleted — it will be orphaned until a cleanup sweep
(see below). The new audio replaces it under a new hash filename.

### New config keys (`config.yaml` / `configuration.py`)
| Key | Default | Description |
|-----|---------|-------------|
| `audio_cache_enabled` | `"disabled"` | Enable/disable audio caching (`"enabled"`/`"disabled"`) |
| `audio_cache_dir` | `~/.sandvoice/audio_cache` | Directory for cached MP3 files |
| `audio_cache_max_files` | `50` | Maximum number of files to keep; oldest by mtime pruned on startup |

All follow the 4-step config pattern (defaults dict → `load_config()` → validation →
documented in `config.yaml`).

`audio_cache_dir` is created on startup if it does not exist (same pattern as the DB
directory).

### Orphan cleanup
On startup (when `audio_cache_enabled` is `"enabled"`), prune files in `audio_cache_dir`
by mtime until the count is ≤ `audio_cache_max_files`. This is the only cleanup
mechanism — no background thread, no per-file expiry.

## Acceptance Criteria
- [ ] On a text cache hit with a valid audio file: TTS API is not called, file is played
- [ ] On a text cache hit with no audio file: TTS is called, result saved, hash stored
- [ ] On a text cache hit where `audio_hash` does not match (text was refreshed): TTS
      called, new file saved under new hash, old file left as orphan
- [ ] `audio_cache_dir` is created on first use if missing
- [ ] Orphan files pruned to `audio_cache_max_files` on startup
- [ ] Audio caching is completely disabled when `audio_cache_enabled: disabled`
- [ ] Streaming TTS path is unaffected
- [ ] All new code paths covered by unit tests (>80% coverage)

## Testing Strategy
- Unit-test `_audio_hash()` for determinism, stability, and input separation (same
  text+voice+model+provider → same hash; different text/voice/model/provider → different hash).
- Unit-test cache hit with valid file: mock file existence, assert TTS not called.
- Unit-test cache hit with missing file: assert TTS called, file written, hash stored.
- Unit-test hash mismatch: assert TTS called even though a file exists at a different path.
- Unit-test orphan cleanup: assert oldest files removed when count exceeds limit.

## Dependencies
- `VoiceCache` (Plan 20) — text cache must be enabled for audio cache to apply.
- `audio_cache_enabled` is independent of `cache_enabled`; both must be on for audio
  caching to activate.
