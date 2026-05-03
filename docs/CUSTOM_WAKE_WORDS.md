# Custom Wake Words Guide

This guide shows you how to create and use custom wake words like "hey sandvoice" with openWakeWord.

## Overview

SandVoice uses [openWakeWord](https://github.com/dscripka/openWakeWord) (MIT-licensed, no API key required).
You can use any of the built-in models or train your own custom `.onnx` model.

## Built-in Models

openWakeWord ships with a small set of pre-trained models. The default is `hey_jarvis`.
Set `openwakeword_model` in `~/.sandvoice/config.yaml` to use one:

```yaml
openwakeword_model: hey_jarvis   # default
wake_phrase: "hey jarvis"
wake_word_sensitivity: 0.35
```

Other available built-in names (pass exact string as `openwakeword_model`):
- `hey_jarvis`
- `alexa`
- `hey_mycroft`

## Training a Custom Wake Word

Custom models are `.onnx` files you train yourself. The easiest way is
[openWakeWord's Colab notebook](https://github.com/dscripka/openWakeWord#training-new-models).

### Quick Steps

1. Open the openWakeWord training notebook in Google Colab (link in the repo above).
2. In the **Target phrase** cell, enter your phrase (e.g. `hey sandvoice`).
3. Run all cells. Training takes ~10–20 minutes on a free Colab GPU.
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
