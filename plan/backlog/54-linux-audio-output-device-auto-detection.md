# Linux Audio Output Device Auto-Detection

**Status**: 📋 Backlog
**Priority**: 54
**Platforms**: Raspberry Pi 3B (Linux). No change on macOS.

---

## Dependencies

- None — this is an `audio.py` change independent of the wake word engine.

---

## Overview

On Raspberry Pi, SDL2 (used by `pygame.mixer` for TTS playback) defaults to the
first ALSA device it finds. On a Pi 3B this is typically `bcm2835` — the onboard
HDMI/headphone output — even when a USB audio headset is connected and set as
the ALSA system default. The result: TTS audio plays on the wrong device (or not
at all if the onboard device has no speaker connected), while the user hears
nothing through their USB headset.

This plan adds startup code in `audio.py` that detects the correct ALSA output
device and sets the `SDL_AUDIODRIVER` and `AUDIODEV` environment variables
**before** `pygame` is imported, so pygame picks up the right device
automatically on every platform.

Also included: move `from pynput import keyboard` from module-level to inside
`Audio.init_recording()`. The module-level import crashes on headless Linux
(`ImportError: this platform is not supported`) even when `init_recording` is
never called.

---

## Problem Statement

1. **Wrong SDL output device**: `pygame.mixer.init()` binds to `bcm2835` on Pi
   instead of the USB headset. TTS responses are inaudible.

2. **pynput crashes on import**: `from pynput import keyboard` at the top of
   `audio.py` raises `ImportError` on headless Linux because pynput requires a
   display server (X11/Wayland). SandVoice in `--wake-word` mode never calls
   `init_recording()`, so the import is unconditionally executed but never needed.

---

## Proposed Solution

### `common/audio.py` — SDL output device auto-detection

At module load time, before `import pygame`:

```python
if platform.system().lower() == "linux":
    if "SDL_AUDIODRIVER" not in os.environ:
        os.environ["SDL_AUDIODRIVER"] = "alsa"

    if "AUDIODEV" not in os.environ:
        try:
            import re as _re, pyaudio as _pa
            _audio = _pa.PyAudio()
            try:
                _audiodev = None
                _fallback = None
                for _i in range(_audio.get_device_count()):
                    _dev = _audio.get_device_info_by_index(_i)
                    _m = _re.search(r'hw:(\d+),(\d+)', _dev.get("name", ""))
                    if not _m:
                        continue
                    _plug = f"plughw:{_m.group(1)},{_m.group(2)}"
                    # Prefer a device with both input AND output (USB headset).
                    if _dev.get("maxOutputChannels", 0) > 0 and _dev.get("maxInputChannels", 0) > 0:
                        _audiodev = _plug
                        break
                    if _fallback is None and _dev.get("maxOutputChannels", 0) > 0:
                        _fallback = _plug
                os.environ["AUDIODEV"] = _audiodev or _fallback or "default"
            finally:
                _audio.terminate()
        except Exception:
            os.environ["AUDIODEV"] = "default"

import pygame
```

Why `plughw:N,M` (not `hw:N,M`)? `plughw` goes through ALSA's plug layer which
handles sample rate conversion automatically; `hw` requires exact format match
and will fail if pygame requests a rate the device doesn't natively support.

Why prefer a device with both in+out channels? On a USB headset (e.g. Razer
Barracuda X) the same `hw:2,0` device handles mic and speakers. Preferring
combined devices avoids accidentally picking an output-only onboard device as
the fallback when a headset is present.

### `common/audio.py` — lazy pynput import

```python
# Before (top of file):
from pynput import keyboard   # ← crashes on headless Linux

# After (inside init_recording only):
def init_recording(self):
    from pynput import keyboard  # imported only when actually needed
    listener = keyboard.Listener(on_press=self.on_press)
    ...
```

---

## Files to Touch

| File | Change |
|------|--------|
| `common/audio.py` | SDL AUDIODEV auto-detection block; lazy pynput import |
| `tests/test_audio_playback.py` | Test `SDL_AUDIODRIVER`/`AUDIODEV` env vars set correctly on Linux before pygame import |
| `tests/test_audio_device_detection.py` | Test device scanning logic, fallback behaviour, and lazy `pynput` import path |

---

## Out of Scope

- Input device selection for PyAudio (that is Plan 53)
- ALSA configuration files (`~/.asoundrc`, `/etc/asound.conf`)
- Windows audio support

---

## Acceptance Criteria

- [ ] `SDL_AUDIODRIVER` set to `alsa` on Linux if not already set by the user
- [ ] `AUDIODEV` set to `plughw:N,M` on Linux if not already set by the user
- [ ] Scans PyAudio devices for `hw:N,M` names; prefers device with both input and output channels (USB headset)
- [ ] Falls back to first output-only `hw:N,M` device and sets `AUDIODEV=plughw:N,M`, then `"default"`
- [ ] `SDL_AUDIODRIVER` and `AUDIODEV` checked and set independently — a user-set `AUDIODEV` is not overwritten
- [ ] `from pynput import keyboard` moved inside `init_recording()`
- [ ] No crash on headless Linux when `init_recording()` is never called
- [ ] macOS behavior unchanged
- [ ] Tests pass on macOS M1 and Raspberry Pi 3B
