# Plan 50: system_prompt_extra — User-Defined Standing Instructions

## Problem

The SandVoice persona is entirely defined in `common/prompt.py`. Users who want
to customise it (e.g. "always respond formally", "you are a cooking expert",
"never recommend products by brand name") currently have no way to do so without
editing source code.

## Goal

Add an optional `system_prompt_extra` config key that appends a block of
user-defined text to the system prompt on every request. The existing persona is
never replaced — the extra text is purely additive.

## Config

```yaml
# Optional: append custom standing instructions to every system prompt.
# Supports YAML block scalar for multi-line text.
# system_prompt_extra: |
#   Always respond in a formal tone.
#   You are an expert in Brazilian cuisine.
#   Never recommend products by brand name.
```

Default: absent / `None` (no injection).

## Implementation

### `common/configuration.py`

Add `system_prompt_extra` to the defaults dict (`None`) and expose it as a
config property. Validate: if present, must be a non-empty string after
stripping whitespace; log a warning and treat as absent if the value is
blank or not a string.

### `common/prompt.py` — `build_system_role`

Append `system_prompt_extra` between the base persona block and `extra_info`:

```python
if getattr(config, "system_prompt_extra", None):
    system_role = system_role + config.system_prompt_extra.strip() + "\n"
if extra_info is not None:
    system_role = system_role + "Consider the following to answer your question: " + extra_info
```

Prompt hierarchy (bottom of the system role, top to bottom):

1. Core persona (botname, language, timezone, location, verbosity)
2. `system_prompt_extra` — standing user customisation
3. `extra_info` — per-request runtime context (weather, news, etc.)

Log at DEBUG when active:

```python
logger.debug("system_prompt_extra active (%d chars)", len(config.system_prompt_extra.strip()))
```

### `config.yaml`

Add the commented-out example above so users can discover the option.

## Acceptance Criteria

- [ ] `system_prompt_extra` absent → prompt unchanged
- [ ] `system_prompt_extra` set → text appended between persona and `extra_info`
- [ ] Blank / whitespace-only value treated as absent (warning logged)
- [ ] Non-string value treated as absent (warning logged)
- [ ] Both `system_prompt_extra` and `extra_info` present → both appended in order
- [ ] `tests/test_prompt.py` updated with cases for the above
- [ ] `tests/test_configuration.py` updated: valid value, blank value, non-string value
- [ ] `config.yaml` updated with commented-out example

## Notes

- `system_prompt_extra` is a standing configuration — it applies to every
  request. Per-request context remains in `extra_info` (passed by plugins).
- No changes to `OpenAILLMProvider` or call sites — `build_system_role` is the
  only place to update.
