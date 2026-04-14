# Plan 47: Extract System Prompt to common/prompt.py

## Problem

`OpenAILLMProvider._build_system_role()` contains the core SandVoice persona and
conversation instructions assembled from configuration values (bot identity, language,
timezone/location, verbosity, and a formatting constraint not to reply as a chat).

None of this is OpenAI-specific. It is the application-level identity of SandVoice —
persona, language, timezone, verbosity. Any future provider (Gemini, Anthropic, etc.)
would need the identical prompt, forcing either duplication or inheritance from
`OpenAILLMProvider`.

The implementation in `common/providers/openai_llm.py` is the source of truth for the
exact prompt text. This plan must preserve it exactly.

## Goal

Move `_build_system_role` logic into a standalone `build_system_role(config,
extra_info=None)` function in `common/prompt.py`. Each provider that needs a system
role calls this shared function. `OpenAILLMProvider` becomes a thin caller.

## Approach

### New file: `common/prompt.py`

Copy the body of `OpenAILLMProvider._build_system_role()` into a module-level
function with only the minimal `self.config` → `config` substitution needed for
the extraction; otherwise preserve the logic and prompt text exactly — including
the leading/trailing whitespace inside the triple-quoted `system_role` f-string,
which is part of the prompt text and must not be "cleaned up" during the move.

**Do not rely on the snippet below for exact indentation or content.** The snippet
is illustrative only. The source of truth is `common/providers/openai_llm.py` at
implementation time — copy/paste the f-string directly from that file.

The prompt text must match `openai_llm.py` exactly at the time of implementation —
check for any instructions added by later PRs (e.g. PR #127) and include them.

### `OpenAILLMProvider` (`common/providers/openai_llm.py`)

Replace `_build_system_role` with a one-line delegation:

```python
from common.prompt import build_system_role

class OpenAILLMProvider(LLMProvider):
    def _build_system_role(self, extra_info=None):
        return build_system_role(self.config, extra_info=extra_info)
```

The private method is kept as a thin wrapper so the call sites inside
`OpenAILLMProvider` (`generate_response`, `stream_response_deltas`) don't need to
change.

### Future providers

Any future `GeminiLLMProvider`, `AnthropicLLMProvider`, etc. imports and calls
`build_system_role(self.config, extra_info=extra_info)` directly — no inheritance
from `OpenAILLMProvider` required.

## Acceptance Criteria

- [ ] `common/prompt.py` created with `build_system_role(config, extra_info=None)`
- [ ] `OpenAILLMProvider._build_system_role` delegates to `build_system_role`; no
      prompt logic remains in `openai_llm.py`
- [ ] All existing tests pass unchanged (the output of `_build_system_role` is identical,
      including leading/trailing whitespace in the f-string)
- [ ] `tests/test_prompt.py` added: covers verbosity variants (brief/normal/detailed),
      `extra_info` appended correctly, `None` extra_info omitted; assertions use exact
      string equality (not `assertIn`) to catch accidental whitespace changes; patch
      `datetime.datetime.now` to a fixed value so assertions are deterministic
- [ ] Coverage >80% for `common/prompt.py`

## Dependencies

- None (purely additive refactor, no plan dependencies)

## Notes

- `build_system_role` reads config values and returns a string. It calls
  `datetime.datetime.now()` internally, so it is time-dependent (not strictly pure),
  but it has no other side effects. Tests must patch `datetime.datetime.now` to a
  fixed value to get deterministic output.
- The `text_summary` system role in `OpenAILLMProvider` ("You are a bot that summarizes
  texts in N words.") is intentionally NOT moved — it is a task-specific prompt, not
  the SandVoice persona.
- The routing system role (from `routes.yaml`) is also NOT moved — it is routing
  configuration, not persona.
