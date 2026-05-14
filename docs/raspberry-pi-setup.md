# SandVoice on Raspberry Pi

This guide covers installing and running SandVoice on a Raspberry Pi 3B. It assumes your Pi is already running Raspberry Pi OS Lite 64-bit, is accessible over SSH, and has internet access.

---

## Tested Hardware

| Component | Model |
|-----------|-------|
| Board | Raspberry Pi 3 Model B (1 GB RAM) |
| OS | Raspberry Pi OS Lite 64-bit (Trixie / Debian 13) |
| Microphone | USB mic (PCM2902-based or similar) |
| Speaker | 3.5mm jack or USB headset |

---

## System Dependencies

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    python3-dev python3-venv python3-pip \
    portaudio19-dev libasound2-dev \
    libopenblas-dev libatlas-base-dev \
    git
```

---

## Installation

```bash
git clone https://github.com/spideyz0r/sandvoice.git
cd sandvoice
python3 -m venv env
source env/bin/activate
```

Install `openwakeword` first with `--no-deps` to skip `tflite-runtime` (no wheel available for Python 3.13 on aarch64), then install the rest:

```bash
pip install openwakeword>=0.6.0 --no-deps
pip install scipy
pip install -r requirements.txt
```

---

## Configuration

Create `~/.sandvoice/config.yaml`. Minimum working config:

```yaml
botname: Sandbot
language: English
timezone: America/Toronto
location: Toronto, Ontario, Canada
verbosity: brief

openwakeword_model: ~/sandvoice/models/sand_voice.onnx
wake_phrase: sand voice
wake_word_sensitivity: 0.5

log_level: info

stream_responses: enabled
stream_tts: enabled

text_to_speech_model: tts-1
bot_voice_model: nova
speech_to_text_model: gpt-4o-mini-transcribe
speech_to_text_task: transcribe
speech_to_text_language: en
```

Adjust `timezone`, `location`, `language`, and `speech_to_text_language` to your locale.

---

## Audio Setup

### Check available devices

```bash
# Playback devices
aplay -l

# Capture (input) devices
arecord -l
```

Example output with a USB mic and 3.5mm speaker:

```
**** List of PLAYBACK Hardware Devices ****
card 0: Headphones [bcm2835 Headphones], device 0: ...   ← 3.5mm jack
card 1: vc4hdmi [vc4-hdmi], device 0: ...               ← HDMI (ignore)

**** List of CAPTURE Hardware Devices ****
card 1: Device [USB PnP Sound Device], device 0: ...     ← USB mic
```

### Input (microphone)

SandVoice automatically selects the first `hw:N,M` USB input device on Linux — no configuration needed. If you have multiple USB audio devices, the first one found is used.

### Output (speaker)

SandVoice automatically detects USB output devices and sets `AUDIODEV` accordingly. If you want to force a specific output device (e.g. 3.5mm jack instead of USB), set `AUDIODEV` in your shell before launching:

```bash
# Use 3.5mm jack (card 0)
export AUDIODEV=plughw:0,0
```

To make this permanent, add it to `~/.bashrc`:

```bash
echo 'export AUDIODEV=plughw:0,0' >> ~/.bashrc
source ~/.bashrc
```

To use a USB headset for both input and output, leave `AUDIODEV` unset — auto-detection will pick it up.

### Test audio

Test speaker output:

```bash
speaker-test -D plughw:0,0 -t sine -f 440 -l 1   # 3.5mm
speaker-test -D plughw:2,0 -t sine -f 440 -l 1   # USB (adjust card number)
```

Test mic input (record 3 seconds, play back):

```bash
arecord -D hw:1,0 -f cd -d 3 /tmp/test.wav && aplay /tmp/test.wav
```

---

## Running SandVoice

```bash
cd ~/sandvoice
OPENAI_API_KEY=your_key OPENWEATHERMAP_API_KEY=your_key env/bin/python3 sandvoice.py --wake-word
```

Say the wake phrase (`sand voice` by default) to activate. SandVoice will beep, listen, transcribe, and respond via TTS.

---

## Wake Word Model

The repo ships with `models/sand_voice.onnx` — a custom model for the phrase "sand voice". To use a different wake word, see [CUSTOM_WAKE_WORDS.md](./CUSTOM_WAKE_WORDS.md) or use one of the built-in openWakeWord models:

```yaml
openwakeword_model: hey_jarvis    # built-in, no file path needed
wake_phrase: hey jarvis
```
