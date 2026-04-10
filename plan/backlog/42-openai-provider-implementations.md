# Plan 42: OpenAI Provider Implementations

## Problem

Plan 41 defines the three provider ABCs. This plan implements them for OpenAI — moving
the existing logic from `AI` into dedicated provider classes. The `AI` class is **not
changed** in this plan; the new providers coexist with the existing class and are not
yet wired in. This keeps the PR small and reviewable independently.

## Goal

Create `OpenAILLMProvider`, `OpenAITTSProvider`, and `OpenAISTTProvider` — each
implementing the matching ABC from Plan 41. All OpenAI-specific logic lives in these
classes after this plan; Plan 43 removes the duplicate from `AI`.

## Approach

### `common/providers/openai_llm.py` — `OpenAILLMProvider`

Implements `LLMProvider`. Receives `openai_client` and `config` in `__init__`.

**Key differences from the current `AI` methods:**

- No `self.conversation_history` — history is passed in as a parameter to each method.
  Methods do not mutate the list; the caller (`AI` in Plan 43) appends turns.
- `generate_response` and `stream_response_deltas` build the system prompt internally
  (same logic as today). The verbosity instruction and system role template move here.
- `define_route` reads `routes.yaml` path from config (same as today).
- `text_summary` is unchanged in logic.

```python
class OpenAILLMProvider(LLMProvider):
    def __init__(self, openai_client, config):
        self._client = openai_client
        self._config = config

    def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
        ...

    def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
        ...

    def define_route(self, user_input, model=None, extra_routes=None):
        ...

    def text_summary(self, user_input, extra_info=None, words="100", model=None):
        ...
```

### `common/providers/openai_tts.py` — `OpenAITTSProvider`

Implements `TTSProvider`. Receives `openai_client` and `config`.

Logic moved verbatim from `AI._generate_tts_files` and `AI.text_to_speech`. The
`@retry_with_backoff` decorator stays on `_generate_tts_files`.

```python
class OpenAITTSProvider(TTSProvider):
    def __init__(self, openai_client, config):
        self._client = openai_client
        self._config = config

    def text_to_speech(self, text, model=None, voice=None) -> list:
        ...

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def _generate_tts_files(self, text, model, voice):
        ...
```

### `common/providers/openai_stt.py` — `OpenAISTTProvider`

Implements `STTProvider`. Receives `openai_client` and `config`.

`transcribe_and_translate` is renamed to `transcribe` to match the ABC. All existing
logic (task=transcribe/translate, language_hint, translate_provider, translate_model)
is preserved unchanged.

```python
class OpenAISTTProvider(STTProvider):
    def __init__(self, openai_client, config):
        self._client = openai_client
        self._config = config

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def transcribe(self, audio_file_path=None, model=None) -> str:
        ...
```

### `common/providers/__init__.py` — updated

Add the OpenAI implementations to the module exports:

```python
from common.providers.base import LLMProvider, TTSProvider, STTProvider
from common.providers.openai_llm import OpenAILLMProvider
from common.providers.openai_tts import OpenAITTSProvider
from common.providers.openai_stt import OpenAISTTProvider

__all__ = [
    "LLMProvider", "TTSProvider", "STTProvider",
    "OpenAILLMProvider", "OpenAITTSProvider", "OpenAISTTProvider",
]
```

### `common/ai.py` — unchanged

The existing `AI` class continues to work as before. The providers exist in parallel.
Duplication is intentional and temporary — Plan 43 removes it.

## Acceptance Criteria

- [ ] `OpenAILLMProvider`, `OpenAITTSProvider`, `OpenAISTTProvider` each implement their
      ABC without `TypeError`
- [ ] Provider classes are importable from `common.providers`
- [ ] No existing files are modified
- [ ] Full test coverage (>80%) for all three provider classes using mocked `openai_client`
- [ ] Tests verify that conversation history is not mutated by provider methods
- [ ] Existing `tests/test_ai.py` suite still passes unchanged

## Dependencies

- Plan 41 merged

## Notes

- Do not add `OPENAI_API_KEY` validation inside providers — that belongs in the factory
  (`AI.from_config`) in Plan 43
- Retry decorator stays on the methods where it lives today
- `split_text_for_tts`, `pop_streaming_chunk`, `ErrorMessage`, `_normalize_route_response`,
  and `normalize_route_name` remain in `common/ai.py` for now; Plan 43 decides whether
  to move or import them
