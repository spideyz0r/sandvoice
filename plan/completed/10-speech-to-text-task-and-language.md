# Speech-to-Text: Transcribe vs Translate (Configurable)

**Status**: 📋 Backlog
**Priority**: 10
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

SandVoice currently uses Whisper "translations" which always returns English text. This is surprising for non-English voice-first usage (e.g., PT-BR): the user speaks Portuguese but the printed transcription becomes English.

This feature makes speech-to-text behavior explicit and configurable:
- **transcribe**: keep the original spoken language
- **translate**: convert speech to English

It also adds an explicit language hint option for better accuracy when transcribing.

---

## Problem Statement

Current behavior:
- Speech-to-text uses Whisper translations endpoint
- Output is always English

Issues:
- Users who speak PT-BR expect the transcription to remain PT-BR
- Route selection and plugin queries can behave differently depending on whether the input was translated

---

## Goals

- Voice-first: preserve the user’s spoken language when desired
- Make speech-to-text behavior explicit and predictable
- Support language hints (ISO-639-1) to improve recognition
- Keep compatibility with existing workflows (English users can keep translate)

---

## Non-Goals

- Full multilingual routing policies
- Automatic language detection policies beyond what Whisper already does

---

## Proposed Configuration

```yaml
# Speech-to-text
speech_to_text_model: whisper-1

# translate: output English
# transcribe: output original language
speech_to_text_task: transcribe

# Optional ISO-639-1 language hint (e.g. pt, en). Empty means auto-detect.
speech_to_text_language: pt

# When task=translate, choose provider:
# - whisper: Whisper translations endpoint
# - gpt: transcribe (optionally with language hint) then translate via GPT
speech_to_text_translate_provider: whisper

# When provider=gpt
speech_to_text_translate_model: gpt-5-mini
```

---

## Implementation Notes

- If `speech_to_text_task=transcribe`:
  - use Whisper transcriptions endpoint
  - pass `language` only when `speech_to_text_language` is set

- If `speech_to_text_task=translate`:
  - if `speech_to_text_translate_provider=whisper`: use Whisper translations endpoint (single call)
  - if `speech_to_text_translate_provider=gpt`: transcribe first (with optional language hint) then translate to English using `speech_to_text_translate_model`

---

## Acceptance Criteria

- [ ] Setting `speech_to_text_task=transcribe` returns speech-to-text output in the spoken language
- [ ] Setting `speech_to_text_task=translate` returns English output
- [ ] Setting `speech_to_text_language` improves transcription accuracy for known languages
- [ ] Defaults preserve existing behavior (English translation)

---

## Testing

- Unit tests for config validation of new keys
- Unit tests for `AI.transcribe_and_translate()` selecting the correct endpoint/provider
