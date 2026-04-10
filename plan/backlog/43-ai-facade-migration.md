# Plan 43: AI Facade Migration

## Problem

After Plans 41 and 42, three OpenAI provider classes exist alongside the original `AI`
class, which still owns all the logic directly. This plan completes the migration:
`AI` becomes a thin facade that owns conversation history, delegates all capability calls
to provider instances, and exposes a factory (`AI.from_config`) that reads config to
pick and instantiate the right providers.

All call sites (`sandvoice.py`, `wake_word.py`, plugins, scheduler) remain unchanged —
`s.ai.generate_response(...)` still works.

## Goal

- `AI` owns `conversation_history` and delegates to `LLMProvider`, `TTSProvider`,
  `STTProvider`
- `AI.from_config(config)` is the standard constructor; the bare `AI(config)` constructor
  is removed or kept only for tests that pass providers directly
- Three new config keys (`llm_provider`, `tts_provider`, `stt_provider`) select the
  provider; all default to `openai`
- Duplicate logic in `ai.py` is deleted once providers own it

## Approach

### `AI` class redesign

```python
class AI:
    def __init__(self, llm: LLMProvider, tts: TTSProvider, stt: STTProvider, config):
        self.config = config
        self._llm = llm
        self._tts = tts
        self._stt = stt
        self.conversation_history = []

    @classmethod
    def from_config(cls, config):
        setup_error_logging(config)
        _check_api_key(config)  # validates OPENAI_API_KEY (or future provider keys)
        openai_client = OpenAI(timeout=config.api_timeout)
        llm = _build_llm_provider(config, openai_client)
        tts = _build_tts_provider(config, openai_client)
        stt = _build_stt_provider(config, openai_client)
        return cls(llm, tts, stt, config)
```

### Public API — unchanged for all callers

`AI` wraps provider calls and manages history:

```python
def generate_response(self, user_input, extra_info=None, model=None):
    user_message = "User: " + user_input
    if not self.conversation_history or self.conversation_history[-1] != user_message:
        self.conversation_history.append(user_message)
    result = self._llm.generate_response(
        user_input, self.conversation_history, extra_info=extra_info, model=model
    )
    self.conversation_history.append(f"{self.config.botname}: " + result.content)
    return result

def stream_response_deltas(self, user_input, extra_info=None, model=None):
    user_message = "User: " + user_input
    if not self.conversation_history or self.conversation_history[-1] != user_message:
        self.conversation_history.append(user_message)
    collected = []
    for piece in self._llm.stream_response_deltas(
        user_input, self.conversation_history, extra_info=extra_info, model=model
    ):
        collected.append(piece)
        yield piece
    self.conversation_history.append(f"{self.config.botname}: " + "".join(collected))

def text_to_speech(self, text, model=None, voice=None):
    return self._tts.text_to_speech(text, model=model, voice=voice)

def transcribe_and_translate(self, model=None, audio_file_path=None):
    return self._stt.transcribe(audio_file_path=audio_file_path, model=model)

def define_route(self, user_input, model=None, extra_routes=None):
    return self._llm.define_route(user_input, model=model, extra_routes=extra_routes)

def text_summary(self, user_input, extra_info=None, words="100", model=None):
    return self._llm.text_summary(user_input, extra_info=extra_info, words=words, model=model)
```

Note: `transcribe_and_translate` is kept as the public name (callers use this name) but
delegates to `stt.transcribe`.

### Provider factory helpers

```python
def _build_llm_provider(config, openai_client):
    provider = getattr(config, "llm_provider", "openai")
    if provider == "openai":
        return OpenAILLMProvider(openai_client, config)
    raise ValueError(f"Unknown llm_provider: {provider!r}")

def _build_tts_provider(config, openai_client): ...
def _build_stt_provider(config, openai_client): ...
```

Raising `ValueError` on unknown provider names fails fast at startup — better than
silent fallback to a wrong provider.

### New config keys

Add to `configuration.py` defaults and `load_config()`:

```python
"llm_provider": "openai",
"tts_provider": "openai",
"stt_provider": "openai",
```

No validation beyond the factory raise is needed for now (only `openai` is valid).

### Cleanup in `common/ai.py`

Once providers own all logic, remove from `AI`:
- Direct `openai.OpenAI` client construction (moves to `from_config`)
- `OPENAI_API_KEY` check (moves to `from_config`)
- All method bodies that now delegate to providers
- `setup_error_logging` call (stays in `from_config`)

Helpers that are not provider-specific remain in `ai.py`:
- `split_text_for_tts`, `pop_streaming_chunk` — pure text utilities used elsewhere
- `normalize_route_name`, `_normalize_route_response` — used in `define_route`
- `ErrorMessage` — used by tests and providers

## Acceptance Criteria

- [ ] `AI.from_config(config)` is the standard construction path; `sandvoice.py` and
      `wake_word.py` updated to call it
- [ ] `llm_provider`, `tts_provider`, `stt_provider` config keys added with `openai` default
- [ ] `conversation_history` lives on `AI`; provider methods do not own or mutate it
- [ ] Unknown provider name raises `ValueError` at startup (tested)
- [ ] All existing call sites (`sandvoice.py`, `wake_word.py`, plugins, scheduler,
      `_SchedulerContext`) work without modification beyond the construction call
- [ ] All existing tests pass; `test_ai.py` updated to use `AI(llm, tts, stt, config)`
      direct constructor with mock providers
- [ ] Coverage >80% for updated `ai.py`
- [ ] No OpenAI-specific code remains in `AI` (only in provider classes)

## Dependencies

- Plan 41 merged
- Plan 42 merged

## Notes

- `_SchedulerContext` in `scheduler.py` creates its own `AI` instance — it should also
  call `AI.from_config`; verify it still passes an isolated `conversation_history`
  (it does, because history is now on `AI`, not shared between instances)
- Keep `transcribe_and_translate` as the public name on `AI` to avoid touching all
  callers; the rename to `transcribe` is internal to the STT provider
- Do not add provider config keys for future providers in this plan — add them only
  when a second provider is implemented
