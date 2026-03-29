# Plan 17: Voice Filler

**Status**: 📋 Backlog
**Priority**: 17
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

When SandVoice routes a request to a plugin (weather, news, web search), there is an audible gap while the plugin fetches data. This plan fills that gap by playing a short pre-generated audio phrase after a configurable delay — "One sec.", "Got it, checking now.", etc. — so the assistant feels responsive even before the answer is ready.

The filler audio is generated at boot time and cached to disk. Playback is instant: no TTS API call on the hot path.

---

## Problem Statement

The earcon (ack sound after recording) signals "I heard you." But for plugin routes that take 1-3 seconds, there is silence until the response is ready. Users familiar with smart speakers expect the assistant to start speaking much sooner.

Streaming (Plan 08) solves this for the default LLM route. Filler solves it for plugin routes where there is nothing to stream yet.

---

## Goals

- Reduce perceived latency on plugin routes in wake-word mode
- Zero API cost on the hot path — audio files pre-generated at boot
- Enabled by default with sensible built-in phrases; no config required
- Barge-in interrupts filler and final response
- Boot fails if filler generation fails (fail-fast — see Warm Phase)

---

## Non-Goals

- Route-specific phrases ("Checking the weather.") — deferred to a follow-up plan
- Model-generated filler — out of scope; pre-generated phrases are safer and faster
- CLI mode — no TTS playback in CLI, filler not applicable
- Non-wake-word voice mode — filler only active in `--wake-word` mode

---

## Design

### Warm Phase (boot sequence)

A `WarmPhase` runs at `SandVoice.__init__` when wake-word mode is active. It blocks startup until all required tasks complete. If a required task fails, startup aborts.

The filler warm task generates any missing phrase audio files in parallel:

```
SandVoice.__init__()
  └── if wake-word mode:
        WarmPhase([WarmTask("voice-filler", filler_cache.warm, required=True)]).run()
        # blocks here; raises RuntimeError on failure
      WakeWordMode starts
```

`WarmPhase` is designed for extensibility — future tasks (cache prefill, connectivity check) slot in alongside filler without touching this logic.

### File storage

```
~/.sandvoice/voice_filler/
  one_sec.mp3
  got_it_checking_now.mp3
  okay_give_me_a_moment.mp3
  let_me_check_that.mp3
  sure_one_moment.mp3
```

Filenames are derived by slugifying the phrase (lowercase, strip punctuation, spaces to underscores). Files are human-readable — users can identify them when browsing.

### Hash validation via SQLite

A `voice_filler_cache` table in the existing SQLite DB (`scheduler_db_path`) stores the authoritative mapping:

```sql
CREATE TABLE IF NOT EXISTS voice_filler_cache (
    filename     TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,   -- sha256(phrase|voice_model|tts_model)[:16]
    created_at   TEXT NOT NULL
)
```

At warm phase, for each phrase:
1. Derive `filename` from phrase slug
2. Compute `content_hash` from `(phrase, voice model, TTS model)`
3. Check: file exists on disk **and** DB row has matching hash → skip (already valid)
4. Otherwise: generate MP3, write to disk, upsert DB row

If voice or TTS model changes in config, the hash changes, triggering regeneration. Old files are orphaned (harmless — each is ~15 KB).

### Playback (hot path)

During `_state_processing`, after the route is known to be a plugin route:
- Plugin callable runs in background thread (already the case via `barge_in.run_with_polling`)
- A timer starts; when `voice_filler_delay_ms` elapses and result is not yet ready:
  - Pick a random phrase from the available filler files
  - Play via `audio.play_audio_file(path)` — instant, no API call
  - Filler plays at most once per request

If filler files are empty (user set `voice_filler_phrases: []`) the timer fires but nothing plays. No special branch needed.

### Files affected

| File | Change |
|---|---|
| `common/warm_phase.py` | New: `WarmTask`, `WarmPhase` |
| `common/voice_filler.py` | New: `VoiceFillerCache` — warm, slugify, hash, DB |
| `common/db.py` | Add `voice_filler_cache` table creation |
| `common/barge_in.py` | Extend `run_with_polling` with optional `lead_delay_s` / `lead_fn` |
| `common/wake_word.py` | Wire filler into plugin route path in `_state_processing` |
| `sandvoice.py` | Call `WarmPhase.run()` before `WakeWordMode` init |
| `common/configuration.py` | Add `voice_filler_delay_ms`, `voice_filler_phrases` config keys |
| `tests/` | `test_warm_phase.py`, `test_voice_filler.py` |

---

## Configuration

Enabled by default. No config change required to use it.

```yaml
# ~/.sandvoice/config.yaml (all optional — these are the defaults)
voice_filler_delay_ms: 800
voice_filler_phrases:
  - "One sec."
  - "Got it, checking now."
  - "Okay, give me a moment."
  - "Let me check that."
  - "Sure, one moment."
```

To disable: set `voice_filler_phrases: []`.

---

## Acceptance Criteria

- [ ] On first boot, filler files are generated and stored in `~/.sandvoice/voice_filler/`
- [ ] On subsequent boots, existing valid files are reused (no API calls)
- [ ] If voice or TTS model changes, affected files are regenerated at next boot
- [ ] If filler generation fails, boot aborts with a clear error
- [ ] Plugin route responses that take longer than `voice_filler_delay_ms` trigger exactly one filler phrase
- [ ] Fast responses (under the delay threshold) play no filler
- [ ] Barge-in interrupts filler playback
- [ ] Empty `voice_filler_phrases` list results in silent operation (no crash, no filler)
- [ ] Works on macOS M1 and Raspberry Pi 3B

---

## Testing

- `test_warm_phase.py`: required task failure raises, optional task failure logs warning; parallel execution
- `test_voice_filler.py`: slug generation, hash computation, cache hit/miss logic, warm with pre-existing files, warm with stale files (hash mismatch)
- `test_wake_word.py` (integration): filler fires when plugin exceeds delay; no filler for fast plugins; no filler for default (streaming) route

---

## Future Work (out of scope)

- **Plan 39**: Route-specific filler phrases ("Checking the weather." for weather route, etc.)
- Boot-complete ready signal (beep or UI indicator) — deferred, existing UI handles state display
