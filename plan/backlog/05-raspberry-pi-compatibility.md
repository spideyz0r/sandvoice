# Raspberry Pi Compatibility

**Status**: 📋 Planned
**Priority**: 5
**Platforms**: Raspberry Pi 3B (primary target), also Pi 4/5

---

## Overview

Ensure SandVoice works seamlessly on Raspberry Pi 3B with USB audio devices. Document setup process, dependencies, and testing procedures. The goal is to make Raspberry Pi a viable platform for deploying SandVoice as a personal voice assistant.

---

## Problem Statement

Current development is Mac-focused with no Pi testing:
- Unknown if dependencies install correctly on Pi
- No documentation for Pi setup
- No testing on ARM architecture
- No performance benchmarks for Pi 3B
- USB audio device setup not documented

This prevents users from deploying on affordable, dedicated hardware like Raspberry Pi.

---

## User Stories

**As a user**, I want to run SandVoice on a Raspberry Pi, so I can have a dedicated, always-available voice assistant.

**As a new Pi user**, I want clear setup instructions, so I can get SandVoice running without troubleshooting.

**As a developer**, I want to know SandVoice works on Pi, so I can confidently develop features for both platforms.

---

## Acceptance Criteria

### Raspberry Pi OS Compatibility
- [ ] Identify Python version shipped with latest Raspberry Pi OS
- [ ] Verify all dependencies install on Pi 3B
- [ ] Document any Pi-specific package requirements
- [ ] Test on Raspberry Pi OS (64-bit preferred)

### USB Audio Device Support
- [ ] Document recommended USB audio devices
- [ ] Document setup for USB headsets
- [ ] Document setup for USB microphones + speakers
- [ ] Provide audio device troubleshooting guide

### Performance
- [ ] Verify acceptable performance on Pi 3B
- [ ] Measure latency for full interaction cycle
- [ ] Verify wake word detection works on Pi
- [ ] Document any performance limitations

### Documentation
- [ ] Complete setup guide for Pi installation
- [ ] List of required apt packages
- [ ] Python package installation instructions
- [ ] Audio device configuration steps
- [ ] Common troubleshooting issues
- [ ] Performance optimization tips

---

## Technical Requirements

### Research Tasks

**Raspberry Pi OS Python Version:**
- Identify Python version in latest Raspberry Pi OS Lite and Desktop
- Verify compatibility with SandVoice requirements
- Document any version-specific issues

**USB Audio Devices:**
- Test with common USB headsets
- Test with USB microphone + 3.5mm speakers
- Test with USB audio adapters
- Document device selection in PyAudio

### System Requirements

**Minimum Hardware:**
- Raspberry Pi 3B (1GB RAM)
- 8GB+ microSD card
- USB audio device (microphone + speakers or headset)
- Internet connection

**Recommended Hardware:**
- Raspberry Pi 4 (2GB+ RAM) or Pi 5 for better performance
- 16GB+ microSD card (Class 10)
- Quality USB headset with noise cancellation
- Ethernet connection (more stable than WiFi)

### Installation Steps (To Be Documented)

**System Setup:**
1. Flash Raspberry Pi OS (64-bit recommended)
2. Configure WiFi/Ethernet
3. Update system packages
4. Install required apt packages

**Audio Setup:**
1. Connect USB audio device
2. Verify device detected
3. Test recording
4. Test playback
5. Configure ALSA settings if needed

**SandVoice Installation:**
1. Install Python dependencies
2. Clone repository
3. Create virtual environment
4. Install requirements
5. Configure settings
6. Test basic functionality

**Wake Word Setup (if enabled):**
1. Install Porcupine
2. Configure wake word model
3. Test detection
4. Optimize sensitivity

### Performance Expectations

**Pi 3B (realistic expectations):**
- Wake word detection: Should work well (lightweight)
- Audio recording: No issues
- OpenAI API calls: Network bound (same as Mac)
- Audio playback: No issues
- MP3 encoding: May be slower than Mac (acceptable delay)

**Bottlenecks:**
- lameenc MP3 encoding on Pi 3B may add 1-2 seconds
- Network latency to OpenAI (not hardware specific)
- SD card I/O (use quality card)

### Platform-Specific Code

Ensure platform detection correctly identifies Pi:
- Detect ARM architecture
- Detect Linux OS
- Configure audio appropriately
- Use ALSA library correctly

---

## Configuration Changes

No config changes needed - platform auto-detection should handle Pi setup.

Document recommended config.yaml settings for Pi in setup guide.

---

## Documentation Structure

Create `docs/raspberry-pi-setup.md`:

```markdown
# Raspberry Pi Setup Guide

## Hardware Requirements
## Raspberry Pi OS Installation
## Audio Device Setup
## SandVoice Installation
## Testing
## Troubleshooting
## Performance Tips
```

---

## Testing Requirements

### Initial Testing
- [ ] Test on Raspberry Pi 3B with Raspberry Pi OS
- [ ] Test with USB headset
- [ ] Test all three interaction modes (voice, CLI, wake word)
- [ ] Test all plugins
- [ ] Measure performance metrics

### Performance Metrics to Collect
- Time from wake word to start recording
- Audio encoding time (WAV to MP3)
- Round-trip time for full interaction
- CPU usage idle vs active
- Memory usage

### Compatibility Testing
- [ ] Test with different USB audio devices
- [ ] Test with Raspberry Pi 4 (if available)
- [ ] Test on 32-bit vs 64-bit Pi OS

### Regression Testing
- Ensure changes for Pi don't break Mac functionality
- Test on Mac M1 after Pi compatibility changes

---

## Dependencies

- **Depends on**: Error Handling (Priority 1) - need robust error handling for Pi
- **Depends on**: Platform Auto-Detection (Priority 2) - critical for Pi setup
- **Depends on**: Unit Tests (Priority 3) - verify Pi compatibility
- **Depends on**: Wake Word Mode (Priority 4) - main use case for Pi

**Pi-Specific System Packages (to be documented):**
```bash
# Expected packages (TBD during implementation)
sudo apt-get update
sudo apt-get install -y \
    python3-dev \
    portaudio19-dev \
    python3-pyaudio \
    libasound2-dev \
    # ... others as discovered
```

---

## Out of Scope

- Raspberry Pi Zero support (too slow)
- Raspberry Pi 1/2 support (outdated)
- GUI/touch screen interface
- Custom Pi OS images
- Automated Pi provisioning
- Hardware HATs (stick with USB audio)
- Power management/optimization

---

## Success Metrics

- Complete setup guide written and tested
- Successfully runs on Pi 3B from fresh install
- All features work on Pi (voice, CLI, wake word, all plugins)
- Performance acceptable (<5 second total latency)
- Wake word detection >90% accuracy on Pi
- No platform-specific crashes
- Setup takes <30 minutes for new user
