# Plugin Manifest System

**Status**: 📋 Backlog
**Priority**: 22
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Replace the current single-file plugin convention with a self-contained folder structure driven by a `plugin.yaml` manifest. Each plugin declares its own route description, config defaults, required env vars, and pip dependencies — eliminating all manual editing of `routes.yaml` and `~/.sandvoice/config.yaml` when adding or removing a plugin.

This is sandvoice's equivalent of nanoclaw's skills system, adapted to be simpler: because sandvoice plugins never touch core files, no git-merge mechanics are needed. A plugin is just a folder you drop in.

---

## Problem Statement

Current behavior — adding a plugin requires all of the following by hand:
1. Drop `.py` file into `plugins/`
2. Edit `routes.yaml` to add the route description and any extra JSON keys
3. Edit `~/.sandvoice/config.yaml` to add plugin-specific config defaults
4. Run `pip install` for any new dependencies
5. Set any required API key env vars (discovered only by reading the source)

Removing a plugin requires the same steps in reverse. There is no way to distribute a plugin without shipping documentation alongside it.

Desired behavior:
- Drop a folder into `plugins/` → plugin self-registers
- Remove the folder → plugin is gone
- Missing env vars → clear startup warning, plugin skipped gracefully
- Community plugin is a folder (git repo / zip) with no manual integration steps

---

## Goals

1. Plugin folder structure with `plugin.yaml` manifest
2. Route descriptions assembled dynamically from manifests at startup
3. Config defaults merged from manifests (no manual `~/.sandvoice/config.yaml` edits)
4. Startup validation: warn and skip plugins with missing required env vars
5. Backward compatibility: existing single-file plugins continue to work
6. No changes to core routing logic or `AI` class

---

## Non-Goals

- No `sandvoice install <url>` CLI command (that is a follow-up)
- No plugin sandboxing or permission model
- No plugin versioning or conflict resolution between plugins
- No changes to how the LLM router model works

---

## Plugin Structure

### Before (current)
```
plugins/
├── weather.py
├── hacker-news.py
└── news.py
```

### After
```
plugins/
├── weather/
│   ├── plugin.yaml
│   └── plugin.py
├── hacker-news/
│   ├── plugin.yaml
│   └── plugin.py
└── news/
    ├── plugin.yaml
    └── plugin.py
```

Single-file plugins (`.py`) continue to load as today — no forced migration.

---

## Manifest Format (`plugin.yaml`)

```yaml
# Required
name: weather                    # route key (must be unique)
version: 1.0.0

# Route registration
route_description: |
  The user is asking how the weather is or feels like. The JSON answer
  must also include the keys "location" and "unit". If no location is
  defined, consider {{ location }}. Convert location to: City, state code
  (US only), country code (ISO 3166), comma-separated. Unit defaults to
  "metric"; other option is "imperial". Example:
  {"route": "weather", "location": "Toronto,ON,CA", "unit": "metric"}
route_extra_keys:                # additional keys the router should extract
  - location
  - unit

# Environment variables required by this plugin
# Plugin is skipped at startup if any are missing
env_vars:
  - OPENWEATHERMAP_API_KEY

# Config keys this plugin adds (merged into Config at startup)
config_defaults:
  location: "Toronto, ON, CA"
  unit: metric

# pip packages required (informational — printed on missing import)
dependencies:
  - requests
```

Only `name` and `route_description` are required. All other keys are optional.

---

## Loader Behavior

### Startup sequence (`load_plugins()`)

```python
def load_plugins(self):
    for entry in os.scandir(self.config.plugin_path):
        if entry.is_dir():
            self._load_plugin_folder(entry)   # new: manifest-based
        elif entry.name.endswith('.py'):
            self._load_plugin_file(entry)     # existing: backward compat
```

### `_load_plugin_folder(path)`

1. Read and parse `plugin.yaml`
2. Check `env_vars` — if any are missing, print warning and skip:
   ```
   [sandvoice] weather plugin disabled: missing env var OPENWEATHERMAP_API_KEY
   ```
3. Merge `config_defaults` into `Config` (only for keys not already set by user)
4. Register route description for dynamic route assembly
5. Import `plugin.py`, register `process()` or `Plugin` class as usual

### Dynamic route assembly

Today `routes.yaml` contains both core routes and plugin routes. After this plan:

- **Core routes** (`default-rote`, `greeting`, `technical`, `echo`) stay in `routes.yaml`
- **Plugin routes** are injected from manifests at startup
- The route prompt sent to the LLM is assembled by concatenating both

```python
def build_route_prompt(self, core_routes_yaml, plugin_manifests):
    lines = [core_routes_yaml]
    for manifest in plugin_manifests:
        lines.append(f"\n{manifest.name}: {manifest.route_description}")
    return "\n".join(lines)
```

---

## Config Integration

Plugin `config_defaults` are merged at the lowest priority — user config always wins:

```python
# In Config.__init__, after loading user config:
for manifest in loaded_manifests:
    for key, value in manifest.config_defaults.items():
        if key not in self.config:          # user hasn't set this key
            self.config[key] = value
```

No changes to existing config keys. Plugin-specific keys are namespaced by convention (e.g., `weather_unit`, `weather_location`) to avoid collisions.

---

## Migration of Existing Plugins

Migration is optional and can be done incrementally:

| Plugin | env vars | config keys | extra route keys |
|--------|----------|-------------|-----------------|
| `weather` | `OPENWEATHERMAP_API_KEY` | `location`, `unit` | `location`, `unit` |
| `hacker-news` | — | `summary_words` | — |
| `news` | — | `rss_news`, `rss_news_max_items` | — |
| `realtime_websearch` | OpenAI key (shared) | `search_sources` | `query` |
| `greeting` | — | `botname`, `language` | — |
| `echo` | — | — | — |
| `technical` | — | — | — |

---

## Implementation Phases

### Phase 1: Loader + Manifest Parser
- `common/plugin_loader.py` — `PluginManifest` dataclass, YAML parser, env var check
- Update `load_plugins()` in `sandvoice.py` to handle both folder and file plugins
- Unit tests: manifest parsing, missing env var skips plugin, bad YAML error handling

### Phase 2: Dynamic Route Assembly
- Extract route-prompt building into `common/plugin_loader.py`
- Core routes stay in `routes.yaml`; plugin routes injected from manifests
- Existing `routes.yaml` plugin entries removed as plugins are migrated
- Unit tests: route prompt includes manifest descriptions, extra keys propagated

### Phase 3: Config Defaults Merging
- `Config` accepts list of manifests after plugin load
- Manifest `config_defaults` merged at lowest priority
- Unit tests: user config overrides manifest default, missing key gets manifest default

### Phase 4: Migrate Existing Plugins
- Convert each built-in plugin to folder + `plugin.yaml`
- Remove now-redundant entries from `routes.yaml`
- Verify all tests pass, no behavior change

---

## Acceptance Criteria

- [ ] A new plugin folder with valid `plugin.yaml` is loaded without touching any other file
- [ ] Plugin with missing required env var is skipped with a clear warning
- [ ] Plugin `config_defaults` are merged and do not override user config
- [ ] Route prompt includes descriptions from all loaded manifests
- [ ] Single-file `.py` plugins still load without modification
- [ ] All existing plugin behavior is unchanged after migration

---

## Effort: Medium

---

## Dependencies

- No new runtime dependencies (uses stdlib `yaml` parsing via `pyyaml`, already present)

## Relationship

- Unlocks: future Timers & Reminders plugin, Spotify plugin, smart home plugin, etc.
- Builds on: existing plugin loader in `sandvoice.py`
- Independent of: Plan 20, Plan 21 (scheduler)
