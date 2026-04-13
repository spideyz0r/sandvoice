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

Copy the body of `OpenAILLMProvider._build_system_role()` verbatim into a module-level
function, replacing `self.config` with `config`:

```python
import datetime

def build_system_role(config, extra_info=None):
    """Build the SandVoice system prompt from config.

    Returns a string suitable for use as the system role in any LLM API call.
    Provider-agnostic — contains only application-level instructions.
    """
    now = datetime.datetime.now()
    verbosity = getattr(config, "verbosity", "brief")

    if verbosity == "detailed":
        verbosity_instruction = (
            "Verbosity: detailed. Provide thorough, structured answers by default. "
            "Include steps/examples when helpful. If the user asks for a short answer, comply."
        )
    elif verbosity == "normal":
        verbosity_instruction = (
            "Verbosity: normal. Be concise but complete. "
            "Expand when the user explicitly asks for more detail."
        )
    else:
        verbosity_instruction = (
            "Verbosity: brief. Keep answers short by default (1-3 sentences). "
            "Avoid long lists and excessive detail unless the user explicitly asks to expand, "
            "asks for details, or says they want a longer answer."
        )

    system_role = f"""
        Your name is {config.botname}.
        You are an assistant written in Python by Breno Brand.
        You must answer in {config.language}.
        The person that is talking to you is in the {config.timezone} time zone.
        The person that is talking to you is located in {config.location}.
        Current date and time to be considered when answering the message: {now}.
        Never answer as a chat, for example reading your name in a conversation.
        DO NOT reply to messages with the format "{config.botname}": <message here>.
        Reply in a natural and human way.
        {verbosity_instruction}
        """

    if extra_info is not None:
        system_role = system_role + "Consider the following to answer your question: " + extra_info

    return system_role
```

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
- [ ] All existing tests pass unchanged (the output of `_build_system_role` is identical)
- [ ] `tests/test_prompt.py` added: covers verbosity variants (brief/normal/detailed),
      `extra_info` appended correctly, `None` extra_info omitted
- [ ] Coverage >80% for `common/prompt.py`

## Dependencies

- None (purely additive refactor, no plan dependencies)

## Notes

- `build_system_role` is a pure function — it reads config values and returns a string.
  No side effects, easy to test in isolation.
- The `text_summary` system role in `OpenAILLMProvider` ("You are a bot that summarizes
  texts in N words.") is intentionally NOT moved — it is a task-specific prompt, not
  the SandVoice persona.
- The routing system role (from `routes.yaml`) is also NOT moved — it is routing
  configuration, not persona.
