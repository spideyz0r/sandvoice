# Raspberry Pi Compatibility

**Status**: 📋 Planned
**Priority**: 5
**Platforms**: Raspberry Pi 3B (primary target)

---

## Dependencies

- **Plan 52** — openWakeWord engine (replaces Porcupine)
- **Plan 53** — Linux ALSA input device auto-selection
- **Plan 54** — Linux audio output device auto-detection
- **Plan 55** — VAD pre-speech grace period

This plan is documentation-only. All code changes are covered by plans 52–55.
Implement those first, then write the setup guide.

---

## Overview

Document and validate the complete process for deploying SandVoice on a
Raspberry Pi 3B from scratch. The target is a headless Pi running
Raspberry Pi OS Lite 64-bit (Bookworm) with a USB audio device (headset or
separate mic + speaker).

---

## Validated Hardware

Tested and working:

| Component | Model |
|-----------|-------|
| Board | Raspberry Pi 3 Model B (1 GB RAM) |
| OS | Raspberry Pi OS Lite 64-bit (Bookworm / Debian 12) |
| Audio | Razer Barracuda X 2.4 USB wireless headset |
| Storage | 32 GB microSD (Class 10) |

---

## Known Pi-Specific Issues (Resolved by code plans)

| Issue | Resolution |
|-------|-----------|
| Porcupine requires company email + per-device activation | Plan 52: replace with openWakeWord |
| `onnxruntime>=1.21` crashes on Pi 3B (C++ STL assertion) | Plan 52: pin `onnxruntime==1.20.0` |
| `tflite-runtime` fails on Python 3.13 | Plan 52: install openWakeWord with `--no-deps` |
| PyAudio opens virtual ALSA `default` device (amplitude=0) | Plan 53: auto-select `hw:N,M` input |
| `pygame` binds to `bcm2835` onboard device instead of USB headset | Plan 54: auto-detect SDL `AUDIODEV` |
| `pynput` import crashes on headless Linux | Plan 54: lazy import inside `init_recording()` |
| VAD cuts off before user has time to speak | Plan 55: pre-speech grace period |
| Confirmation beep blocks when PyAudio input stream holds hw: device | Plan 52/53: beep played after `_cleanup_pyaudio()` |

---

## System Requirements

**Minimum hardware:**
- Raspberry Pi 3B (1 GB RAM)
- 8 GB+ microSD card
- USB audio device (headset, or mic + speaker)
- Internet connection (OpenAI API calls)

**Recommended:**
- 16 GB+ microSD card (Class 10 or better)
- USB headset with mic (single device, simpler ALSA config)
- Ethernet (more stable than WiFi for API latency)

---

## Acceptance Criteria (Documentation)

### `docs/raspberry-pi-setup.md` must cover:

- [ ] Hardware requirements
- [ ] Flashing Raspberry Pi OS Lite 64-bit with Raspberry Pi Imager
  - Enable SSH, set hostname (`sandvoice.local`), configure WiFi during flash
- [ ] First boot and SSH access
- [ ] System package installation:
  ```bash
  sudo apt-get update && sudo apt-get upgrade -y
  sudo apt-get install -y \
      python3-dev python3-venv python3-pip \
      portaudio19-dev libasound2-dev \
      libopenblas-dev libatlas-base-dev \
      git
  ```
- [ ] Python virtual environment setup
- [ ] Repository clone and dependency installation:
  ```bash
  pip install -r requirements.txt
  # openWakeWord: install without tflite-runtime (not available on Python 3.13)
  pip install openwakeword>=0.6.0 --no-deps
  pip install scipy
  ```
- [ ] First-run model download (`openwakeword.utils.download_models()`)
- [ ] `~/.sandvoice/config.yaml` minimum configuration:
  ```yaml
  openwakeword_model: hey_jarvis
  wake_word_sensitivity: 0.35
  wake_phrase: "hey sandvoice"
  log_level: info
  ```
- [ ] Verifying audio device detection (ALSA device listing)
- [ ] Running SandVoice in wake word mode:
  ```bash
  OPENAI_API_KEY=sk-... python3 sandvoice.py --wake-word
  ```
- [ ] Troubleshooting:
  - No audio output → check `AUDIODEV` env var; try `aplay -l`
  - Wake word not triggering → lower `wake_word_sensitivity` (try `0.25`)
  - VAD cuts off early → `vad_silence_duration: 2.0` in config
  - High CPU → verify `onnxruntime==1.20.0` is installed
  - `tflite-runtime` install error → use `--no-deps` (documented above)
- [ ] Recommended `~/.sandvoice/config.yaml` for Pi (with timezone, TTS voice, etc.)
- [ ] Running as a systemd service (optional section)

---

## Out of Scope

- Raspberry Pi Zero (too slow for real-time inference)
- Raspberry Pi 1/2 (outdated)
- GUI or touch screen
- Custom OS images or automated provisioning
- Hardware HATs (USB audio only)
- Bluetooth audio devices
