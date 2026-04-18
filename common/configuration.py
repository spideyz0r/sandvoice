import math, os, yaml, logging
from common.platform_detection import log_platform_info
from common.audio_device_detection import get_optimal_channels, log_device_info

logger = logging.getLogger(__name__)


def _parse_exact_float(value):
    """Convert value to float, but return booleans or non-finite values unchanged so validate_config() can reject them."""
    if isinstance(value, bool):
        return value  # bool is a subclass of int/float; let validation reject it
    try:
        result = float(value)
        if not math.isfinite(result):
            return value  # reject NaN/Inf; let validation reject the original value
        return result
    except (TypeError, ValueError):
        return value


def _parse_exact_int(value):
    """Convert value to int only if it is already an exact integer representation.

    Non-integer floats (e.g. 800.9) are returned unchanged so validate_config()
    can reject them with a clear error.
    """
    if isinstance(value, bool):
        return value  # bool is a subclass of int; let validation reject it
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    return value


class Config:
    def __init__(self):
        self.config_file = os.path.join(os.path.expanduser("~"), ".sandvoice", "config.yaml")
        self.defaults  = {
            "channels": None,
            "bitrate": 128,
            "rate": 44100,
            "chunk": 1024,
            "tmp_files_path": os.path.join(os.path.expanduser("~"), ".sandvoice", "tmp") + os.sep,
            "botname": "SandVoice",
            "timezone": "EST",
            "location": "Toronto, ON, CA",
            "unit": "metric",
            "language": "English",
            # Assistant response verbosity.
            # - brief: concise answers by default; expand on explicit user request
            # - normal: balanced detail
            # - detailed: more thorough, structured answers
            "verbosity": "brief",
            "log_level": "warning",
            "summary_words": "100",
            "search_sources": "4",
            "push_to_talk": "disabled",
            "rss_news": "https://feeds.bbci.co.uk/news/rss.xml",
            "rss_news_max_items": "5",
            "llm_summary_model" : "gpt-5-mini",
            "llm_route_model" : "gpt-4.1-nano",
            "llm_response_model" : "gpt-5-mini",
            "speech_to_text_model" : "whisper-1",
            # Speech-to-text behavior
            # - translate: translate speech to English (Whisper translations endpoint)
            # - transcribe: keep original language (Whisper transcriptions endpoint)
            "speech_to_text_task": "translate",
            # Optional ISO-639-1 language hint used for transcriptions and for the GPT transcribe-then-translate flow (e.g. "pt", "en").
            "speech_to_text_language": "",
            # Translation provider used when speech_to_text_task=translate
            # - whisper: Whisper translations endpoint (single call, auto-detect source language)
            # - gpt: transcribe (optionally with language hint) then translate via GPT
            "speech_to_text_translate_provider": "whisper",
            # Model used when speech_to_text_translate_provider=gpt
            "speech_to_text_translate_model": "gpt-5-mini",
            "text_to_speech_model" : "tts-1",
            "bot_voice_model" : "nova",
            "cli_input": "disabled",
            "bot_voice": "enabled",
            "api_timeout": 10,
            "api_retry_attempts": 3,
            "enable_error_logging": "disabled",
            "error_log_path": os.path.join(os.path.expanduser("~"), ".sandvoice", "error.log"),

            # LLM streaming (Phase 1: stream text assembly)
            "stream_responses": "disabled",

            # Plan 08 Phase 2: streaming TTS (buffer then play)
            "stream_tts": "disabled",
            "stream_tts_boundary": "sentence",  # sentence|paragraph
            "stream_tts_first_chunk_target_s": 6,
            # Wake word mode settings (only active with --wake-word flag)
            "wake_word_enabled": "enabled",
            "wake_phrase": "hey sandvoice",
            "wake_word_sensitivity": 0.5,
            "porcupine_access_key": "",
            "porcupine_keyword_paths": None,
            # Voice Activity Detection
            "vad_enabled": "enabled",
            "vad_aggressiveness": 3,
            "vad_silence_duration": 1.5,
            "vad_frame_duration": 30,
            "vad_timeout": 30,
            # Audio feedback
            "wake_confirmation_beep": "enabled",
            "wake_confirmation_beep_freq": 800,
            "wake_confirmation_beep_duration": 0.1,
            "visual_state_indicator": "enabled",
            # Voice UX
            "voice_ack_earcon": "disabled",
            "voice_ack_earcon_freq": 600,
            "voice_ack_earcon_duration": 0.06,
            # Voice Filler (Plan 17) — pre-generated phrases played during plugin processing
            "voice_filler_delay_ms": 800,
            "voice_filler_phrases": [
                "One sec.",
                "Got it.",
                "Sure.",
                "Alright.",
                "Mm-hmm.",
            ],

            # Optional: append custom instructions to the greeting plugin's generation prompt.
            # Supports YAML block scalar for multi-line text.
            # greeting_extra: |
            #   End the greeting with a short, relevant proverb.
            "greeting_extra": None,

            # Background Cache (Plan 20)
            "cache_enabled": "disabled",
            "cache_weather_ttl_s": 10800,    # 3 hours — refresh window
            "cache_weather_max_stale_s": 21600,  # 6 hours — hard expiry
            "cache_auto_refresh": [],

            # Blocking Cache Warmup (Plan 39)
            "cache_warmup_timeout_s": 15,   # max seconds to wait for all warmup threads (0 = fire-and-forget)
            "cache_warmup_retries": 3,       # max attempts per plugin before giving up
            "cache_warmup_retry_delay_s": 2, # seconds between retry attempts

            # Provider selection (Plan 43) — only "openai" is supported for now
            "llm_provider": "openai",
            "tts_provider": "openai",
            "stt_provider": "openai",

            # Optional: append custom standing instructions to every system prompt.
            # Supports YAML block scalar for multi-line text.
            # system_prompt_extra: |
            #   Always respond in a formal tone.
            #   You are an expert in Brazilian cuisine.
            "system_prompt_extra": None,

            # Task Scheduler (Plan 21)
            "scheduler_enabled": "disabled",
            "scheduler_poll_interval": 30,
            "scheduler_db_path": os.path.join(os.path.expanduser("~"), ".sandvoice", "sandvoice.db"),
            "tasks_file_path": os.path.join(os.path.expanduser("~"), ".sandvoice", "tasks.yaml"),
        }
        self.config = self.load_defaults()
        self.load_config()

    def load_defaults(self):
        if not os.path.exists(self.config_file):
            self._user_keys: set = set()
            return dict(self.defaults)
        with open(self.config_file, "r") as f:
            data = yaml.safe_load(f)
        if data is None:
            data = {}
        elif not isinstance(data, dict):
            logger.warning(
                "Config file %s must be a YAML mapping; ignoring malformed content",
                self.config_file,
            )
            data = {}
        self._user_keys: set = set(data.keys())
        return {**self.defaults, **data}

    def load_config(self):
        self.channels = self.get("channels")
        self.bitrate = self.get("bitrate")
        self.rate = self.get("rate")
        self.chunk = self.get("chunk")
        self.tmp_files_path = self.get("tmp_files_path")
        self.botname = self.get("botname")
        self.timezone = self.get("timezone")
        self.location = self.get("location")
        self.unit = self.get("unit")
        self.language = self.get("language")

        verbosity = self.get("verbosity")
        if verbosity is None:
            verbosity = "brief"
        self.verbosity = str(verbosity).strip().lower()
        self.summary_words = self.get("summary_words")
        self.search_sources = self.get("search_sources")
        self.rss_news = self.get("rss_news")
        self.rss_news_max_items = self.get("rss_news_max_items")
        self.tmp_recording = self.tmp_files_path + "recording"
        raw = str(self.get("log_level") or "warning").strip().lower()
        self.log_level = raw if raw in ("warning", "info", "debug") else "warning"
        self.bot_voice = self.get("bot_voice").lower() == "enabled"
        self.push_to_talk = self.get("push_to_talk").lower() == "enabled"
        self.sandvoice_path = f"{os.path.dirname(os.path.realpath(__file__))}/../"
        self.plugin_path = f"{self.sandvoice_path}plugins/"
        self.llm_summary_model = self.get("llm_summary_model")
        self.llm_route_model = self.get("llm_route_model")
        self.llm_response_model = self.get("llm_response_model")
        self.speech_to_text_model = self.get("speech_to_text_model")
        self.speech_to_text_task = str(self.get("speech_to_text_task") or "translate").strip().lower()
        self.speech_to_text_language = str(self.get("speech_to_text_language") or "").strip().lower()
        self.speech_to_text_translate_provider = str(
            self.get("speech_to_text_translate_provider") or "whisper"
        ).strip().lower()
        self.speech_to_text_translate_model = self.get("speech_to_text_translate_model")
        self.text_to_speech_model = self.get("text_to_speech_model")
        self.bot_voice_model = self.get("bot_voice_model")
        self.cli_input = self.get("cli_input").lower() == "enabled"
        self.api_timeout = self.get("api_timeout")
        self.api_retry_attempts = self.get("api_retry_attempts")
        self.enable_error_logging = self.get("enable_error_logging").lower() == "enabled"
        self.error_log_path = self.get("error_log_path")
        self.llm_provider = str(self.get("llm_provider") or "openai").strip().lower()
        self.tts_provider = str(self.get("tts_provider") or "openai").strip().lower()
        self.stt_provider = str(self.get("stt_provider") or "openai").strip().lower()

        # Streaming
        self.stream_responses = self.get("stream_responses").lower() == "enabled"
        self.stream_tts = self.get("stream_tts").lower() == "enabled"
        self.stream_tts_boundary = str(self.get("stream_tts_boundary") or "sentence").strip().lower()
        self.stream_tts_first_chunk_target_s = self.get("stream_tts_first_chunk_target_s")
        if isinstance(self.stream_tts_first_chunk_target_s, float) and self.stream_tts_first_chunk_target_s.is_integer():
            self.stream_tts_first_chunk_target_s = int(self.stream_tts_first_chunk_target_s)

        # Wake word mode settings
        self.wake_word_enabled = self.get("wake_word_enabled").lower() == "enabled"
        self.wake_phrase = self.get("wake_phrase")
        self.wake_word_sensitivity = self.get("wake_word_sensitivity")
        self.porcupine_access_key = self.get("porcupine_access_key")
        self.porcupine_keyword_paths = self.get("porcupine_keyword_paths")
        # Voice Activity Detection
        self.vad_enabled = self.get("vad_enabled").lower() == "enabled"
        self.vad_aggressiveness = self.get("vad_aggressiveness")
        self.vad_silence_duration = self.get("vad_silence_duration")
        self.vad_frame_duration = self.get("vad_frame_duration")
        self.vad_timeout = self.get("vad_timeout")
        # Audio feedback
        self.wake_confirmation_beep = self.get("wake_confirmation_beep").lower() == "enabled"
        self.wake_confirmation_beep_freq = _parse_exact_int(self.get("wake_confirmation_beep_freq"))
        self.wake_confirmation_beep_duration = _parse_exact_float(self.get("wake_confirmation_beep_duration"))
        self.visual_state_indicator = self.get("visual_state_indicator").lower() == "enabled"

        # Task Scheduler
        raw_scheduler_enabled = self.get("scheduler_enabled")
        if isinstance(raw_scheduler_enabled, bool):
            self.scheduler_enabled = raw_scheduler_enabled
        else:
            self.scheduler_enabled = str(raw_scheduler_enabled or "disabled").strip().lower() in (
                "enabled", "true", "yes", "1", "on"
            )
        raw_poll = self.get("scheduler_poll_interval")
        try:
            self.scheduler_poll_interval = max(1, int(raw_poll)) if raw_poll is not None else 30
        except (TypeError, ValueError):
            self.scheduler_poll_interval = 30
        raw_db_path = self.get("scheduler_db_path")
        self.scheduler_db_path = os.path.expanduser(str(raw_db_path)) if raw_db_path else self.defaults["scheduler_db_path"]
        raw_tasks_file_path = self.get("tasks_file_path")
        self.tasks_file_path = os.path.expanduser(str(raw_tasks_file_path)) if raw_tasks_file_path else self.defaults["tasks_file_path"]
        if os.path.exists(self.tasks_file_path) and not os.path.isfile(self.tasks_file_path):
            raise ValueError(f"tasks_file_path must point to a file: {self.tasks_file_path}")
        self.tasks_file_exists = os.path.isfile(self.tasks_file_path)
        self.tasks = self._load_tasks_file()
        if "tasks" in self.config:
            logger.warning("'tasks' in config.yaml is ignored. Use tasks_file_path/tasks.yaml instead.")

        # Background Cache (Plan 20)
        raw_cache_enabled = self.get("cache_enabled")
        if isinstance(raw_cache_enabled, bool):
            self.cache_enabled = raw_cache_enabled
        else:
            self.cache_enabled = str(raw_cache_enabled or "disabled").strip().lower() in (
                "enabled", "true", "yes", "1", "on"
            )
        try:
            self.cache_weather_ttl_s = max(1, int(self.get("cache_weather_ttl_s")))
        except (TypeError, ValueError):
            self.cache_weather_ttl_s = self.defaults["cache_weather_ttl_s"]
        try:
            self.cache_weather_max_stale_s = max(1, int(self.get("cache_weather_max_stale_s")))
        except (TypeError, ValueError):
            self.cache_weather_max_stale_s = self.defaults["cache_weather_max_stale_s"]
        if self.cache_weather_max_stale_s < self.cache_weather_ttl_s:
            logger.warning(
                "cache_weather_max_stale_s (%d) is less than cache_weather_ttl_s (%d); "
                "clamping max_stale to ttl value.",
                self.cache_weather_max_stale_s,
                self.cache_weather_ttl_s,
            )
            self.cache_weather_max_stale_s = self.cache_weather_ttl_s
        self.cache_auto_refresh = self._parse_cache_auto_refresh(self.get("cache_auto_refresh"))
        _timeout = _parse_exact_int(self.get("cache_warmup_timeout_s"))
        if isinstance(_timeout, int) and not isinstance(_timeout, bool):
            self.cache_warmup_timeout_s = max(0, _timeout)
        else:
            self.cache_warmup_timeout_s = self.defaults["cache_warmup_timeout_s"]
        _retries = _parse_exact_int(self.get("cache_warmup_retries"))
        if isinstance(_retries, int) and not isinstance(_retries, bool):
            self.cache_warmup_retries = max(0, _retries)
        else:
            self.cache_warmup_retries = self.defaults["cache_warmup_retries"]
        _delay = _parse_exact_float(self.get("cache_warmup_retry_delay_s"))
        if isinstance(_delay, (int, float)) and not isinstance(_delay, bool):
            self.cache_warmup_retry_delay_s = max(0.0, float(_delay))
        else:
            self.cache_warmup_retry_delay_s = self.defaults["cache_warmup_retry_delay_s"]

        # Voice UX
        voice_ack_earcon = self.get("voice_ack_earcon")
        if isinstance(voice_ack_earcon, bool):
            self.voice_ack_earcon = voice_ack_earcon
        elif isinstance(voice_ack_earcon, int):
            self.voice_ack_earcon = voice_ack_earcon != 0
        else:
            self.voice_ack_earcon = str(voice_ack_earcon or "disabled").lower() == "enabled"
        self.voice_ack_earcon_freq = _parse_exact_int(self.get("voice_ack_earcon_freq"))
        self.voice_ack_earcon_duration = _parse_exact_float(self.get("voice_ack_earcon_duration"))

        # Voice Filler
        _raw_delay = _parse_exact_int(self.get("voice_filler_delay_ms"))
        if isinstance(_raw_delay, int) and not isinstance(_raw_delay, bool):
            self.voice_filler_delay_ms = max(0, _raw_delay)
        else:
            self.voice_filler_delay_ms = self.defaults["voice_filler_delay_ms"]
        raw_phrases = self.get("voice_filler_phrases")
        if isinstance(raw_phrases, list):
            self.voice_filler_phrases = [s for p in raw_phrases if p is not None for s in [str(p).strip()] if s]
        elif raw_phrases is None:
            self.voice_filler_phrases = list(self.defaults["voice_filler_phrases"])
        else:
            self.voice_filler_phrases = list(self.defaults["voice_filler_phrases"])

        # System prompt extra (Plan 50)
        raw_spe = self.get("system_prompt_extra")
        if raw_spe is None:
            self.system_prompt_extra = None
        elif not isinstance(raw_spe, str):
            logger.warning(
                "system_prompt_extra must be a non-empty string; ignoring value of type %s",
                type(raw_spe).__name__,
            )
            self.system_prompt_extra = None
        elif not raw_spe.strip():
            logger.warning(
                "system_prompt_extra is blank or whitespace-only (length=%d); ignoring",
                len(raw_spe),
            )
            self.system_prompt_extra = None
        else:
            self.system_prompt_extra = raw_spe.strip()

        # Greeting extra (Plan 51)
        raw_ge = self.get("greeting_extra")
        if raw_ge is None:
            self.greeting_extra = None
        elif not isinstance(raw_ge, str) or not raw_ge.strip():
            logger.warning(
                "greeting_extra must be a non-empty string; ignoring value of type %s",
                type(raw_ge).__name__,
            )
            self.greeting_extra = None
        else:
            self.greeting_extra = raw_ge.strip()

        # Auto-detect channels if not explicitly configured
        if self.channels is None:
            try:
                self.channels = get_optimal_channels()
                logger.debug("Auto-detected audio channels: %d", self.channels)
            except Exception as e:
                logger.warning(
                    "Failed to auto-detect audio channels: %s. Falling back to 2 channels.",
                    e
                )
                self.channels = 2

        # Log platform and audio device info in debug mode
        if self.debug:
            log_platform_info(self)
            log_device_info(self)

        self.validate_config()

    @property
    def debug(self) -> bool:
        """True when log_level is 'debug'. Read-only; set log_level instead."""
        return self.log_level == "debug"

    def validate_config(self):
        """Validate configuration values and raise errors for invalid settings."""
        errors = []

        # Validate numeric values
        if not isinstance(self.channels, int) or self.channels < 1 or self.channels > 2:
            errors.append("channels must be 1 or 2")

        if not isinstance(self.bitrate, int) or self.bitrate < 32 or self.bitrate > 320:
            errors.append("bitrate must be between 32 and 320")

        if not isinstance(self.rate, int) or self.rate < 8000:
            errors.append("rate must be at least 8000")

        if not isinstance(self.chunk, int) or self.chunk < 256:
            errors.append("chunk must be at least 256")

        if not isinstance(self.api_timeout, int) or self.api_timeout < 1:
            errors.append("api_timeout must be at least 1")

        if not isinstance(self.api_retry_attempts, int) or self.api_retry_attempts < 1:
            errors.append("api_retry_attempts must be at least 1")

        # Validate string values
        if not self.botname or not isinstance(self.botname, str):
            errors.append("botname must be a non-empty string")

        if not self.language or not isinstance(self.language, str):
            errors.append("language must be a non-empty string")

        if self.verbosity not in ["brief", "normal", "detailed"]:
            errors.append("verbosity must be 'brief', 'normal', or 'detailed'")

        if not self.location or not isinstance(self.location, str):
            errors.append("location must be a non-empty string")

        if self.speech_to_text_task not in ["translate", "transcribe"]:
            errors.append("speech_to_text_task must be 'translate' or 'transcribe'")

        if not isinstance(self.speech_to_text_language, str):
            errors.append("speech_to_text_language must be a string")

        if self.speech_to_text_translate_provider not in ["whisper", "gpt"]:
            errors.append("speech_to_text_translate_provider must be 'whisper' or 'gpt'")

        if not self.speech_to_text_translate_model or not isinstance(self.speech_to_text_translate_model, str):
            errors.append("speech_to_text_translate_model must be a non-empty string")

        # Validate unit
        if self.unit not in ["metric", "imperial"]:
            errors.append("unit must be 'metric' or 'imperial'")

        # Validate paths
        if not self.tmp_files_path or not isinstance(self.tmp_files_path, str):
            errors.append("tmp_files_path must be a non-empty string")

        if not self.tasks_file_path or not isinstance(self.tasks_file_path, str):
            errors.append("tasks_file_path must be a non-empty string")

        # Validate wake word settings
        if not isinstance(self.wake_word_sensitivity, (int, float)) or not (0.0 <= self.wake_word_sensitivity <= 1.0):
            errors.append("wake_word_sensitivity must be between 0.0 and 1.0")

        if not self.wake_phrase or not isinstance(self.wake_phrase, str):
            errors.append("wake_phrase must be a non-empty string")

        if not isinstance(self.porcupine_access_key, str):
            errors.append("porcupine_access_key must be a string")

        # Validate VAD settings
        if not isinstance(self.vad_aggressiveness, int) or not (0 <= self.vad_aggressiveness <= 3):
            errors.append("vad_aggressiveness must be between 0 and 3")

        if not isinstance(self.vad_silence_duration, (int, float)) or self.vad_silence_duration <= 0:
            errors.append("vad_silence_duration must be a positive number")

        if self.vad_frame_duration not in [10, 20, 30]:
            errors.append("vad_frame_duration must be 10, 20, or 30")

        if not isinstance(self.vad_timeout, (int, float)) or self.vad_timeout <= 0:
            errors.append("vad_timeout must be a positive number")

        # Validate audio feedback settings
        if isinstance(self.wake_confirmation_beep_freq, bool) or not isinstance(self.wake_confirmation_beep_freq, int) or self.wake_confirmation_beep_freq <= 0:
            errors.append("wake_confirmation_beep_freq must be a positive integer")

        if isinstance(self.wake_confirmation_beep_duration, bool) or not isinstance(self.wake_confirmation_beep_duration, (int, float)) or not math.isfinite(self.wake_confirmation_beep_duration) or self.wake_confirmation_beep_duration <= 0:
            errors.append("wake_confirmation_beep_duration must be a positive number")

        if self.voice_ack_earcon:
            if isinstance(self.voice_ack_earcon_freq, bool) or not isinstance(self.voice_ack_earcon_freq, int) or self.voice_ack_earcon_freq <= 0:
                errors.append("voice_ack_earcon_freq must be a positive integer")
            if isinstance(self.voice_ack_earcon_duration, bool) or not isinstance(self.voice_ack_earcon_duration, (int, float)) or not math.isfinite(self.voice_ack_earcon_duration) or self.voice_ack_earcon_duration <= 0:
                errors.append("voice_ack_earcon_duration must be a positive number")

        # Validate streaming TTS settings
        if self.stream_tts_boundary not in ["sentence", "paragraph"]:
            errors.append("stream_tts_boundary must be 'sentence' or 'paragraph'")

        if isinstance(self.stream_tts_first_chunk_target_s, bool) or not isinstance(self.stream_tts_first_chunk_target_s, int) or self.stream_tts_first_chunk_target_s < 1:
            errors.append("stream_tts_first_chunk_target_s must be an integer >= 1")

        # Report all errors
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

    def get(self, key):
        return self.config.get(key, self.defaults.get(key))

    def merge_plugin_defaults(self, manifests):
        """Merge config defaults from plugin manifests at the lowest priority.

        For each key in a manifest's ``config_defaults``, the value is only
        applied when the user has not explicitly set that key in their
        ``config.yaml``.  User config wins over manifest defaults; when
        multiple manifests provide the same key the first one wins.

        Args:
            manifests: Iterable of :class:`~common.plugin_loader.PluginManifest`.
        """
        changed = False
        plugin_keys_applied: set = set()
        for manifest in manifests:
            for key, value in manifest.config_defaults.items():
                if key not in self._user_keys and key not in plugin_keys_applied:
                    self.config[key] = value
                    plugin_keys_applied.add(key)
                    changed = True
        if changed:
            self._apply_plugin_config_properties()
            self.validate_config()

    def _apply_plugin_config_properties(self):
        """Re-apply the subset of config properties that plugins may supply defaults for."""
        if "location" in self.config:
            self.location = self.get("location")
        if "unit" in self.config:
            self.unit = self.get("unit")
        if "rss_news" in self.config:
            self.rss_news = self.get("rss_news")
        if "rss_news_max_items" in self.config:
            self.rss_news_max_items = self.get("rss_news_max_items")
        if "summary_words" in self.config:
            self.summary_words = self.get("summary_words")
        if "search_sources" in self.config:
            self.search_sources = self.get("search_sources")

    def _parse_cache_auto_refresh(self, raw):
        """Validate and normalise the cache_auto_refresh list.

        Each entry must have:
          - ``plugin``: non-empty string
          - ``interval_s``: positive integer

        Optional fields:
          - ``query``: string (defaults to plugin name)
          - ``ttl_s``: positive integer (defaults to ``interval_s``)
          - ``max_stale_s``: positive integer (defaults to ``int(interval_s * 1.5)``)
          - ``rss_url``: string (news plugin only; overrides ``rss_news`` config)
          - ``location``: string (weather plugin only; overrides ``location`` config)
          - ``unit``: string (weather plugin only; overrides ``unit`` config)

        Invalid entries are logged as warnings and skipped.
        """
        if raw is None:
            return []
        if not isinstance(raw, list):
            logger.warning(
                "cache_auto_refresh must be a list; ignoring invalid value of type %s",
                type(raw).__name__,
            )
            return []
        validated = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                logger.warning(
                    "cache_auto_refresh entry %d: expected a mapping, got %s; skipping",
                    i,
                    type(entry).__name__,
                )
                continue
            plugin = entry.get("plugin")
            if not isinstance(plugin, str):
                logger.warning(
                    "cache_auto_refresh entry %d: 'plugin' must be a non-empty string; skipping",
                    i,
                )
                continue
            plugin = plugin.strip()
            if not plugin:
                logger.warning(
                    "cache_auto_refresh entry %d: 'plugin' must be a non-empty string; skipping",
                    i,
                )
                continue
            interval_s = _parse_exact_int(entry.get("interval_s"))
            if not isinstance(interval_s, int) or isinstance(interval_s, bool) or interval_s <= 0:
                logger.warning(
                    "cache_auto_refresh entry %d (plugin=%r): 'interval_s' must be a positive integer; skipping",
                    i,
                    plugin,
                )
                continue
            raw_ttl = _parse_exact_int(entry.get("ttl_s")) if entry.get("ttl_s") is not None else None
            if raw_ttl is not None:
                if not isinstance(raw_ttl, int) or isinstance(raw_ttl, bool) or raw_ttl <= 0:
                    logger.warning(
                        "cache_auto_refresh entry %d (plugin=%r): 'ttl_s' must be a positive integer; using interval_s",
                        i,
                        plugin,
                    )
                    ttl_s = interval_s
                else:
                    ttl_s = raw_ttl
            else:
                ttl_s = interval_s
            raw_max_stale = _parse_exact_int(entry.get("max_stale_s")) if entry.get("max_stale_s") is not None else None
            if raw_max_stale is not None:
                if not isinstance(raw_max_stale, int) or isinstance(raw_max_stale, bool) or raw_max_stale <= 0:
                    logger.warning(
                        "cache_auto_refresh entry %d (plugin=%r): 'max_stale_s' must be a positive integer; using default",
                        i,
                        plugin,
                    )
                    max_stale_s = int(interval_s * 1.5)
                else:
                    max_stale_s = raw_max_stale
            else:
                max_stale_s = int(interval_s * 1.5)
            if max_stale_s < ttl_s:
                logger.warning(
                    "cache_auto_refresh entry %d (plugin=%r): 'max_stale_s' (%d) is less than "
                    "'ttl_s' (%d); clamping max_stale_s to ttl_s.",
                    i,
                    plugin,
                    max_stale_s,
                    ttl_s,
                )
                max_stale_s = ttl_s
            normalised = {
                "plugin": plugin,
                "interval_s": interval_s,
                "ttl_s": ttl_s,
                "max_stale_s": max_stale_s,
                "query": str(entry.get("query") or "").strip() or plugin,
            }
            for optional_key in ("rss_url", "location", "unit"):
                if optional_key in entry and entry[optional_key] is not None:
                    optional_value = str(entry[optional_key]).strip()
                    if optional_value:
                        normalised[optional_key] = optional_value
            validated.append(normalised)
        return validated

    def _load_tasks_file(self):
        if not self.tasks_file_exists:
            return []
        with open(self.tasks_file_path, "r") as f:
            data = yaml.safe_load(f)
        if data is None:
            return []
        if not isinstance(data, list):
            raise ValueError(f"tasks file must contain a YAML list: {self.tasks_file_path}")
        return list(data)
