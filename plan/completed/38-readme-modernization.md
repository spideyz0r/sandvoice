# README Modernization

**Status**: ✅ Completed (PR #111)
**Priority**: 38
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Rewrite `README.md` to accurately reflect the current state of the project: plugin manifest system, updated config reference, correct model defaults, and clarified operational notes.

---

## Changes Made

### Plugin manifest system documentation
- Added `plugin.yaml` structure and field reference
- Documented plugin loader constraints (folder name must match `name` after hyphen→underscore normalization, both sides normalized)
- Documented plugin API: top-level `process` function or `Plugin` class with `process` method
- Added `dependencies` informational note (not auto-installed)

### Config reference corrections
- `tmp_files_path` documented with `# must end with /` (uses string concatenation, not `os.path.join`)
- Added `~` expansion note: `tmp_files_path` and `error_log_path` do **not** expand `~`; `scheduler_db_path` and `tasks_file_path` do
- Quoted string config values that require quoting: `summary_words`, `search_sources`, `rss_news_max_items`

### Model defaults updated
- `gpt_summary_model`: `gpt-5-mini`
- `gpt_route_model`: `gpt-4.1-nano`
- `gpt_response_model`: `gpt-5-mini`
- (Replaced outdated `gpt-3.5-turbo` references)

### Mode and invocation fixes
- All `./sandvoice` references changed to `./sandvoice.py` (the entry point is `sandvoice.py` with a shebang; no wrapper script exists)
- Default mode description corrected: "Voice conversation that records until ESC is pressed"

### Plugin API wording
- Process function return comment softened: `# should return a string; exceptions abort the current run`
- Background cache section scoped to weather plugin explicitly

### tasks_file_path docs
- Added scheduled tasks section covering `tasks.yaml` format, schedule types, and cron quick reference
