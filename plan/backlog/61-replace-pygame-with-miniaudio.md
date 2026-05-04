# Replace pygame with miniaudio for TTS Playback

**Status**: 📋 Backlog
**Priority**: 61
**Platforms**: macOS M1 + Raspberry Pi 3B (Linux).

---

## Dependencies

- Plan 60 (lazy pygame import) is NOT a prerequisite — this plan supersedes it.
  If Plan 61 is implemented, Plan 60 can be dropped.

---

## Overview

SandVoice uses `pygame.mixer` exclusively for audio playback (TTS MP3 files).
pygame is a game framework; its audio subsystem sits on top of SDL2, which on
Linux requires manual ALSA device configuration via environment variables
(`SDL_AUDIODRIVER`, `AUDIODEV`) that must be set before `import pygame` — causing
the import-time side effects documented in Plan 60.

[miniaudio](https://github.com/irmen/pyminiaudio) (`pip install miniaudio`) is a
thin Python wrapper around the miniaudio C library. It handles MP3/WAV/FLAC/OGG
playback natively across platforms, with no SDL layer, no env-var setup, and no
import-time side effects. On Linux it talks directly to ALSA or PulseAudio; on
macOS it uses CoreAudio.

**This plan replaces the entire pygame audio subsystem with miniaudio**, removing
the SDL probe block, ALSA suppression, and env-var ordering constraints entirely.

---

## Why miniaudio

| Concern | pygame | miniaudio |
|---------|--------|-----------|
| SDL env-var setup required on Linux | Yes | No |
| Import-time side effects | Yes | No |
| ALSA noise suppression required | Yes | No |
| Plays MP3 natively | Yes | Yes |
| Supports stop mid-playback | Yes | Yes |
| Blocking playback loop | Yes | Yes |
| ARM / Pi 3B support | Yes | Yes |
| Dependency footprint | Heavy (game framework) | Light (single C lib wrapper) |
| Already used for input | No | No (PyAudio still used for mic) |

---

## Proposed Solution

### New playback helper

```python
import miniaudio

def _play_mp3_blocking(file_path, stop_event=None):
    """Play an MP3 file synchronously; return when done or stop_event is set."""
    stream = miniaudio.stream_file(file_path)
    with miniaudio.PlaybackDevice() as device:
        device.start(stream)
        while device.running:
            if stop_event and stop_event.is_set():
                device.stop()
                break
            time.sleep(0.01)
```

This replaces the `pygame.mixer.music.load / play / get_busy` loop in
`Audio.play_audio_file()`.

### Changes required

- Remove `import pygame` (module level and inside methods).
- Remove SDL probe block (`_detect_sdl_audio_device` / `_suppress_alsa_errors`
  for SDL purposes — ALSA suppression for PyAudio mic use can remain if needed).
- Remove `Audio.stop_playback()` pygame-specific logic; replace with miniaudio
  device stop.
- Remove `Audio.is_playing()` pygame-specific logic; replace with
  `device.running`.
- Remove `Audio.log_mixer_state()` (pygame mixer debug helper; not applicable).
- Replace `play_audio_file()` internals with `_play_mp3_blocking()`.
- `play_audio_queue()` and `play_audio_files()` remain structurally unchanged —
  they call `play_audio_file()` internally.
- Add `miniaudio` to `requirements.txt`.
- Remove `pygame` from `requirements.txt`.

### Config changes

None. The playback API surface (`play_audio_file`, `play_audio_queue`,
`stop_playback`, `is_playing`) is unchanged from the caller's perspective.

---

## Files to Touch

| File | Change |
|------|--------|
| `common/audio.py` | Replace pygame with miniaudio; remove SDL probe and ALSA suppression |
| `requirements.txt` | Remove `pygame`; add `miniaudio` |
| `tests/test_audio_playback.py` | Update mocks from `pygame.mixer` to `miniaudio` |

---

## Out of Scope

- PyAudio (mic recording) is unchanged.
- Barge-in detection is unchanged.
- TTS generation (OpenAI API) is unchanged.
- Any change to the streaming pipeline — `play_audio_queue` contract is preserved.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| miniaudio not packaged for Pi aarch64 | Test `pip install miniaudio` on Pi 3B before implementing; it ships a pure-C extension with no extra system deps beyond libasound |
| Latency difference | miniaudio decodes inline; profile against pygame on Pi if needed |
| Stop-event latency | 10 ms poll loop vs pygame's 100 ms tick — equal or better |

---

## Acceptance Criteria

- [ ] `import common.audio` has no import-time side effects on any platform
- [ ] TTS MP3 playback works on macOS M1
- [ ] TTS MP3 playback works on Raspberry Pi 3B (correct USB output device)
- [ ] `stop_playback()` stops audio within ~50 ms
- [ ] `play_audio_queue()` with `stop_event` interrupts cleanly (barge-in path)
- [ ] `pygame` removed from `requirements.txt`
- [ ] All tests pass with >80% coverage on new playback code
- [ ] No ALSA warnings on stderr on Pi during startup or playback
