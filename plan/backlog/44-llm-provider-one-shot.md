# Plan 44: LLMProvider one_shot Method

## Problem

`VoiceFillerCache._translate_phrases()` needs a single-turn LLM call that does not
touch `AI.conversation_history`. Currently it bypasses the provider interface entirely:

```python
completion = self._ai.openai_client.chat.completions.create(
    model=self._config.gpt_response_model,
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

Implement by delegating to the existing `generate_response` with an empty history:

```python
def one_shot(self, prompt, model=None):
    return self.generate_response(prompt, [], model=model)
```

`generate_response` already handles an empty history correctly — it builds a messages
list with no prior turns and returns an `ErrorMessage`-compatible result on failure.

### `AI` facade (`common/ai.py`)

```python
def one_shot(self, prompt, model=None):
    """Single-turn LLM call that does not affect conversation history."""
    return self._llm.one_shot(prompt, model=model)
```

No history reads or writes. Return value is passed straight through to the caller.

## Acceptance Criteria

- [ ] `LLMProvider.one_shot(prompt, model=None)` abstract method added
- [ ] `OpenAILLMProvider.one_shot` implemented; delegates to `generate_response(prompt, [])`
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
