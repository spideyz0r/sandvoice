# Plan 14: Energy-Based Speech Detection

**Status**: 📋 Backlog
**Priority**: 14
**Platforms**: macOS, Raspberry Pi

---

## Problem Statement
WebRTC VAD detects any sound as potential speech, including constant background noise like music or podcasts. We need to distinguish actual speech (variable energy, speech patterns) from ambient noise (relatively constant energy).

## Goals
1. Measure ambient noise baseline during IDLE state
2. Only consider frames as speech if energy exceeds baseline + threshold
3. Auto-calibrate on startup and periodically
4. Reduce false positives from constant background audio

## Technical Approach

### Energy Detection Concept
- **Ambient noise** (music, HVAC, fans): Relatively constant energy level
- **Human speech**: Variable energy with pauses, higher peaks above ambient
- **Key insight**: Speech energy spikes above ambient; background is steady

### Algorithm
1. During IDLE, sample ambient noise level (RMS energy)
2. Calculate baseline as rolling average of ambient samples
3. During LISTENING, only count frame as "speech" if:
   - Energy > baseline + threshold_db
   - AND webrtcvad also says it's speech
4. Periodically recalibrate baseline (every N seconds in IDLE)

## Implementation

### Phase 1: Energy Measurement Utility
```python
# In common/audio_utils.py (new file)
import numpy as np

def calculate_rms_energy(audio_frames: bytes, sample_width: int = 2) -> float:
    """Calculate RMS energy of audio frames in dB."""
    # Select appropriate dtype and full-scale value based on sample width (bytes)
    if sample_width == 1:
        dtype = np.int8
    elif sample_width == 2:
        dtype = np.int16
    elif sample_width == 4:
        dtype = np.int32
    else:
        raise ValueError(f"Unsupported sample_width: {sample_width}")

    samples = np.frombuffer(audio_frames, dtype=dtype)
    rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
    if rms == 0:
        return -96.0  # Floor

    # Full-scale value for signed PCM with the given sample width
    full_scale = float(1 << (8 * sample_width - 1))
    return 20 * np.log10(rms / full_scale)

def is_above_threshold(energy_db: float, baseline_db: float, threshold_db: float) -> bool:
    """Check if energy exceeds baseline by threshold."""
    return energy_db > (baseline_db + threshold_db)
```

### Phase 2: Ambient Calibration in IDLE
```python
# In wake_word.py, during _state_idle()
from common.audio_utils import calculate_rms_energy
import statistics

class WakeWordMode:
    def __init__(self, ...):
        self.ambient_baseline_db = -40.0  # Default
        self.calibration_samples = []

    def _calibrate_ambient(self, audio_frames):
        """Update ambient baseline with new sample."""
        energy = calculate_rms_energy(audio_frames)
        self.calibration_samples.append(energy)
        if len(self.calibration_samples) > 50:  # ~1.5 seconds
            self.calibration_samples.pop(0)
        self.ambient_baseline_db = statistics.fmean(self.calibration_samples)
```

### Phase 3: Enhanced VAD in LISTENING
```python
def _is_speech_frame(self, audio_frames) -> bool:
    """Combined VAD + energy detection."""
    # Standard VAD check
    vad_says_speech = self.vad.is_speech(audio_frames, self.sample_rate)

    if not self.config.energy_detection_enabled:
        return vad_says_speech

    # Energy check
    energy = calculate_rms_energy(audio_frames)
    above_ambient = is_above_threshold(
        energy,
        self.ambient_baseline_db,
        self.config.energy_threshold_db
    )

    # Both must agree
    return vad_says_speech and above_ambient
```

### Phase 4: Configuration
```yaml
# New config options
energy_detection_enabled: true
energy_threshold_db: 6.0        # dB above ambient to count as speech
energy_calibration_seconds: 2.0  # How long to sample ambient on startup
energy_recalibrate_interval: 30  # Recalibrate every N seconds in IDLE
```

## Testing Strategy

### Unit Tests
- Test RMS calculation with known signals
- Test threshold comparison logic
- Test calibration averaging

### Integration Tests
- Test with silence → should calibrate low
- Test with music → should calibrate to music level
- Test speech over music → should detect speech peaks

### Manual Testing
- Play music, say wake word, speak → should stop correctly
- Play podcast, speak over it → should detect your speech
- Quiet room → should work as before

## Success Criteria
- [ ] Ambient baseline calibrated on startup
- [ ] Speech detected only when energy > baseline + threshold
- [ ] Works correctly with music playing
- [ ] No regression in quiet environment performance

## Effort: Medium

## Dependencies
- numpy (already likely installed)
- Plan 13 (VAD robustness) recommended first

## Relationship
- Builds on: Plan 13 (VAD Robustness)
- Enhanced by: Plan 15 (Speech Classification)
