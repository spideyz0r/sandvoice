# Plan 46: Remove openai_client Escape Hatch

## Problem

`AI` exposes a public `openai_client` property that lets callers bypass the provider
interface entirely:

```python
@property
def openai_client(self):
    if self._openai_client is None:
        raise AttributeError(
            "openai_client is not available: AI was not constructed via "
            "from_config, or the configured provider does not use an OpenAI client."
        )
    return self._openai_client
```

Two callers depend on it:

| Caller | What it does |
|--------|-------------|
| `common/voice_filler.py` | Single-turn LLM call for phrase translation |
| `plugins/realtime_websearch/plugin.py` | Responses API web search call |

Both have proper provider-level solutions in Plans 44 and 45. Once those are in place,
the escape hatch serves no purpose and should be removed.

## Goal

Migrate both callers to use the new provider methods, then delete `openai_client` from
`AI` and `_openai_client` from `AI.__init__`. No caller should reference the OpenAI
SDK directly outside of `common/providers/`.

## Approach

### `common/voice_filler.py`

Replace:
```python
completion = self._ai.openai_client.chat.completions.create(
    model=self._config.gpt_response_model,
    messages=[{"role": "user", "content": prompt}],
)
raw = completion.choices[0].message.content.strip()
```

With:
```python
result = self._ai.one_shot(prompt, model=self._config.gpt_response_model)
raw = result.content.strip()
```

### `plugins/realtime_websearch/plugin.py`

Replace:
```python
resp = s.ai.openai_client.responses.create(
    model=...,
    instructions=system_instructions,
    tools=[{"type": "web_search"}],
    tool_choice="auto",
    input=query,
    include=include_params,
)
text = resp.output_text or "..."
```

With:
```python
resp = s.ai.web_search(
    query,
    instructions=system_instructions,
    model=getattr(s.config, 'gpt_response_model', None) or "gpt-5-mini",
    include=include_params,
)
text = resp.output_text or "..."
```

The debug source-printing block that inspects `resp.output` stays in the plugin —
it is presentation logic, not provider logic.

### `common/ai.py`

Remove:
- `self._openai_client = openai_client` from `AI.__init__`
- `openai_client` keyword-only parameter from `AI.__init__`
- `openai_client` property
- `openai_client=openai_client` kwarg from `cls(...)` call in `from_config`

`from_config` still constructs the client locally and passes it to the three
`_build_*_provider` helpers — that is an implementation detail of the factory, not
part of the public AI interface.

### Tests

- Update `tests/test_ai.py`: remove `test_openai_client_accessible_after_from_config`
  and `test_openai_client_raises_when_not_set` (the property no longer exists).
- Update any tests that directly access or mock `ai.openai_client` to use the
  provider-backed interface instead: `tests/test_ai.py` (remove the two
  `openai_client` property tests), `tests/test_voice_filler.py` (mock `ai.one_shot`
  instead of `ai.openai_client.chat.completions.create`).
- Update `tests/test_realtime_websearch_plugin.py` to mock `s.ai.web_search`
  instead of `sv.ai.openai_client.responses.create`.

## Acceptance Criteria

- [ ] `voice_filler.py` uses `ai.one_shot(prompt, model=...)` — no `openai_client` reference
- [ ] `realtime_websearch/plugin.py` uses `s.ai.web_search(...)` — no `openai_client` reference
- [ ] `AI.openai_client` property removed
- [ ] `AI._openai_client` attribute removed
- [ ] No `openai_client` keyword in `AI.__init__` or `AI.from_config`
- [ ] No plugin or `AI` instance method imports or references the `openai` SDK directly;
      `AI.from_config` (the provider wiring point) may retain `from openai import OpenAI`
- [ ] All tests pass; removed tests replaced with ones targeting the new interface
- [ ] Coverage >80% for changed files

## Dependencies

- Plan 44 merged
- Plan 45 merged

## Notes

- `from openai import OpenAI` remains in `common/ai.py` inside `from_config` — this
  is the intentional provider wiring point. The constraint is that no *instance method*
  of `AI` and no *plugin* touches the SDK directly.
- After this plan, adding a non-OpenAI provider requires only implementing the
  `LLMProvider` ABC — no plugins or `voice_filler.py` need changes.
