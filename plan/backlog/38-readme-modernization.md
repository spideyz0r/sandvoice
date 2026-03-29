# Plan 38: README Modernization

**Status**: 📋 Backlog
**Priority**: 38
**Platforms**: n/a (documentation)

---

## Problem Statement

The current README is outdated and reads like a changelog rather than a project page. Specific issues:

- Entire plugin section describes the old single-file approach (`plugins/weather.py` + manual `routes.yaml` edit) — the new folder/manifest system is not documented at all
- No quick demo or terminal output example — readers can't tell at a glance what the experience is like
- Config reference is a single 80-key bullet dump — no structure, no "here's the minimum you need"
- Tone is dry and AI-sounding: passive voice, no personality, reads like internal docs
- Some config keys removed in Plan 26 may still be listed
- Scheduled tasks section is thorough but buried — most users won't scroll that far

---

## Goals

- Give the project a page that makes someone want to try it
- Explain the new plugin system clearly (folder plugins, plugin.yaml, auto-registration)
- Keep it honest and direct — no puffery, no AI filler
- Maintain the reference value of the config section, but reorganize it
- Not look AI-generated: avoid bullet-for-everything structure, use short prose where it reads better

---

## Non-Goals

- Adding screenshots (the terminal UI is ANSI-only, screenshots need manual capture)
- Writing a full wiki or separate docs site
- Documenting every internal detail — that lives in code comments

---

## Proposed Structure

### 1. Header / Quick hook
One paragraph. What it is, what it runs on, what makes it interesting. No bullet points. Link to the demo/screenshot if one exists.

### 2. Modes
Short section: voice mode, CLI mode, wake-word mode. One paragraph per mode or a compact comparison table. This replaces the current "How it Works" + "CLI mode" + "Wake word mode" scatter.

### 3. Getting started
Install → configure → run. Minimal config snippet (the 4-5 keys you actually need to set). Not the full reference.

### 4. Plugins
Full rewrite. New structure:
- What a plugin does (one paragraph)
- The folder layout (`plugins/weather/plugin.py`, `plugin.yaml`, `__init__.py`)
- What `plugin.yaml` looks like and what each field does
- How plugins self-register (no `routes.yaml` editing needed)
- How to write a minimal custom plugin (code snippet)
- Mention legacy single-file plugins still work

### 5. Configuration reference
Keep the full list but split into groups:
- Audio & hardware
- AI models
- Speech-to-text
- Wake word & VAD
- Scheduler
- Cache
- Plugins / voice lead (when Plan 17 lands)

Remove keys that were dropped in Plan 26.

### 6. Scheduled tasks
Keep the existing content — it's good — but trim the cron reference table to just examples, not a full grammar lesson.

### 7. Background cache
Keep existing content, trim slightly.

---

## Tone guidelines

- Write sentences, not bullets, where prose reads naturally
- Use second person ("you") throughout
- Be specific over vague: "the Pi 3B needs ~1.2s to respond" not "performance may vary"
- Short sentences. Cut every "In order to" / "It is worth noting that" / "This allows users to"
- The project has personality — it has a wake word, a name, earcons, a terminal UI. Let that come through.
- No emojis outside of terminal-output code blocks

---

## Acceptance Criteria

- [ ] Plugin section fully reflects the current folder/manifest approach
- [ ] Legacy single-file plugin approach documented as still supported
- [ ] Outdated config keys (removed in Plan 26) removed from reference
- [ ] `voice_lead` config keys documented (when Plan 17 lands, or added as a follow-up)
- [ ] Getting started section works end-to-end on a fresh Mac M1 install
- [ ] README does not read like it was written by an LLM

---

## Effort

Medium — the hard part is tone, not volume. Most existing content can be adapted rather than rewritten from scratch.

## Dependencies

- Plan 17 (voice lead) should land first so the config section includes it
- Plan 22 (plugin manifest) is already merged — this plan documents the result
