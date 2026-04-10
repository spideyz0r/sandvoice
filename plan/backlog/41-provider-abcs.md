# Plan 41: Provider Interface ABCs

## Problem

`common/ai.py` wraps OpenAI directly — `openai.OpenAI` is the only client ever
instantiated. Every capability (text generation, TTS, STT) shares a single class and
a single provider. Swapping any one capability for a different service (e.g. a local
TTS engine on the Pi, a self-hosted STT model, an alternative LLM) requires forking the
entire `AI` class rather than replacing one component.

## Goal

Define three abstract base classes that describe the capability contracts for LLM, TTS,
and STT. No existing code is changed in this plan — the ABCs are additive. Future plans
implement these interfaces and wire them into `AI`.

## Approach

### New module: `common/providers/base.py`

Three ABCs, one per capability:

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
        """Return a response object with a `.content` attribute (str)."""

    @abstractmethod
    def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
        """Yield str deltas from the LLM stream."""

    @abstractmethod
    def define_route(self, user_input, model=None, extra_routes=None):
        """Return a route dict: {"route": str, "reason": str}."""

    @abstractmethod
    def text_summary(self, user_input, extra_info=None, words="100", model=None):
        """Return a summary dict: {"title": str, "text": str}."""


class TTSProvider(ABC):
    @abstractmethod
    def text_to_speech(self, text, model=None, voice=None) -> list:
        """Convert text to audio. Return a list of audio file paths (str)."""


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_file_path=None, model=None) -> str:
        """Transcribe audio file to text.

        If `audio_file_path` is None, use the configured temporary recording path.
        Return the transcript string.
        """
```

### New file: `common/providers/__init__.py`

Export the three ABCs for clean imports:

```python
from common.providers.base import LLMProvider, TTSProvider, STTProvider

__all__ = ["LLMProvider", "TTSProvider", "STTProvider"]
```

### Conversation history ownership

`LLMProvider` methods receive `conversation_history` as a parameter — the list is owned
by the caller (`AI` in Plan 43), not by the provider. This allows:

- Providers to remain stateless (no `self.conversation_history`)
- Swapping providers mid-session without losing history
- Scheduler to pass an isolated history (or empty list) without affecting interactive history

### Notes on the `generate_response` return type

The current `AI.generate_response` returns either a `completion.choices[0].message`
object (OpenAI SDK) or a `SimpleNamespace(content=...)`, both accessed via `.content`.
The ABC codifies `.content` as the contract — providers must return an object with a
string `.content` attribute, or a plain `SimpleNamespace`.

## Acceptance Criteria

- [ ] `common/providers/__init__.py` and `common/providers/base.py` exist
- [ ] `LLMProvider`, `TTSProvider`, `STTProvider` are importable from `common.providers`
- [ ] All three classes are ABCs: instantiating without implementing all abstract methods
      raises `TypeError`
- [ ] Tests cover ABC enforcement for each class
- [ ] No existing files are modified
- [ ] Coverage >80% for the new module

## Dependencies

None — this plan is purely additive.

## Notes

- Keep `base.py` minimal: only the interface, no helper code
- Do not add provider-specific imports to `base.py`
- Plan 42 implements the OpenAI providers; Plan 43 wires them into `AI`
