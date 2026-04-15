# Plan 44: LLMProvider one_shot Method

## Problem

`VoiceFillerCache._translate_phrases()` needs a single-turn LLM call that does not
touch `AI.conversation_history`. Currently it bypasses the provider interface entirely:

```python
completion = self._ai.openai_client.chat.completions.create(
    model=self._config.llm_response_model,
    messages=[{"role": "user", "content": prompt}],
)
```

This couples the module to the OpenAI SDK directly, which defeats the purpose of the
provider facade introduced in Plans 41–43.

`AI.generate_response()` cannot be used here because it appends both the user turn and
the assistant reply to `conversation_history`, contaminating the interactive session
with warmup data.

## Goal

Add a `one_shot(prompt, model=None)` method to `LLMProvider`, implement it in
`OpenAILLMProvider`, and expose it on `AI` — so callers can make a single-turn LLM
call without affecting conversation history.

## Approach

### `LLMProvider` ABC (`common/providers/base.py`)

```python
@abstractmethod
def one_shot(self, prompt, model=None):
    """Single-turn LLM call with no conversation history.

    Returns a response object with a `.content` attribute (str).
    Does not read or mutate any conversation state.
    """
```

### `OpenAILLMProvider` (`common/providers/openai_llm.py`)

Implement as a direct, minimal API call — **do not** delegate to `generate_response`.
`generate_response` injects the full SandVoice system role (including the
`"answer in {config.language}"` instruction) and wraps the user prompt as
`"User: {prompt}"`. These are the wrong semantics for a raw single-turn call: callers
like `voice_filler` supply a self-contained prompt that must not be overridden by the
SandVoice persona.

```python
@retry_with_backoff(max_attempts=3, initial_delay=1)
def _call_one_shot(self, prompt, model=None):
    if not model:
        model = self.config.llm_response_model
    completion = self._client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message

def one_shot(self, prompt, model=None):
    try:
        return self._call_one_shot(prompt, model=model)
    except Exception as e:
        error_msg = handle_api_error(e, service_name="OpenAI GPT")
        logger.error("one_shot error: %s", e)
        return ErrorMessage(error_msg)
```

### `AI` facade (`common/ai.py`)

```python
def one_shot(self, prompt, model=None):
    """Single-turn LLM call that does not affect conversation history."""
    return self._llm.one_shot(prompt, model=model)
```

No history reads or writes. Return value is passed straight through to the caller.

## Acceptance Criteria

- [ ] `LLMProvider.one_shot(prompt, model=None)` abstract method added
- [ ] `OpenAILLMProvider.one_shot` implemented as a direct, system-role-free API call (via `_call_one_shot` with `retry_with_backoff`); does **not** delegate to `generate_response`
- [ ] `AI.one_shot(prompt, model=None)` delegates to `self._llm.one_shot`
- [ ] Unit tests cover: successful call, API failure returns `ErrorMessage`-like result
- [ ] Coverage >80% for changed files

## Dependencies

- Plan 43 merged

## Notes

- `one_shot` intentionally has no `extra_info` parameter — it is for simple
  single-prompt calls. If a caller needs system context, pass it in the prompt string.
- The method name `one_shot` is preferred over `prompt` or `query` to make it clear
  that no history is involved.
