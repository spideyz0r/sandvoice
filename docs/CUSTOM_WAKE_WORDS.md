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

> **Path resolution for `.onnx` files:** Relative paths are resolved first against the config directory (`~/.sandvoice/`), then against the SandVoice install directory (where `sandvoice.py` lives). Absolute paths are used as-is. For custom models, an absolute path or a path relative to `~/.sandvoice/` is recommended (e.g. `~/.sandvoice/wake-words/my_model.onnx`).

## Built-in Models (No File Required)

If you prefer a built-in model that needs no `.onnx` file, set `openwakeword_model` to a model name string:

```yaml
openwakeword_model: hey_jarvis
wake_phrase: "hey jarvis"
wake_word_sensitivity: 0.35
```

Available built-in names: `hey_jarvis`, `alexa`, `hey_mycroft`.

## Training Your Own Wake Word

The easiest way to train a custom model is Google Colab — free GPU, no local setup required. The full pipeline takes ~85 minutes (data download ~30 min, synthetic clip generation ~40 min, model training ~15 min).

> **Note:** The upstream openWakeWord training notebooks don't work with current Google Colab (Python 3.12+). Use the fixed fork at [spideyz0r/openWakeWord](https://github.com/spideyz0r/openWakeWord), which patches Python 3.12 compatibility and torchaudio issues. The training notebooks are in the `notebooks/` directory.

### Steps

1. Open Colab → **File → Open notebook → GitHub** → `spideyz0r/openWakeWord`, branch `fix/python312-compat` (check the repo for the latest branch if this one is gone), file `notebooks/automatic_model_training.ipynb`
2. In the **Define training configuration** cell, set your phrase: `config["target_phrase"] = ["your phrase here"]`. Also set `model_name` and `output_dir`.
3. Run the **Environment setup** cell
4. Run the **Download data** cell (downloads AudioSet negatives — ~30 min)
5. Run the **Generate synthetic clips** cell (generates TTS clips — ~40 min)
6. *(Optional but recommended)* Upload your own voice recordings and oversample them:
```bash
cp /content/your_clips/*.wav /content/my_custom_model/<model_name>/positive_train/
# oversample real clips 20x so the model learns your voice, not just synthetic TTS
# skip clip_* (synthetic) and real_* (already-oversampled) files
cd /content/my_custom_model/<model_name>/positive_train/
for f in *.wav; do
  case "$f" in clip_*|real_*) continue;; esac
  for i in $(seq 1 19); do cp "$f" "real_${i}_${f}"; done
done
```
7. Run the **Augment clips** cell
8. Run the **Train model** cell (~15 min)
9. Download `/content/my_custom_model/<model_name>.onnx` from the Colab file browser
10. Copy it to your machine and update your config:

```yaml
openwakeword_model: "/home/user/.sandvoice/wake-words/my_model.onnx"
wake_phrase: "my phrase"
wake_word_sensitivity: 0.25
```

**Notes:**
- `wake_phrase` is for display/logging only; actual detection uses the model. When using a built-in model, keep `wake_phrase` consistent with that model's trigger phrase (e.g. `"hey jarvis"` for `hey_jarvis`) to avoid misleading terminal output.
- The same `.onnx` file works on macOS M1 and Raspberry Pi — no per-platform retraining needed.
- Adding real voice recordings (step 6) makes a significant difference in real-world accuracy.

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

1. Enable debug mode: set `log_level: debug` in config.
2. Check logs for `Wake word score:` lines to see raw scores for your phrase.
3. If scores never reach threshold, lower `wake_word_sensitivity` or retrain.
4. Report issues: https://github.com/spideyz0r/sandvoice/issues
