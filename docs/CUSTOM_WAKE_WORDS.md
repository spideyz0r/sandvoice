# Custom Wake Words Guide

This guide shows you how to create and use custom wake words like "hey sandvoice" instead of built-in keywords.

## Overview

SandVoice supports two types of wake words:
1. **Built-in Keywords**: Pre-trained words like "computer", "jarvis", "porcupine"
2. **Custom Wake Words**: Your own phrases trained on Picovoice Console

## Built-in Wake Words

Available without any setup:
- alexa
- americano
- blueberry
- bumblebee
- computer
- grapefruit
- grasshopper
- hey barista
- hey google
- hey siri
- jarvis
- ok google
- pico clock
- picovoice
- porcupine
- terminator

**Quick Start with Built-in:**
```yaml
# ~/.sandvoice/config.yaml
wake_phrase: "computer"
porcupine_access_key: "YOUR_ACCESS_KEY"
```

## Creating Custom Wake Words

### Step 1: Get Picovoice Access Key

1. Visit [Picovoice Console](https://console.picovoice.ai/)
2. Sign up (free tier available)
3. Copy your **Access Key** from the dashboard

**Free Tier Limits:**
- ✅ 3 custom wake words
- ✅ Unlimited API calls
- ✅ Works offline after first download

### Step 2: Train Your Custom Wake Word

1. Go to **Porcupine Wake Word** section
2. Click **"Train Custom Wake Word"**
3. Enter your phrase (e.g., "hey sandvoice", "sand voice")
4. Select **Language**: English
5. Select **Platform(s)**:
   - **macOS (x86_64)** for Intel Macs
   - **macOS (arm64)** for M1/M2 Macs
   - **Linux (ARM Cortex-A)** for Raspberry Pi
   - You can train multiple platforms at once
6. Click **"Train"** (takes 2-5 minutes)
7. Download the `.ppn` file(s)

### Step 3: Install the .ppn File

```bash
# Create directory for wake word models
mkdir -p ~/.sandvoice/wake-words/

# Move your downloaded .ppn file
mv ~/Downloads/Sand-voice_en_mac_v4_0_0.ppn ~/.sandvoice/wake-words/
```

### Step 4: Configure SandVoice

Edit `~/.sandvoice/config.yaml`:

```yaml
wake_phrase: "sand voice"
porcupine_access_key: "YOUR_ACCESS_KEY_HERE"
porcupine_keyword_paths: "/Users/username/.sandvoice/wake-words/Sand-voice_en_mac_v4_0_0.ppn"

# Optional: Adjust sensitivity (0.0 - 1.0)
wake_word_sensitivity: 0.5
```

**Important:**
- Use **absolute path** for `porcupine_keyword_paths`
- Don't use `~` shorthand - use full `/Users/username/...` path
- `wake_phrase` is for display only - actual detection uses the .ppn file

### Step 5: Test It

```bash
cd ~/path/to/sandvoice
source env/bin/activate
python sandvoice.py --wake-word
```

Say your custom phrase to activate!

## Multi-Platform Setup

If you use SandVoice on multiple devices, train separate models:

**macOS Config:**
```yaml
porcupine_keyword_paths: "/Users/username/.sandvoice/wake-words/Sand-voice_en_mac_v4_0_0.ppn"
```

**Raspberry Pi Config:**
```yaml
porcupine_keyword_paths: "/home/pi/.sandvoice/wake-words/Sand-voice_en_linux_v4_0_0.ppn"
```

## Configuration Examples

### Example 1: Single Custom Wake Word (TXT format)
```yaml
wake_phrase: "hey assistant"
porcupine_access_key: "REDACTED"
porcupine_keyword_paths: "/Users/john/.sandvoice/wake-words/hey-assistant_en_mac_v4_0_0.ppn"
wake_word_sensitivity: 0.5
```

### Example 2: Single Custom Wake Word (JSON format)
```yaml
wake_phrase: "sand voice"
porcupine_access_key: "REDACTED"
porcupine_keyword_paths: "/Users/john/.sandvoice/wake-words/Sand-voice_en_mac_v4_0_0.ppn"
wake_word_sensitivity: 0.7
```

### Example 3: Built-in Wake Word
```yaml
wake_phrase: "jarvis"
porcupine_access_key: "REDACTED"
# No porcupine_keyword_paths needed for built-in keywords
wake_word_sensitivity: 0.5
```

## Troubleshooting

For troubleshooting wake word detection issues, see the [official Porcupine documentation](https://picovoice.ai/docs/porcupine/).

## Advanced Configuration

### Adjusting VAD (Voice Activity Detection)

Control how long SandVoice listens after wake word:

```yaml
# How long to wait for silence before processing (seconds)
vad_silence_duration: 1.5

# VAD aggressiveness (0-3, higher = more aggressive silence detection)
vad_aggressiveness: 3

# Maximum continuous speech duration (seconds)
vad_timeout: 30
```

### Audio Feedback

```yaml
# Play beep when wake word detected
wake_confirmation_beep: enabled
wake_confirmation_beep_freq: 800  # Hz
wake_confirmation_beep_duration: 0.1  # seconds

# Show visual state indicators in terminal
visual_state_indicator: enabled
```

## Tips for Best Results

1. **Train with natural voice**: Say the phrase naturally, not robotically
2. **Quiet environment**: Train in a quiet room
3. **Unique phrases**: Avoid common words to reduce false positives
4. **Repeat training**: If detection is poor, re-train the model
5. **Test distances**: Test from 1m, 2m, 3m away to find optimal sensitivity

## Getting Help

If you're still having issues:
1. Enable debug mode: `debug: enabled` in config
2. Check logs for error messages
3. Report issues: https://github.com/spideyz0r/sandvoice/issues
4. Include:
   - Platform (macOS/Linux/Pi)
   - Config file (remove access key)
   - Error messages

## References

- [Picovoice Console](https://console.picovoice.ai/)
- [Porcupine Documentation](https://picovoice.ai/docs/porcupine/)
- [SandVoice GitHub](https://github.com/spideyz0r/sandvoice)
