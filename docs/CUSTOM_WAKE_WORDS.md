# Custom Wake Words Guide

This guide covers wake word configuration for SandVoice.

## Overview

SandVoice uses [openWakeWord](https://github.com/dscripka/openWakeWord) (MIT-licensed, no API key required).
The default wake phrase is **"sand voice"**, using the model bundled at `models/sand_voice.onnx`.
You can also use any built-in openWakeWord model or train your own.

## Default Model

Out of the box, SandVoice responds to **"sand voice"** using the included model:

```yaml
openwakeword_model: models/sand_voice.onnx
wake_phrase: "sand voice"
wake_word_sensitivity: 0.25
```

## Built-in Models (No File Required)

If you prefer a built-in model that needs no `.onnx` file, set `openwakeword_model` to a model name string:

```yaml
openwakeword_model: hey_jarvis
wake_phrase: "hey jarvis"
wake_word_sensitivity: 0.35
```

Available built-in names: `hey_jarvis`, `alexa`, `hey_mycroft`.

## Training Your Own Wake Word

The easiest way to train a custom model is the [openWakeWord Google Colab notebook](https://github.com/dscripka/openWakeWord#training-new-models) — free GPU, no local setup required. Training takes ~10–20 minutes.

### Quick Steps

1. Open the Colab notebook (link above).
2. In the **Target phrase** cell, enter your phrase (e.g. `sand voice`).
3. Optionally record real samples of your own voice — this significantly improves accuracy over synthetic-only training.
4. Run all cells. Training takes ~10–20 minutes on a free Colab GPU.
4. Download the generated `.onnx` file from the Colab session.
5. Copy it to your machine, e.g. `~/.sandvoice/wake-words/hey_sandvoice.onnx`.
6. Point SandVoice at it:

```yaml
openwakeword_model: "/home/user/.sandvoice/wake-words/hey_sandvoice.onnx"
wake_phrase: "hey sandvoice"
wake_word_sensitivity: 0.5
```

**Notes:**
- Use an absolute path for `openwakeword_model` when pointing to a custom `.onnx` file.
- `wake_phrase` is for display/logging only; actual detection uses the model.
- Train separate models per platform if needed — openWakeWord models are architecture-independent (ONNX), so the same file works on macOS M1 and Raspberry Pi.

## Configuration Reference

```yaml
# Wake word settings
openwakeword_model: hey_jarvis          # built-in name or absolute path to .onnx
wake_phrase: "hey jarvis"               # display name shown in logs/terminal
wake_word_sensitivity: 0.35            # detection threshold (0.0–1.0)

# VAD settings (control how long to listen after wake word)
vad_silence_duration: 1.5              # seconds of silence = end of utterance
vad_aggressiveness: 3                  # 0–3, higher = more aggressive silence detection
vad_timeout: 30                        # max recording length (seconds)

# Audio feedback
wake_confirmation_beep: enabled
wake_confirmation_beep_freq: 800       # Hz
wake_confirmation_beep_duration: 0.1   # seconds
visual_state_indicator: enabled
```

## Raspberry Pi / Linux Install

openWakeWord uses ONNX Runtime, not tflite. Install:

```bash
pip install openwakeword>=0.6.0 --no-deps
pip install scipy
```

If `onnxruntime` is not already installed, add it:

```bash
pip install onnxruntime==1.20.0
```

(Pin to 1.20.0 — later versions have known issues on aarch64 Pi.)

## Tips for Best Results

1. **Train with natural voice**: Say the phrase naturally, not robotically.
2. **Unique phrases**: Avoid common words to reduce false positives.
3. **Adjust sensitivity**: Lower `wake_word_sensitivity` (e.g. 0.3) to catch more detections; raise it (e.g. 0.7) to reduce false positives.
4. **Test distances**: Test from 1 m, 2 m, 3 m to find optimal placement.

## Troubleshooting

1. Enable debug mode: `debug: enabled` in config.
2. Check logs for `Wake word score:` lines to see raw scores for your phrase.
3. If scores never reach threshold, lower `wake_word_sensitivity` or retrain.
4. Report issues: https://github.com/spideyz0r/sandvoice/issues
