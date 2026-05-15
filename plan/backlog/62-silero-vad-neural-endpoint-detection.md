# Plan 62: Silero VAD — Neural End-of-Speech Detection

## Status: 📋 Backlog

## Problem Statement

WebRTC VAD is a rule-based model from ~2012. Even with the Plan 14 energy pre-filter
it can misfire in challenging acoustic conditions: TV dialogue at higher volumes,
another person speaking nearby, or music with speech-like frequency content. A neural
VAD model trained specifically to distinguish human speech from these noise sources
provides dramatically better accuracy.

## Goals

1. Replace the `webrtcvad.Vad.is_speech()` call with Silero VAD inference
2. Keep the Plan 14 energy pre-filter as the first-stage gate (cheap, always-on)
3. Maintain the same `VadRecorder` interface — no changes outside `vad_recorder.py`
   and `common/configuration.py`
4. Must run acceptably on Raspberry Pi 3B (benchmark target: ≤ 15ms per 30ms frame)
5. Graceful fallback to WebRTC VAD if the Silero model file cannot be loaded

## Background: Why Silero

| | WebRTC VAD | Silero VAD |
|---|---|---|
| Type | Rule-based (signal processing) | Neural LSTM |
| Model size | — (no file) | ~1.5 MB ONNX |
| False-positive rate (TV bg) | High | Low |
| Inference latency (Pi 3B) | ~0.1ms | ~5–12ms (to confirm) |
| Dependency | `webrtcvad` | `onnxruntime` (already installed) |

Silero VAD ships as an ONNX model, so `onnxruntime` — which is already a dependency
(via openWakeWord) — is the only inference runtime required.

## Technical Approach

### Model acquisition

Silero VAD v5 ONNX weights are available from the official repo. The model file
(`silero_vad.onnx`) should be bundled under `models/` alongside the existing wake
word model. At ~1.5 MB it is small enough to commit.

### Inference interface

Silero VAD is stateful — it maintains an internal LSTM hidden state across frames.
The state must be reset between utterances (i.e. at the start of each `record()` call).

```python
import onnxruntime as ort
import numpy as np

class SileroVad:
    def __init__(self, model_path, sample_rate=16000):
        self._session = ort.InferenceSession(model_path)
        self._sr = sample_rate
        self.reset()

    def reset(self):
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def is_speech(self, pcm: bytes) -> bool:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        out, self._h, self._c = self._session.run(
            None,
            {"input": samples[np.newaxis], "sr": np.array(self._sr), "h": self._h, "c": self._c},
        )
        return float(out[0]) >= 0.5   # threshold configurable
```

### Integration in VadRecorder

- `VadRecorder.__init__` checks config for `vad_engine: silero | webrtc` (default `webrtc`
  until benchmarked on Pi)
- If `silero`: load `SileroVad`; if load fails, log a warning and fall back to `webrtcvad`
- `is_speech` call site in `record()` becomes `self._vad.is_speech(pcm)` regardless of engine

### Configuration

```yaml
vad_engine: silero          # webrtc | silero (default: webrtc)
silero_model_path: ~/sandvoice/models/silero_vad.onnx
silero_speech_threshold: 0.5  # probability threshold (0.0–1.0)
```

## Implementation Plan

### Step 0 — Benchmark first
Before writing any production code, benchmark Silero inference on the Pi 3B:
- Script: `tools/benchmark_silero.py` — feed 1000 frames, measure p50/p99 latency
- Target: p99 ≤ 15ms per 30ms frame (so VAD overhead < 50% of frame time)
- If Pi cannot meet the target, this plan becomes macOS-only or deferred

### Step 1 — `models/silero_vad.onnx`
Download and commit the Silero VAD v5 ONNX weights.

### Step 2 — `common/silero_vad.py`
Implement `SileroVad` class (reset, is_speech). Unit tests with synthetic PCM.

### Step 3 — `common/vad_recorder.py`
- Add `vad_engine` config read in `__init__`
- Instantiate `SileroVad` or `webrtcvad.Vad` accordingly
- Normalise the call site: `is_speech = self._vad_is_speech(pcm)`
- On Silero load failure: warn and fall back to WebRTC

### Step 4 — `common/configuration.py`
- Add `vad_engine` (default `"webrtc"`), `silero_model_path`, `silero_speech_threshold`
- Validate: `vad_engine` in `{"webrtc", "silero"}`; threshold in (0.0, 1.0)

### Step 5 — Tests
- Test `SileroVad.reset()` zeroes state
- Test probability threshold gating
- Test fallback: if model path invalid, `VadRecorder` uses WebRTC
- Benchmark script in `tools/`

### Step 6 — Docs
- Update README config table
- Note Pi 3B benchmarks in plan doc after measuring

## Success Criteria

- [ ] TV at background volume no longer keeps the VAD loop open
- [ ] Inference p99 latency ≤ 15ms per frame on Pi 3B (or plan scoped to macOS)
- [ ] WebRTC fallback works when model file is missing
- [ ] `vad_engine: webrtc` restores previous behavior exactly
- [ ] >80% test coverage on `common/silero_vad.py`

## Effort: Medium

## Dependencies

- Plan 14 (Adaptive Energy Pre-Filter) — prerequisite; energy gate stays as first stage
- `onnxruntime` — already installed (via openWakeWord)
- Silero VAD v5 ONNX weights — ~1.5 MB, to be committed to `models/`

## Relationship

- Supersedes dropped Plan 15 (Speech Classification / ML VAD) — same goal, but
  `onnxruntime` is already a dependency so there is no new install requirement;
  Pi 3B viability needs a fresh benchmark with the actual ONNX runtime
- Builds on: Plan 14 (energy gate remains as cheap first-stage filter)
