# Plan 45: LLMProvider web_search Method

## Problem

`plugins/realtime_websearch/plugin.py` calls the OpenAI Responses API directly:

```python
resp = s.ai.openai_client.responses.create(
    model=...,
    instructions=system_instructions,
    tools=[{"type": "web_search"}],
    tool_choice="auto",
    input=query,
    include=include_params,
)
```

This bypasses the provider interface, couples the plugin to the OpenAI SDK, and relies
on the `openai_client` escape hatch on `AI` that should be removed (Plan 46).

## Goal

Add `web_search(query, instructions, model=None, include=None)` to `LLMProvider`,
implement it in `OpenAILLMProvider` using the Responses API, and expose it on `AI` —
so plugins call `s.ai.web_search(...)` with no knowledge of the underlying SDK.

## Approach

### `LLMProvider` ABC (`common/providers/base.py`)

```python
@abstractmethod
def web_search(self, query, instructions, model=None, include=None):
    """Answer a query using a web-search-augmented LLM call.

    Args:
        query: The user question to search for.
        instructions: System-level instructions for the response style.
        model: Override the default model. Provider picks a default when None.
        include: Optional list of provider-specific include flags
                 (e.g. ["web_search_call.action.sources"] for debugging).

    Returns:
        A result object with at minimum an `.output_text` attribute (str).
        Returns a fallback result with a user-friendly error message on failure.
    """
```

### `OpenAILLMProvider` (`common/providers/openai_llm.py`)

Move the `responses.create` call from the plugin into the provider:

```python
@retry_with_backoff(max_attempts=3, initial_delay=1)
def _call_web_search(self, query, instructions, model=None, include=None):
    if not model:
        model = self.config.gpt_response_model
    return self._client.responses.create(
        model=model,
        instructions=instructions,
        tools=[{"type": "web_search"}],
        tool_choice="auto",
        input=query,
        include=include or [],
    )

def web_search(self, query, instructions, model=None, include=None):
    try:
        return self._call_web_search(
            query, instructions, model=model, include=include
        )
    except Exception as e:
        error_msg = handle_api_error(e, service_name="OpenAI web search")
        logger.error("Web search error: %s", e)
        print(error_msg)
        return _WebSearchErrorResult(
            output_text="I encountered an error while searching the web. Please try again."
        )
```

`_WebSearchErrorResult` is a namedtuple defined at module level in `openai_llm.py`:

```python
from collections import namedtuple
_WebSearchErrorResult = namedtuple("_WebSearchErrorResult", ["output_text"])
```

Using the named field (`output_text=...`) in the constructor makes the `.output_text`
contract explicit and avoids positional-argument ambiguity.

### `AI` facade (`common/ai.py`)

```python
def web_search(self, query, instructions, model=None, include=None):
    """Web-search-augmented LLM call. Does not affect conversation history."""
    return self._llm.web_search(
        query, instructions, model=model, include=include
    )
```

## Acceptance Criteria

- [ ] `LLMProvider.web_search(query, instructions, model=None, include=None)` abstract method added
- [ ] `OpenAILLMProvider.web_search` implemented with `retry_with_backoff`, error handling, and consistent return interface (both success and failure paths expose `.output_text`)
- [ ] `_WebSearchErrorResult` (or equivalent) returns a user-friendly `.output_text` on failure
- [ ] `AI.web_search(...)` delegates to `self._llm.web_search`
- [ ] Unit tests cover: successful call, API failure returns error result with `.output_text`
- [ ] Coverage >80% for changed files

## Dependencies

- Plan 43 merged

## Notes

- `web_search` does not append to `conversation_history` — the plugin is responsible
  for deciding what (if anything) to include in the response returned to the user.
- The `include` parameter is intentionally generic; callers pass provider-specific
  values and the provider uses them as-is. This avoids over-abstracting a debug feature.
- When a second search provider is added, the return type contract (`output_text`)
  should be formalised into a `SearchResult` dataclass shared across providers.
