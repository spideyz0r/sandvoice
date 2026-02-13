# Plan 15: ML-Based Speech Classification

**Status**: 📋 Backlog
**Priority**: 15
**Platforms**: macOS, Raspberry Pi

---

## Problem Statement
Energy-based detection (Plan 14) helps with constant noise but struggles with:
- Podcasts/audiobooks (speech in background)
- TV shows with dialogue
- Multiple speakers in room

Need ML-based speech detection that is more robust than simple energy thresholds; distinguishing "user speaking to assistant" vs "background speech" will be achieved by combining this with additional signals (e.g., wake-word windowing or proximity/direction features).

## Goals
1. Integrate lightweight speech classification / VAD model
2. Robustly detect speech vs non-speech even with background audio (music, TV, podcasts)
3. Maintain low latency (<50ms per frame)
4. Work on Raspberry Pi with acceptable performance
5. Combine VAD with at least one additional signal (wake-word gating, proximity heuristics) to approximate "user speaking to assistant"

## Technical Options

### Option A: Silero VAD (Recommended)
- **Pros**: Lightweight, runs on CPU, better than webrtcvad, easy integration
- **Cons**: Still general speech detection, not speaker-specific
- **Model size**: ~2MB
- **Latency**: ~10ms per frame

```python
import torch
model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad')
(get_speech_timestamps, _, read_audio, *_) = utils

# Per-frame detection
speech_prob = model(audio_chunk, sample_rate)
is_speech = speech_prob > 0.5
```

### Option B: Yamnet Audio Classification
- **Pros**: Classifies 521 audio types (speech, music, noise, etc.)
- **Cons**: Heavier model, may be slow on Pi
- **Model size**: ~15MB
- **Use case**: Could classify "speech" vs "music" vs "silence"

### Option C: Custom Lightweight Classifier
- **Pros**: Tailored to our needs, smallest possible
- **Cons**: Requires training data, more development effort
- **Approach**: Train small CNN on speech vs background audio

### Option D: Voice Activity + Speaker Proximity
- **Pros**: No ML needed, uses audio characteristics
- **Cons**: Less accurate
- **Approach**: Use energy variance, speech cadence, proximity cues

## Recommended Approach: Silero VAD

Silero VAD is significantly better than webrtcvad and runs efficiently on CPU.

### Implementation

#### Phase 1: Silero Integration
```python
# In common/speech_classifier.py (new file)
import torch

class SpeechClassifier:
    def __init__(self, threshold=0.5):
        # Pin to specific version for reproducibility and offline support
        # Consider vendoring model artifact for Pi/offline use with integrity verification
        self.model, self.utils = torch.hub.load(
            'snakers4/silero-vad:v5.1',  # Pin to immutable revision
            'silero_vad',
            force_reload=False
        )
        self.threshold = threshold

    def is_speech(self, audio_frames: bytes, sample_rate: int) -> bool:
        """Classify if audio contains speech."""
        # Convert bytes to tensor
        audio_tensor = self._bytes_to_tensor(audio_frames)

        # Get speech probability
        speech_prob = self.model(audio_tensor, sample_rate).item()

        return speech_prob > self.threshold

    def get_speech_probability(self, audio_frames: bytes, sample_rate: int) -> float:
        """Get speech probability score."""
        audio_tensor = self._bytes_to_tensor(audio_frames)
        return self.model(audio_tensor, sample_rate).item()
```

#### Phase 2: Hybrid Detection
Combine Silero with energy detection for best results:

```python
def _is_user_speech(self, audio_frames) -> bool:
    """Determine if this is user speech directed at assistant."""
    # Layer 1: Energy above ambient (Plan 11)
    if not self._is_above_ambient(audio_frames):
        return False

    # Layer 2: Silero speech classification
    speech_prob = self.classifier.get_speech_probability(audio_frames, self.sample_rate)

    # Layer 3: Proximity heuristic (louder = closer = user)
    energy = calculate_rms_energy(audio_frames)
    proximity_bonus = max(0, (energy - self.ambient_baseline_db - 10) / 20)

    # Combined score
    final_score = speech_prob + (proximity_bonus * 0.2)

    return final_score > self.config.speech_classification_threshold
```

#### Phase 3: Configuration
```yaml
# New config options
speech_classifier_enabled: true
speech_classifier_backend: "silero"  # Options: silero, webrtcvad, hybrid
speech_classification_threshold: 0.6
speech_classifier_use_proximity: true
```

#### Phase 4: Lazy Loading for Pi Performance
```python
class SpeechClassifier:
    _instance = None

    def __init__(self, threshold=0.5):
        # ... (as shown in Phase 1)
        self.threshold = threshold

    @classmethod
    def get_instance(cls, threshold=0.5):
        """Lazy singleton to avoid loading model until needed."""
        if cls._instance is None:
            cls._instance = cls(threshold=threshold)
        return cls._instance
```

## Testing Strategy

### Unit Tests
- Test Silero model loads correctly
- Test speech probability output range
- Test fallback to webrtcvad if Silero unavailable

### Performance Tests
- Measure latency per frame on Mac
- Measure latency per frame on Pi
- Measure memory usage

### Accuracy Tests
- Test with clean speech → high probability
- Test with music → low probability
- Test with podcast → medium probability
- Test with speech over music → should detect foreground speech

## Success Criteria
- [ ] Silero VAD integrated and working
- [ ] Latency < 50ms per frame on Mac
- [ ] Latency < 100ms per frame on Pi (acceptable)
- [ ] Better accuracy than webrtcvad alone
- [ ] Graceful fallback if model unavailable

## Effort: Medium-High

## Dependencies
- torch (PyTorch) - may be heavy for Pi
- torchaudio (optional, for better audio handling)
- Plan 13 (VAD Robustness)
- Plan 14 (Energy Detection) - recommended

## Risks
1. **PyTorch on Pi**: May need lighter alternative (ONNX runtime)
2. **Model download**: First run downloads model from hub
3. **Memory usage**: Monitor RAM on Pi

## Alternatives if PyTorch Too Heavy
- Export Silero to ONNX, use onnxruntime
- Use TensorFlow Lite version if available
- Fall back to enhanced webrtcvad + energy detection

## Relationship
- Builds on: Plan 13, Plan 14
- This is the most advanced layer of noise filtering
