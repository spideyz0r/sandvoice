import os, yaml, logging
from common.platform_detection import log_platform_info
from common.audio_device_detection import get_optimal_channels, log_device_info

class Config:
    def __init__(self):
        self.config_file = f"{os.environ['HOME']}/.sandvoice/config.yaml"
        self.defaults  = {
            "channels": None,
            "bitrate": 128,
            "rate": 44100,
            "chunk": 1024,
            "tmp_files_path": f"{os.environ['HOME']}/.sandvoice/tmp/",
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
            "debug": "disabled",
            "summary_words": "100",
            "search_sources": "4",
            "push_to_talk": "disabled",
            "rss_news": "https://feeds.bbci.co.uk/news/rss.xml",
            "rss_news_max_items": "5",
            "linux_warnings": "enabled",
            "gpt_summary_model" : "gpt-3.5-turbo",
            "gpt_route_model" : "gpt-3.5-turbo",
            "gpt_response_model" : "gpt-3.5-turbo",
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
            "error_log_path": f"{os.environ['HOME']}/.sandvoice/error.log",
            "fallback_to_text_on_audio_error": "enabled",

            # LLM streaming (Phase 1: stream text assembly)
            "stream_responses": "disabled",
            # Only used when stream_responses is enabled; useful in debug/CLI.
            "stream_print_deltas": "disabled",

            # Plan 08 Phase 2: streaming TTS (buffer then play)
            "stream_tts": "disabled",
            "stream_tts_boundary": "sentence",  # sentence|paragraph
            "stream_tts_first_chunk_target_s": 6,
            "stream_tts_buffer_chunks": 2,
            "stream_tts_tts_join_timeout_s": 30,
            "stream_tts_player_join_timeout_s": 60,
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
            # Barge-in feature (interrupt TTS with wake word)
            "barge_in": "disabled",

            # Voice UX
            "voice_ack_earcon": "disabled",
            "voice_ack_earcon_freq": 600,
            "voice_ack_earcon_duration": 0.06,

            # Task Scheduler (Plan 21)
            "scheduler_enabled": "enabled",
            "scheduler_poll_interval": 30,
            "scheduler_db_path": f"{os.environ['HOME']}/.sandvoice/sandvoice.db",
        }
        self.config = self.load_defaults()
        self.load_config()

    def load_defaults(self):
        if not os.path.exists(self.config_file):
            return self.defaults
        with open(self.config_file, "r") as f:
            data = yaml.safe_load(f)
        # combine both dicts, data overrides defaults
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
        self.debug = self.get("debug").lower() == "enabled"
        self.bot_voice = self.get("bot_voice").lower() == "enabled"
        self.push_to_talk = self.get("push_to_talk").lower() == "enabled"
        self.linux_warnings = self.get("linux_warnings").lower() == "enabled"
        self.sandvoice_path = f"{os.path.dirname(os.path.realpath(__file__))}/../"
        self.plugin_path = f"{self.sandvoice_path}plugins/"
        self.gpt_summary_model = self.get("gpt_summary_model")
        self.gpt_route_model = self.get("gpt_route_model")
        self.gpt_response_model = self.get("gpt_response_model")
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
        self.fallback_to_text_on_audio_error = self.get("fallback_to_text_on_audio_error").lower() == "enabled"

        # Streaming
        self.stream_responses = self.get("stream_responses").lower() == "enabled"
        self.stream_print_deltas = self.get("stream_print_deltas").lower() == "enabled"

        self.stream_tts = self.get("stream_tts").lower() == "enabled"
        self.stream_tts_boundary = str(self.get("stream_tts_boundary") or "sentence").strip().lower()
        self.stream_tts_first_chunk_target_s = self.get("stream_tts_first_chunk_target_s")
        self.stream_tts_buffer_chunks = self.get("stream_tts_buffer_chunks")
        self.stream_tts_tts_join_timeout_s = self.get("stream_tts_tts_join_timeout_s")
        self.stream_tts_player_join_timeout_s = self.get("stream_tts_player_join_timeout_s")

        # Normalize numeric YAML representations for streaming TTS
        if isinstance(self.stream_tts_first_chunk_target_s, float) and self.stream_tts_first_chunk_target_s.is_integer():
            self.stream_tts_first_chunk_target_s = int(self.stream_tts_first_chunk_target_s)
        if isinstance(self.stream_tts_buffer_chunks, float) and self.stream_tts_buffer_chunks.is_integer():
            self.stream_tts_buffer_chunks = int(self.stream_tts_buffer_chunks)

        if isinstance(self.stream_tts_tts_join_timeout_s, float) and self.stream_tts_tts_join_timeout_s.is_integer():
            self.stream_tts_tts_join_timeout_s = int(self.stream_tts_tts_join_timeout_s)
        if isinstance(self.stream_tts_player_join_timeout_s, float) and self.stream_tts_player_join_timeout_s.is_integer():
            self.stream_tts_player_join_timeout_s = int(self.stream_tts_player_join_timeout_s)

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
        self.wake_confirmation_beep_freq = self.get("wake_confirmation_beep_freq")
        self.wake_confirmation_beep_duration = self.get("wake_confirmation_beep_duration")
        self.visual_state_indicator = self.get("visual_state_indicator").lower() == "enabled"
        # Barge-in feature
        self.barge_in = self.get("barge_in").lower() == "enabled"

        # Task Scheduler
        self.scheduler_enabled = str(self.get("scheduler_enabled") or "enabled").lower() == "enabled"
        raw_poll = self.get("scheduler_poll_interval")
        try:
            self.scheduler_poll_interval = max(1, int(raw_poll)) if raw_poll is not None else 30
        except (TypeError, ValueError):
            self.scheduler_poll_interval = 30
        raw_db_path = self.get("scheduler_db_path")
        self.scheduler_db_path = str(raw_db_path) if raw_db_path else self.defaults["scheduler_db_path"]

        # Voice UX
        voice_ack_earcon = self.get("voice_ack_earcon")
        if isinstance(voice_ack_earcon, bool):
            self.voice_ack_earcon = voice_ack_earcon
        elif isinstance(voice_ack_earcon, int):
            self.voice_ack_earcon = voice_ack_earcon != 0
        else:
            self.voice_ack_earcon = str(voice_ack_earcon or "disabled").lower() == "enabled"
        self.voice_ack_earcon_freq = self.get("voice_ack_earcon_freq")
        self.voice_ack_earcon_duration = self.get("voice_ack_earcon_duration")

        # Normalize common YAML representations
        if isinstance(self.voice_ack_earcon_freq, float) and self.voice_ack_earcon_freq.is_integer():
            self.voice_ack_earcon_freq = int(self.voice_ack_earcon_freq)
        elif isinstance(self.voice_ack_earcon_freq, str):
            freq_str = self.voice_ack_earcon_freq.strip()
            try:
                freq_val = float(freq_str)
            except Exception:
                freq_val = None

            if freq_val is not None and float(freq_val).is_integer():
                self.voice_ack_earcon_freq = int(freq_val)

        if isinstance(self.voice_ack_earcon_duration, str):
            duration_str = self.voice_ack_earcon_duration.strip()
            try:
                self.voice_ack_earcon_duration = float(duration_str)
            except Exception:
                pass

        # Auto-detect channels if not explicitly configured
        if self.channels is None:
            try:
                self.channels = get_optimal_channels()
                if self.debug:
                    print(f"Auto-detected audio channels: {self.channels}")
            except Exception as e:
                logging.warning(
                    "Failed to auto-detect audio channels: %s. Falling back to 2 channels.",
                    e
                )
                self.channels = 2

        # Deprecation warning for linux_warnings
        if "linux_warnings" in self.config and self.config["linux_warnings"] != self.defaults["linux_warnings"]:
            print("WARNING: 'linux_warnings' configuration is deprecated and no longer needed.")
            print("Platform-specific audio settings are now auto-detected.")

        # Log platform and audio device info in debug mode
        if self.debug:
            log_platform_info(self)
            log_device_info(self)

        self.validate_config()

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
        if not isinstance(self.wake_confirmation_beep_freq, int) or self.wake_confirmation_beep_freq <= 0:
            errors.append("wake_confirmation_beep_freq must be a positive integer")

        if not isinstance(self.wake_confirmation_beep_duration, (int, float)) or self.wake_confirmation_beep_duration <= 0:
            errors.append("wake_confirmation_beep_duration must be a positive number")

        if self.voice_ack_earcon:
            if not isinstance(self.voice_ack_earcon_freq, int) or self.voice_ack_earcon_freq <= 0:
                errors.append("voice_ack_earcon_freq must be a positive integer")

            if not isinstance(self.voice_ack_earcon_duration, (int, float)) or self.voice_ack_earcon_duration <= 0:
                errors.append("voice_ack_earcon_duration must be a positive number")

        # Validate streaming TTS settings
        if self.stream_tts_boundary not in ["sentence", "paragraph"]:
            errors.append("stream_tts_boundary must be 'sentence' or 'paragraph'")

        if isinstance(self.stream_tts_first_chunk_target_s, bool) or not isinstance(self.stream_tts_first_chunk_target_s, int) or self.stream_tts_first_chunk_target_s < 1:
            errors.append("stream_tts_first_chunk_target_s must be an integer >= 1")

        if isinstance(self.stream_tts_buffer_chunks, bool) or not isinstance(self.stream_tts_buffer_chunks, int) or self.stream_tts_buffer_chunks < 1:
            errors.append("stream_tts_buffer_chunks must be an integer >= 1")

        if isinstance(self.stream_tts_tts_join_timeout_s, bool) or not isinstance(self.stream_tts_tts_join_timeout_s, int) or self.stream_tts_tts_join_timeout_s < 1:
            errors.append("stream_tts_tts_join_timeout_s must be an integer >= 1")

        if isinstance(self.stream_tts_player_join_timeout_s, bool) or not isinstance(self.stream_tts_player_join_timeout_s, int) or self.stream_tts_player_join_timeout_s < 1:
            errors.append("stream_tts_player_join_timeout_s must be an integer >= 1")

        # Report all errors
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
            logging.error(error_msg)
            raise ValueError(error_msg)

    def get(self, key):
            return self.config.get(key, self.defaults[key])
