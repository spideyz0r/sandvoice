# Platform Auto-Detection

**Status**: 📋 Planned
**Priority**: 2
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Currently, users must manually configure platform-specific settings like `linux_warnings` and `channels` in config.yaml. This is error-prone and confusing. The application should automatically detect the platform and configure audio settings appropriately.

---

## Problem Statement

Configuration footguns:
- `linux_warnings: disabled` on macOS causes the app to crash (tries to load ALSA library)
- Mac users must set `channels: 1`, but this isn't obvious
- The name "linux_warnings" is confusing when used on macOS
- New users don't know what values to use for their platform

This creates a poor first-run experience and makes setup unnecessarily difficult.

---

## User Stories

**As a macOS user**, I want the app to work out of the box without manual audio configuration, so I don't have to understand platform-specific details.

**As a Raspberry Pi user**, I want the app to automatically detect I'm on Linux and configure itself appropriately, so setup is simple.

**As a developer**, I want to test on both platforms without changing config files, so development workflow is smooth.

---

## Acceptance Criteria

### Platform Detection
- [ ] Automatically detect operating system (macOS, Linux)
- [ ] Detect architecture (ARM for Pi, x86_64/arm64 for Mac)
- [ ] Log detected platform in debug mode

### Audio Configuration
- [ ] macOS: automatically set channels to 1, skip ALSA initialization
- [ ] Linux/Pi: automatically detect optimal channel configuration
- [ ] Detect available audio devices and select appropriate one
- [ ] Warn if no audio devices found, suggest USB headset

### Configuration Cleanup
- [ ] Remove `linux_warnings` from config.yaml (replaced by auto-detection)
- [ ] Make `channels` optional in config (auto-detected by default)
- [ ] Allow manual override if auto-detection fails

### User Experience
- [ ] First run prints detected platform and audio settings
- [ ] Clear message if audio configuration fails with troubleshooting steps
- [ ] Debug mode shows all detected hardware details

---

## Technical Requirements

### Platform Detection

Use Python's `platform` module:
- `platform.system()` - Returns 'Darwin' (Mac) or 'Linux'
- `platform.machine()` - Returns architecture (arm64, aarch64, x86_64)
- `platform.release()` - OS version for logging

### Audio Device Detection

Use PyAudio to enumerate devices:
- Get default input/output devices
- Detect channel support for each device
- Select best match automatically
- Fall back to user configuration if specified

### macOS-Specific

- Never load ALSA library
- Use CoreAudio backend (PyAudio default on Mac)
- Default to 1 channel (mono) unless device supports stereo well

### Linux/Raspberry Pi-Specific

- Load ALSA library and suppress warnings
- Detect if PulseAudio or ALSA backend
- Default to 2 channels, fall back to 1 if needed

### Configuration Precedence

1. User-specified config values (if present)
2. Auto-detected values
3. Fallback defaults

This allows power users to override while keeping defaults sane.

---

## Configuration Changes

Modify `config.yaml`:
```yaml
# Audio settings (optional - will auto-detect if not specified)
# channels: 1  # Uncomment to override auto-detection
# audio_backend: auto  # Options: auto, alsa, pulse, coreaudio

# Removed (no longer needed):
# linux_warnings: enabled
```

Update `configuration.py` defaults:
```python
"channels": None,  # Auto-detect
"audio_backend": "auto",
"platform_auto_detect": True,  # Allow disabling for debugging
```

---

## Testing Requirements

### Unit Tests
- Mock `platform.system()` to test macOS and Linux paths
- Mock PyAudio device enumeration
- Test configuration precedence logic
- Verify ALSA library not loaded on macOS

### Integration Tests
- Run on Mac M1: verify channels=1, no ALSA
- Run on Raspberry Pi 3B: verify channels detected, ALSA loaded
- Test with USB headset: verify correct device selected
- Test with no audio devices: verify graceful fallback

### Manual Testing
- Fresh install on Mac - should work without editing config
- Fresh install on Pi - should work without editing config
- Test with various USB audio devices

---

## Dependencies

- **Depends on**: Error Handling (Priority 1) - need error handling for device detection failures

---

## Out of Scope

- GUI for audio device selection
- Support for Windows (not a target platform)
- Advanced audio routing (multi-device, etc.)
- Audio quality optimization

---

## Success Metrics

- Zero manual audio configuration needed for standard setups
- Works out of box on Mac M1 and Raspberry Pi 3B
- Clear error messages when audio detection fails
- Config file simpler and more intuitive
