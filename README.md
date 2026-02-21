## Overview
This Python script allows users to interact with powerful language models such as OpenAI's GPT
through audio input and output. It's a versatile tool that converts spoken words into text,
processes them, and delivers audible responses. You can also see the conversation history
in your terminal. Optionally you can use the CLI mode for a textual chat!

## How it Works
Once the script is run, it initiates a microphone chat with the language model.
The users can ask questions through their microphone. The application then
transcribes this spoken question into text and sends it to the model. Upon
receiving the response, the application converts it back into audio, enabling
the users to hear the answer. For those who prefer reading, the text version of
the response is also printed in the terminal.

## Plugins
Each plugin has a file under the plugins directory. All the plugins must implement a function `process` that returns a string `str` in this particular API:
`def process(user_input, route, s):`

### Add plugins
To add a plugin you need to:
1) Update the routes.yaml; add the appropriate route for your plugin.
2) Create a file under the plugins directory with the route name (filename without `.py` must match the route name), implementing the process function
3) Use the commons directory if your function could be helpful to other plugins
4) Currently all plugins have access to the "sandvoice" object and all its properties

See the echo plugin in `plugins/echo.py` for an example.

## Key Features
- Voice to text conversion
- Interaction with OpenAI's GPT model (more to be added in the future)
- Text to voice conversion
- Terminal-based conversation history
- Wake word mode (`--wake-word`) with VAD
- Real-time web search route (`realtime_websearch`)

## Mac OSX Support
SandVoice auto-detects audio settings when possible. If you have issues with the default mic/speaker, you can force mono recording by setting `channels: 1` in the config.

### Clone the repository:
```
git clone https://github.com/spideyz0r/sandvoice
cd sandvoice
```

### Activate the virtual env
```
python3 -m venv env
source env/bin/activate
```

### Run it!
```
./sandvoice
```

## API setup
Ensure you have your API key set in environment variables:
- `OPENAI_API_KEY` (required)
- `OPENWEATHERMAP_API_KEY` (required only for the `weather` plugin)

If you use wake word mode, you'll also need a Porcupine access key (configured in `~/.sandvoice/config.yaml`).

## CLI mode
```
usage: sandvoice.py [-h] [--cli | --wake-word]

CLI mode for SandVoice

options:
  -h, --help  show this help message and exit
  --cli       enter cli mode (equivalent to yaml option cli_input: enabled)
  --wake-word enter wake word mode (hands-free voice activation with "hey sandvoice")
  ```

## Wake word mode
Run:
```
./sandvoice --wake-word
```

## Configuration file
It should be installed in `~/.sandvoice/config.yaml`

Note: use absolute paths for file/directory settings (YAML `~` is not expanded by SandVoice).

```
---
channels: 2
bitrate: 128
rate: 44100
chunk: 1024
tmp_files_path: /Users/YOUR_USER/.sandvoice/tmp/
botname: SandVoice
timezone: EST
location: Toronto, ON, CA
unit: metric
language: English
verbosity: brief
debug: disabled
summary_words: 100
search_sources: 4
push_to_talk: disabled
rss_news: https://feeds.bbci.co.uk/news/rss.xml
rss_news_max_items: 5
linux_warnings: enabled

gpt_summary_model: gpt-3.5-turbo
gpt_route_model: gpt-3.5-turbo
gpt_response_model: gpt-3.5-turbo

stream_responses: disabled
stream_print_deltas: disabled

stream_tts: disabled
stream_tts_boundary: sentence
stream_tts_first_chunk_target_s: 6
stream_tts_buffer_chunks: 2
stream_tts_tts_join_timeout_s: 30
stream_tts_player_join_timeout_s: 60

speech_to_text_model: whisper-1
speech_to_text_task: translate
speech_to_text_language: ""
speech_to_text_translate_provider: whisper
speech_to_text_translate_model: gpt-5-mini
text_to_speech_model: tts-1
bot_voice_model: nova

cli_input: disabled
bot_voice: enabled

api_timeout: 10
api_retry_attempts: 3
enable_error_logging: disabled
error_log_path: /Users/YOUR_USER/.sandvoice/error.log
fallback_to_text_on_audio_error: enabled

wake_word_enabled: enabled
wake_phrase: hey sandvoice
wake_word_sensitivity: 0.5
porcupine_access_key: ""
porcupine_keyword_paths: null

vad_enabled: enabled
vad_aggressiveness: 3
vad_silence_duration: 1.5
vad_frame_duration: 30
vad_timeout: 30

wake_confirmation_beep: enabled
wake_confirmation_beep_freq: 800
wake_confirmation_beep_duration: 0.1
visual_state_indicator: enabled

barge_in: disabled

voice_ack_earcon: disabled
voice_ack_earcon_freq: 600
voice_ack_earcon_duration: 0.06

```

### Configuration options

All configuration keys are loaded from `common/configuration.py` defaults and can be overridden in `~/.sandvoice/config.yaml`.

- `channels`: microphone recording channels (`1` or `2`); `null` enables auto-detection
- `bitrate`: MP3 bitrate (32-320)
- `rate`: sample rate in Hz (>= 8000)
- `chunk`: audio frames per buffer (>= 256)
- `tmp_files_path`: temp directory for recordings and generated audio (absolute path)
- `botname`: assistant display name
- `timezone`: user timezone string (used in system prompt)
- `location`: user location string (used in system prompt and routing defaults)
- `unit`: `metric` or `imperial` (used by weather routing/plugin)
- `language`: language string for assistant replies (used in system prompt)
- `verbosity`: `brief`, `normal`, or `detailed` (controls default response length)
- `debug`: `enabled`/`disabled` (prints extra information and logs more details)
- `summary_words`: target word count for summaries (used by some plugins)
- `search_sources`: number of sources to use for search-like plugins (plugin-dependent)
- `push_to_talk`: `enabled`/`disabled`; when enabled, prompts for a keypress before recording again
- `rss_news`: RSS feed URL used by the `news` plugin
- `rss_news_max_items`: max RSS items read per request
- `linux_warnings`: `enabled`/`disabled`; deprecated (platform audio is now auto-detected)

- `gpt_summary_model`: model used for summarization (`AI.text_summary()`)
- `gpt_route_model`: model used for routing (`AI.define_route()`)
- `gpt_response_model`: model used for normal responses (`AI.generate_response()`)

- `stream_responses`: `enabled`/`disabled`; stream LLM responses and assemble final text from deltas
- `stream_print_deltas`: `enabled`/`disabled`; when streaming and `debug` is enabled, print deltas as they arrive

- `stream_tts`: `enabled`/`disabled`; when streaming responses, generate and play TTS chunks before the full response completes (default route only)
- `stream_tts_boundary`: `sentence` or `paragraph`; chunk boundary preference
- `stream_tts_first_chunk_target_s`: integer seconds; target size of the first speakable chunk
- `stream_tts_buffer_chunks`: integer; how many text chunks to buffer ahead of playback
- `stream_tts_tts_join_timeout_s`: integer seconds; join timeout for the TTS worker thread
- `stream_tts_player_join_timeout_s`: integer seconds; join timeout for the audio player thread
- `speech_to_text_model`: model used for speech-to-text
- `speech_to_text_task`: `translate` or `transcribe` (translate outputs English; transcribe keeps the spoken language)
- `speech_to_text_language`: optional ISO-639-1 hint for transcription (e.g. `pt`, `en`); empty means auto-detect
- `speech_to_text_translate_provider`: when task is `translate`, choose `whisper` or `gpt` (gpt does transcribe then translate)
- `speech_to_text_translate_model`: model used when translate provider is `gpt`
- `text_to_speech_model`: model used for TTS generation
- `bot_voice_model`: voice name for TTS (e.g. `nova`)

- `cli_input`: `enabled`/`disabled`; enables CLI input mode without `--cli`
- `bot_voice`: `enabled`/`disabled`; controls whether SandVoice speaks responses

- `api_timeout`: OpenAI client timeout in seconds
- `api_retry_attempts`: retry attempts for OpenAI calls (backoff)
- `enable_error_logging`: `enabled`/`disabled`; writes errors to a file
- `error_log_path`: file path used when error logging is enabled (absolute path)
- `fallback_to_text_on_audio_error`: `enabled`/`disabled`; if enabled, keep going if TTS/audio fails

- `wake_word_enabled`: `enabled`/`disabled`; wake word functionality toggle (used by `--wake-word` mode)
- `wake_phrase`: wake phrase keyword name (built-in Porcupine keyword) when not using custom `.ppn`
- `wake_word_sensitivity`: float 0.0-1.0
- `porcupine_access_key`: Picovoice access key (required for `--wake-word` mode)
- `porcupine_keyword_paths`: custom Porcupine keyword model path(s) (`.ppn`) or `null`

- `vad_enabled`: `enabled`/`disabled`; voice activity detection toggle
- `vad_aggressiveness`: 0-3
- `vad_silence_duration`: seconds of silence before stopping recording
- `vad_frame_duration`: 10, 20, or 30 (ms)
- `vad_timeout`: max seconds to wait for speech

- `wake_confirmation_beep`: `enabled`/`disabled`; play beep on wake
- `wake_confirmation_beep_freq`: beep frequency (Hz)
- `wake_confirmation_beep_duration`: beep duration (seconds)
- `visual_state_indicator`: `enabled`/`disabled`; show terminal state indicators in wake word mode

- `barge_in`: `enabled`/`disabled`; interrupt TTS in `--wake-word` mode by saying the wake word

- `voice_ack_earcon`: `enabled`/`disabled`; play a short ack earcon after recording and before processing
- `voice_ack_earcon_freq`: earcon frequency (Hz, integer)
- `voice_ack_earcon_duration`: earcon duration (seconds)


Enjoy the experience!
