# Wake Word Mode

**Status**: 📋 Planned
**Priority**: 4
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Add a NEW always-on listening mode where SandVoice continuously listens for a wake phrase (default: "Hey Sandvoice") and activates when detected. This is an additional feature alongside the existing keyboard-based interaction modes. Include voice activity detection (VAD) to automatically detect when the user stops speaking.

**Important**: This does NOT replace existing interaction modes. The current ESC key mode and CLI text mode remain unchanged and available.

---

## Problem Statement

Current interaction modes work well but require manual triggering:
- **Voice mode (current)**: User runs app, speaks, presses ESC to stop - great for focused interactions
- **CLI mode (current)**: User types text - great for quiet environments

New capability needed:
- **Wake word mode (NEW)**: Always-on hands-free mode like Alexa/Google Home - great for multitasking

This adds a third mode while preserving existing functionality.

---

## User Stories

**As a user**, I want to choose between keyboard-triggered mode and wake word mode, so I can use the interaction style that fits my current situation.

**As a user cooking**, I want to say "Hey Sandvoice" without touching my keyboard, so I can get help hands-free.

**As a user at my desk**, I want to continue using ESC key mode, because it gives me precise control over when to stop recording.

**As a user**, I want the system to automatically detect when I'm done speaking in wake word mode, so I don't need to press any keys.

**As a user**, I want a confirmation beep when SandVoice hears the wake word, so I know it's listening.

---

## Acceptance Criteria

### Wake Word Detection
- [ ] Continuously listens for wake phrase in background
- [ ] Default wake phrase: "Hey Sandvoice"
- [ ] User can customize wake phrase in config
- [ ] Adjustable sensitivity (low, medium, high)
- [ ] Works on both Mac M1 and Raspberry Pi 3B
- [ ] Low CPU usage when idle

### Voice Activity Detection (Wake Word Mode Only)
- [ ] Automatically detects when user starts speaking
- [ ] Automatically detects when user stops speaking (silence threshold)
- [ ] Configurable silence duration (default: 1.5 seconds)
- [ ] No ESC key needed in this mode

### User Feedback
- [ ] Plays confirmation beep when wake word detected
- [ ] Optional visual indicator in terminal (e.g., "🎤 Listening...")
- [ ] Plays different sound when processing complete
- [ ] Clear indication of current state (idle, listening, processing, responding)

### Interaction Modes

**All three modes coexist:**

1. **Voice Mode (Current - Default)**
   - Run: `./sandvoice`
   - User speaks, presses ESC to stop
   - No wake word needed
   - Precise control
   - **Unchanged by this feature**

2. **CLI Mode (Current)**
   - Run: `./sandvoice --cli`
   - User types text
   - No audio at all
   - **Unchanged by this feature**

3. **Wake Word Mode (NEW)**
   - Run: `./sandvoice --wake-word`
   - Always listening for "Hey Sandvoice"
   - Auto-detects end of speech via VAD
   - Hands-free operation
   - Can exit gracefully (Ctrl+C)

---

## Technical Requirements

### Wake Word Library

Use **Porcupine** by Picovoice:
- Free tier supports 3 wake words
- Works offline (no API calls)
- Low resource usage (important for Pi)
- Cross-platform (macOS, Linux/Pi)
- Pre-trained models available

Alternative: **openWakeWord** (fully open source, but may need more resources)

### Voice Activity Detection

Use **webrtcvad**:
- Lightweight and efficient
- Battle-tested (from WebRTC project)
- Detects speech vs silence
- Configurable aggressiveness

**Note**: VAD only used in wake word mode. Traditional voice mode still uses ESC key.

### State Machine (Wake Word Mode Only)

```
IDLE → (wake word detected) → LISTENING → (silence detected) → PROCESSING → RESPONDING → IDLE
```

**States:**
- **IDLE**: Listening only for wake word, low CPU
- **LISTENING**: Recording user command, running VAD
- **PROCESSING**: Transcribing and routing to plugin
- **RESPONDING**: Playing response audio
- **IDLE**: Returns to wake word detection

### Audio Handling

- Background thread for wake word detection (wake word mode only)
- Main thread handles command processing
- Buffer audio in chunks (10ms frames)
- Clear buffers between states
- Handle audio device changes gracefully
- Traditional voice mode unchanged (no background threads)

### Mode Selection

Wake word mode runs until user exits (Ctrl+C). No daemon mode.

Traditional modes work exactly as before.

---

## Configuration Changes

Add to `config.yaml`:
```yaml
# Wake word settings (only used with --wake-word flag)
wake_phrase: "hey sandvoice"  # Customizable wake phrase
wake_word_sensitivity: medium  # Options: low, medium, high
wake_word_model_path: ~/.sandvoice/wake_word_model.ppn

# Voice activity detection (only used with --wake-word flag)
vad_enabled: true
vad_silence_duration: 1.5  # seconds of silence before considering done
vad_aggressiveness: 3  # 0-3, higher = more aggressive silence detection

# Audio feedback (only used with --wake-word flag)
play_wake_confirmation_beep: true
play_processing_complete_beep: false
show_visual_state_indicator: true

# Note: Traditional voice mode (ESC key) and CLI mode are unaffected
```

---

## Testing Requirements

### Unit Tests
- Mock Porcupine wake word detection
- Test state machine transitions
- Test VAD silence detection logic
- Test audio buffer management
- Verify traditional modes unaffected

### Integration Tests
- Test with recorded wake word audio
- Test with various silence durations
- Test state transitions end-to-end
- Test on Mac M1 and Pi 3B
- Verify ESC key mode still works
- Verify CLI mode still works

### Manual Testing
- Say wake phrase from different distances
- Test with background noise
- Test rapid commands back-to-back
- Test long pauses during speaking
- Verify CPU usage is reasonable when idle
- Verify traditional modes unchanged

---

## Dependencies

- **Depends on**: Error Handling (Priority 1) - wake word detection can fail
- **Depends on**: Platform Auto-Detection (Priority 2) - audio config must work
- **Depends on**: Unit Tests (Priority 3) - need test infrastructure

**New Dependencies to Add:**

```
pvporcupine>=2.2.0  # Wake word detection
webrtcvad>=2.0.10  # Voice activity detection
```

---

## Out of Scope

- Replacing or removing ESC key mode (it stays!)
- Replacing or removing CLI mode (it stays!)
- Multiple wake phrases simultaneously
- Wake word training (use pre-trained models)
- Voice authentication/user recognition
- Continuous conversation mode (always listening after first command)
- Cloud-based wake word detection
- GUI for configuration

---

## Success Metrics

- Wake word detection accuracy >95% in quiet environment
- Wake word detection works from 3+ meters away
- VAD correctly detects end of speech within 2 seconds
- <5% false positive rate for wake word
- CPU usage <10% when idle (Pi 3B)
- Works reliably on both Mac M1 and Pi 3B
- **Traditional ESC key mode and CLI mode remain fully functional**
