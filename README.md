# SandVoice

Talk to an LLM. Hear it talk back.

SandVoice is a Python voice assistant that turns microphone input into an AI conversation — transcribing speech, routing requests to the right plugin, and playing the response through your speakers. It runs on macOS and Raspberry Pi.

## Modes

| Mode | How to start | Best for |
|---|---|---|
| Default | `./sandvoice.py` | Voice conversation that records until ESC is pressed |
| CLI | `./sandvoice.py --cli` | Text input, voice or text output |
| Wake word | `./sandvoice.py --wake-word` | Hands-free, always listening |

## Getting started

```bash
git clone https://github.com/spideyz0r/sandvoice
cd sandvoice
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Set your API key:

```bash
export OPENAI_API_KEY=sk-...
```

Run:

```bash
./sandvoice.py
```

SandVoice reads its config from `~/.sandvoice/config.yaml`. On first run it will work with defaults, but you'll want to review the config section below.

## Wake word mode

Wake word mode keeps SandVoice listening in the background. Say the wake phrase, speak your request, and hear the response — no key press needed.

```bash
./sandvoice.py --wake-word
```

Required config in `~/.sandvoice/config.yaml`:

```yaml
bot_voice: enabled
stream_responses: enabled
stream_tts: enabled
vad_enabled: enabled
porcupine_access_key: "YOUR_KEY_HERE"   # free key at https://console.picovoice.ai/
```

The wake phrase defaults to `hey sandvoice`. Change it with `wake_phrase` in config (must be a built-in Porcupine keyword, or provide a custom `.ppn` model via `porcupine_keyword_paths`).

## API keys

| Key | Required | Used by |
|---|---|---|
| `OPENAI_API_KEY` | Always | All AI features |
| `OPENWEATHERMAP_API_KEY` | Weather plugin only | `weather` plugin |
| `porcupine_access_key` (in config) | Wake word mode only | Wake word, barge-in |

## Configuration

Config lives at `~/.sandvoice/config.yaml`. All keys have defaults — you only need to set what you want to override.

**Note:** `tmp_files_path` and `error_log_path` do not expand `~` — use absolute paths. `scheduler_db_path` and `tasks_file_path` do expand `~`.

### Full config reference

```yaml
# Audio recording
channels: 2                # 1 or 2; null = auto-detect
bitrate: 128               # MP3 bitrate (32-320)
rate: 44100                # sample rate in Hz
chunk: 1024                # frames per buffer
tmp_files_path: /home/user/.sandvoice/tmp/   # must end with /

# Identity and locale
botname: SandVoice
timezone: EST                # timezone name (e.g. EST, America/New_York)
location: Toronto, ON, CA    # used by weather and routing
unit: metric                 # metric or imperial
language: English
verbosity: brief             # brief, normal, or detailed

# Logging
log_level: warning           # warning, info, or debug
enable_error_logging: disabled
error_log_path: /home/user/.sandvoice/error.log

# Models
gpt_summary_model: gpt-5-mini
gpt_route_model: gpt-4.1-nano
gpt_response_model: gpt-5-mini
speech_to_text_model: whisper-1
speech_to_text_task: translate      # translate (→English) or transcribe
speech_to_text_language: ""         # ISO-639-1 hint, e.g. "pt"; empty = auto
speech_to_text_translate_provider: whisper   # whisper or gpt
speech_to_text_translate_model: gpt-5-mini
text_to_speech_model: tts-1
bot_voice_model: nova

# Response streaming
stream_responses: disabled   # enabled = stream LLM deltas (required in --wake-word)
stream_tts: disabled         # enabled = play TTS while response generates (required in --wake-word)
stream_tts_boundary: sentence           # sentence or paragraph
stream_tts_first_chunk_target_s: 6      # seconds of audio to buffer before first play

# I/O toggles
bot_voice: enabled           # enabled = speak responses (required in --wake-word)
cli_input: disabled          # enabled = text input without --cli flag
push_to_talk: disabled       # enabled = wait for keypress between turns

# API reliability
api_timeout: 10
api_retry_attempts: 3

# Plugin settings
summary_words: "100"
search_sources: "4"
rss_news: https://feeds.bbci.co.uk/news/rss.xml
rss_news_max_items: "5"

# Wake word (--wake-word mode)
wake_word_enabled: enabled   # global toggle; --wake-word flag is still required to start the mode
wake_phrase: hey sandvoice
wake_word_sensitivity: 0.5   # 0.0-1.0; higher = more sensitive
porcupine_access_key: ""
porcupine_keyword_paths: null   # path(s) to custom .ppn model(s), or null

# Voice activity detection (required in --wake-word mode)
vad_enabled: enabled
vad_aggressiveness: 3        # 0-3; 3 = most aggressive noise filtering
vad_silence_duration: 1.5    # seconds of silence to end recording
vad_frame_duration: 30       # 10, 20, or 30 ms
vad_timeout: 30              # max seconds waiting for speech

# Wake UX
wake_confirmation_beep: enabled
wake_confirmation_beep_freq: 800
wake_confirmation_beep_duration: 0.1
visual_state_indicator: enabled      # ANSI state display in terminal
voice_ack_earcon: disabled           # short tone after recording ends
voice_ack_earcon_freq: 600
voice_ack_earcon_duration: 0.06
voice_filler_delay_ms: 800           # ms before playing a filler phrase during slow plugin calls
voice_filler_phrases:                # set to [] to disable
  - "One sec."
  - "Got it, checking now."
  - "Okay, give me a moment."
  - "Let me check that."
  - "Sure, one moment."

# Scheduler (see Scheduled Tasks section)
scheduler_enabled: disabled
scheduler_poll_interval: 30
scheduler_db_path: /home/user/.sandvoice/sandvoice.db
tasks_file_path: /home/user/.sandvoice/tasks.yaml

# Background cache (see Background Cache section)
cache_enabled: disabled
cache_weather_ttl_s: 10800       # 3 hours
cache_weather_max_stale_s: 21600 # 6 hours
```

## Plugins

Each plugin handles a specific type of request. When you speak, SandVoice routes your input to the right plugin based on what you said.

### Plugin structure

Plugins live under `plugins/` as either a standalone `.py` file or a folder containing `plugin.py` and `plugin.yaml`:

```
plugins/
  echo.py                  # simple single-file plugin
  weather/
    plugin.py              # plugin logic
    plugin.yaml            # route description and metadata
```

`plugin.yaml` tells SandVoice how to route requests to that plugin:

```yaml
name: weather
version: 1.0.0

route_description: >
  The user is asking about the weather. Include location and unit keys.

route_extra_keys:
  - location
  - unit

env_vars:
  - OPENWEATHERMAP_API_KEY

config_defaults:
  location: "Toronto,ON,CA"
  unit: metric

dependencies:
  - requests
```

Single-file plugins (no YAML) are loaded automatically and use the `routes.yaml` routing table.

### Plugin API

Every plugin must implement a top-level `process` function, or a class named `Plugin` with a `process` method:

```python
def process(user_input, route, s):
    # s.ai      — AI instance (transcription, routing, TTS, responses)
    # s.config  — Config instance
    # s.plugins — dict of all loaded plugins
    # s.cache   — VoiceCache instance (or None if disabled)
    return "response string"  # should return a string; exceptions abort the current run
```

### Built-in plugins

| Plugin | What it does | Extra env var needed |
|---|---|---|
| `weather` | Current conditions and forecast | `OPENWEATHERMAP_API_KEY` |
| `hacker-news` | Top stories from Hacker News | — |
| `news` | Headlines from an RSS feed | — |
| `realtime_websearch` | Live web search via Responses API | — |
| `technical` | Technical/code questions | — |
| `greeting` | Greetings and small talk | — |
| `echo` | Echoes back what you said (example/test) | — |
| `realtime` | Web search (scraping-based, **legacy**) | — |

### Adding a plugin

Create a folder under `plugins/` with a `plugin.yaml` and a `plugin.py`:

1. Write `plugin.yaml` with `name`, `route_description`, and any `env_vars` or `config_defaults`
2. Implement `process(user_input, route, s)` in `plugin.py` — return a string
3. List any PyPI dependencies under `dependencies` in the YAML

**Constraints:**
- The folder name must match the `name` in `plugin.yaml` after normalizing hyphens to underscores (e.g. `name: my-plugin` → folder `my_plugin`). Both sides are normalized before comparison, so `my-plugin` and `my_plugin` are treated as equivalent. Plugins that fail this check are skipped with a warning.
- `dependencies` is informational only. SandVoice does not install packages automatically; run `pip install` for any listed dependency before starting.

No changes to `routes.yaml` or any other file needed.

## Scheduled tasks

SandVoice can speak reminders or trigger plugins on a schedule — without any user interaction.

### Enabling

In `~/.sandvoice/config.yaml`:

```yaml
scheduler_enabled: enabled
tasks_file_path: /home/user/.sandvoice/tasks.yaml
```

### Defining tasks

In `~/.sandvoice/tasks.yaml`:

```yaml
# Speak a reminder every weekday at 9 AM
- name: morning-reminder
  schedule_type: cron
  schedule_value: "0 9 * * 1-5"
  action_type: speak
  action_payload:
    text: "Good morning! Don't forget to check your calendar."

# Refresh weather cache every hour (silently)
- name: hourly-weather
  schedule_type: interval
  schedule_value: "3600"
  action_type: plugin
  action_payload:
    plugin: weather
    query: weather
    refresh_only: true

# One-time reminder
- name: meeting-reminder
  schedule_type: once
  schedule_value: "2026-06-01T09:00:00-05:00"
  action_type: speak
  action_payload:
    text: "Your meeting starts in 15 minutes."
```

### Schedule types

| `schedule_type` | `schedule_value` | Runs |
|---|---|---|
| `interval` | seconds, e.g. `"3600"` | repeatedly, every N seconds |
| `cron` | cron expression, e.g. `"0 9 * * *"` | at specific times (like crontab) |
| `once` | ISO 8601 timestamp | exactly once |

### Cron quick reference

```
┌─ minute (0-59)
│ ┌─ hour (0-23)
│ │ ┌─ day of month (1-31)
│ │ │ ┌─ month (1-12)
│ │ │ │ ┌─ day of week (0-6, Sun=0)
0 9 * * 1-5      weekdays at 09:00
*/15 * * * *     every 15 minutes
0 8,18 * * *     08:00 and 18:00 daily
```

### Notes

- Tasks are keyed by `name`. Rename a task in the YAML to force re-registration; changing only the schedule or payload of an existing name has no effect on the running DB row.
- An empty `tasks.yaml` (`[]`) removes all scheduled tasks from the DB on the next startup.
- If `tasks.yaml` does not exist, startup succeeds and existing DB tasks continue running.
- `once` tasks are retried on transient errors (e.g. network timeout); config errors mark them completed immediately.
- All timestamps are stored in UTC; log output uses your `timezone`.

## Background cache

The cache stores plugin responses in SQLite so repeated queries are answered instantly. The built-in TTL config keys and current cache integration apply to the weather plugin; other plugins can use `s.cache` directly.

### Enabling

```yaml
cache_enabled: enabled
cache_weather_ttl_s: 10800      # fresh for 3 hours
cache_weather_max_stale_s: 21600  # serve stale for up to 6 hours
```

### Freshness model

| Age | Result |
|---|---|
| ≤ `cache_weather_ttl_s` | Returned immediately, no API call |
| TTL < age ≤ max_stale | Returned from cache (possibly background-refreshed) |
| > `cache_weather_max_stale_s` | Live API call, cache updated |

### Silent background refresh

Pair with the scheduler to pre-populate the cache before you ask:

```yaml
# tasks.yaml
- name: weather-cache-refresh
  schedule_type: interval
  schedule_value: "10800"
  action_type: plugin
  action_payload:
    plugin: weather
    query: weather
    refresh_only: true
```

## Platform notes

SandVoice targets macOS M1 and Raspberry Pi 3B. Audio settings are auto-detected where possible. If you run into microphone issues, try setting `channels: 1` in config.
