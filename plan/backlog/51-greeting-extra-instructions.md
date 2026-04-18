# Plan 51: Greeting Plugin — Extra Instructions

## Problem

The greeting plugin generates a fixed-structure greeting (time-of-day salutation,
weather comment, fun fact). Users have no way to customise it — for example,
adding a proverb, a motivational quote, a joke, or any other standing element —
without editing the plugin source.

## Goal

Add an optional `greeting_extra` config key that appends user-defined instructions
to the greeting generation prompt. The base greeting structure instructions remain
in the prompt, but `greeting_extra` may influence the generated content or
formatting.

## Config

```yaml
# Optional: append custom instructions to every generated greeting.
# Supports YAML block scalar for multi-line text.
# greeting_extra: |
#   End the greeting with a short, relevant proverb.
# greeting_extra: "Include a motivational quote to start the day."
```

Default: absent / `None` (no injection).

## Implementation

### `common/configuration.py`

Add `greeting_extra` to the defaults dict (`None`) and parse it in `load_config()`
following the existing `Config` pattern: read the raw value, accept only strings
that remain non-empty after `strip()`, and store the stripped value on the config
object. For blank or non-string values, log a warning and normalise to `None`.
`validate_config()` should not hard-fail on an invalid optional `greeting_extra`
value.

### `plugins/greeting/plugin.py`

Append `greeting_extra` to `extra_system` before the `generate_response` call:

```python
greeting_extra = getattr(s.config, "greeting_extra", None)
if greeting_extra and isinstance(greeting_extra, str) and greeting_extra.strip():
    extra_system = extra_system + greeting_extra.strip() + "\n"
    logger.debug("greeting_extra active (%d chars)", len(greeting_extra.strip()))
```

The `extra_system` string already contains the weather info and time-of-day
instructions; `greeting_extra` is appended at the end so it has the highest
priority in the prompt.

### Cache interaction

`greeting_extra` is part of the generated text. If the user changes
`greeting_extra`, the existing cache entry will be stale (it was generated with
the old instructions). The cache TTL will eventually expire it naturally.
A future improvement could invalidate the cache on config change, but this is out
of scope here.

### `config.yaml`

Add the commented-out example above so users can discover the option.

## Acceptance Criteria

- [ ] `greeting_extra` absent → greeting prompt unchanged
- [ ] `greeting_extra` set → text appended to `extra_system` before LLM call
- [ ] Blank / whitespace-only value treated as absent (warning logged in config)
- [ ] Non-string value treated as absent (warning logged in config)
- [ ] `tests/test_greeting_plugin.py` updated: extra instruction appended to
      prompt, absent when not configured, blank value skipped
- [ ] `tests/test_configuration.py` updated: valid value, blank value,
      non-string value
- [ ] `config.yaml` updated with commented-out example

## Notes

- `greeting_extra` affects only the greeting plugin's live generation prompt.
  It is separate from `system_prompt_extra` (which affects every request).
  Users can set both simultaneously.
- Cache invalidation on config change is a known limitation; users can manually
  clear the cache if they want the new instructions to apply immediately. This
  could be addressed in a future plan.
- Do not put secrets, API keys, or personally identifiable information (PII) in
  `greeting_extra`. The value is appended to the greeting prompt and sent to the
  LLM provider verbatim, where it will appear in API logs.
- Custom instructions can compete with or partially override the default greeting
  structure. This is intentional; users take responsibility for the interaction.
