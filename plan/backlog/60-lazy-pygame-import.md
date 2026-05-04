# Lazy pygame Import — Eliminate Import-Time Audio Side Effects

**Status**: 📋 Backlog
**Priority**: 60
**Platforms**: Linux (Raspberry Pi 3B). Neutral on macOS.

---

## Dependencies

- None — this is a self-contained `audio.py` change.
- Plan 54 (Linux audio output device auto-detection) is already implemented in PR #148 and is the direct motivation for this plan.

---

## Overview

`common/audio.py` currently runs a PyAudio device enumeration block at module
import time in order to set `SDL_AUDIODRIVER` and `AUDIODEV` before
`import pygame` executes (also at module level). This causes three problems:

1. **ALSA warnings on stderr** — `pyaudio.PyAudio()` is constructed before
   `_suppress_alsa_errors()` is ever called, so the noise-suppression hook is not
   yet installed when PortAudio enumerates ALSA devices.

2. **Import-time side effects** — Any code path that imports `common.audio`
   (including CLI mode, tests, and the scheduler thread) triggers a PyAudio
   device enumeration whether or not audio will ever be played.

3. **Fragile ordering constraint** — `_suppress_alsa_errors()` cannot be called
   inside the SDL probe block without triggering a segfault on CI runners (hit in
   PR #148 Round 4), so the warnings cannot be suppressed in the current design.

The root cause: `import pygame` is at module level, forcing the SDL env-var setup
to also be at module level, which forces the PyAudio probe to be at module level.

**This plan breaks that chain by making `import pygame` lazy.**

---

## Proposed Solution

Move `import pygame` from module level into `Audio.initialize_audio()`. The SDL
probe and `_suppress_alsa_errors()` call move there too, running in the correct
order — suppression first, then probe, then pygame import — all inside the method
that actually needs audio.

### Before (simplified)

```python
# Module level — runs at import time
if platform.system() == "linux" ...:
    _pa = pyaudio.PyAudio()          # ← ALSA warnings, no suppression yet
    ...set SDL_AUDIODRIVER / AUDIODEV...
    _pa.terminate()

import pygame                         # ← module level

class Audio:
    def initialize_audio(self):
        _suppress_alsa_errors()       # ← too late; SDL already imported
        self.audio = pyaudio.PyAudio()
```

### After

```python
# No module-level pygame import, no module-level PyAudio probe

class Audio:
    def initialize_audio(self):
        _suppress_alsa_errors()       # 1. suppress ALSA noise first
        _detect_sdl_audio_device()    # 2. probe + set SDL env vars (Linux only)
        import pygame                 # 3. NOW import pygame — env vars already set
        self.audio = pyaudio.PyAudio()
```

`_detect_sdl_audio_device()` is a new module-level helper (no side effects until
called) that encapsulates the existing SDL probe logic. It is idempotent: if
`SDL_AUDIODRIVER` / `AUDIODEV` are already set (user override or already called),
it returns immediately without creating a PyAudio instance.

### Changes required

- Remove module-level `import pygame` from `audio.py`.
- Remove module-level SDL probe block from `audio.py`.
- Extract probe logic into `_detect_sdl_audio_device()` module-level function.
- Call `_suppress_alsa_errors()`, then `_detect_sdl_audio_device()`, then
  `import pygame` inside `Audio.initialize_audio()`.
- All other `pygame.*` references inside `Audio` methods are already inside
  method bodies — they will still work because `initialize_audio()` is always
  called before any playback method.
- Update tests that patch `pygame` at module level to patch at the correct
  location (`common.audio.pygame` will no longer exist; patch the import in
  `initialize_audio` instead, or call `initialize_audio()` with a mocked pygame
  loaded via `sys.modules`).

---

## Files to Touch

| File | Change |
|------|--------|
| `common/audio.py` | Lazy pygame import; extract `_detect_sdl_audio_device()`; call in correct order inside `initialize_audio()` |
| `tests/test_audio_playback.py` | Update pygame patch locations |
| `tests/test_audio_device_detection.py` | Update probe-logic test to call helper directly |

---

## Out of Scope

- Replacing pygame with a different audio library (that is Plan 61).
- Any change to playback logic, queue handling, or barge-in.

---

## Acceptance Criteria

- [ ] No PyAudio device enumeration occurs at `import common.audio` time
- [ ] No `import pygame` occurs at `import common.audio` time
- [ ] `_suppress_alsa_errors()` is called before any PyAudio or pygame initialization
- [ ] SDL env vars are set before `pygame` is imported
- [ ] `AUDIODEV` / `SDL_AUDIODRIVER` not overwritten if already set by user
- [ ] `_detect_sdl_audio_device()` is idempotent (safe to call more than once)
- [ ] Playback behavior unchanged on macOS and Linux
- [ ] All tests pass on macOS M1
- [ ] No ALSA warnings on stderr during import on Raspberry Pi 3B
