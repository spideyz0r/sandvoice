# Plan 48: Rename gpt_*_model Config Keys to llm_*_model

## Problem

Three config keys were named after the vendor (OpenAI/GPT):

- `gpt_response_model`
- `gpt_route_model`
- `gpt_summary_model`

These names are misleading now that the provider facade (Plans 41–43) makes the
LLM layer provider-agnostic. A user switching to a Gemini or Anthropic provider
would still see `gpt_response_model` in their `config.yaml`, which implies
OpenAI-only.

## Goal

Rename to provider-agnostic equivalents:

- `gpt_response_model` → `llm_response_model`
- `gpt_route_model` → `llm_route_model`
- `gpt_summary_model` → `llm_summary_model`

## Changes

- `common/configuration.py` — defaults dict + `load_config` properties
- `common/providers/openai_llm.py` — three `config.*_model` reads
- `common/voice_filler.py` — `config.gpt_response_model` in `_translate_phrases`
- `common/wake_word.py` — logging of route model name
- `plugins/realtime_websearch/plugin.py` — docstring + model read
- `README.md` — example config block
- `docs/PATTERNS.md` — example config in patterns reference
- `plan/backlog/44-llm-provider-one-shot.md` — code snippets
- `plan/backlog/45-llm-provider-web-search.md` — code snippets
- `plan/backlog/46-remove-openai-client-escape-hatch.md` — code snippets
- `tests/test_openai_providers.py`, `test_voice_filler.py`,
  `test_wake_word.py`, `test_realtime_websearch_plugin.py` — fixture config

## Notes

- Breaking change for existing `config.yaml` files — rename the keys manually.
- No backward-compatibility shim: this is a personal project with a single deployer.
- All 928 tests pass after the rename.
