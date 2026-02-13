# Plan 13: VAD Robustness - Timeout and Tuning

**Status**: 📋 Backlog
**Priority**: 13
**Platforms**: macOS, Raspberry Pi

---

## Problem Statement
When background audio is present (music, podcasts, TV), the VAD keeps listening indefinitely because it detects continuous sound as "speech activity." Users have to manually interrupt or the system hangs.

## Goals
1. Ensure `vad_timeout` is enforced and working correctly
2. Add visual feedback when approaching timeout
3. Expose additional VAD tuning options for noisy environments
4. Add environment presets (quiet, noisy, very_noisy)

## Current State
- `vad_timeout: 30` exists in config
- `vad_aggressiveness: 3` is at maximum
- `vad_silence_duration: 1.5` seconds
- No visual indicator of recording duration

## Implementation

### Phase 1: Validate Timeout Enforcement
- Audit `_state_listening()` - verify timeout checked every frame
- Add debug logging when timeout reached
- Ensure clean transition to PROCESSING on timeout

### Phase 2: Visual Feedback
- Show elapsed recording time in terminal
- Warning when approaching timeout (last 5 seconds)
- Clear message: "Recording timeout reached"

### Phase 3: Additional Config Options
```yaml
vad_speech_ratio_threshold: 0.3  # Min ratio of speech frames
vad_min_speech_duration: 0.5     # Min seconds before allowing stop
```

### Phase 4: Environment Presets
```yaml
vad_preset: "default"  # Options: default, quiet, noisy, very_noisy
```

## Success Criteria
- [ ] Timeout always enforced
- [ ] Visual indicator shows recording duration
- [ ] Presets work correctly

## Effort: Small-Medium

## Dependencies
None - builds on existing VAD infrastructure

## Relationship
- Prerequisite for: Plan 14, Plan 15
