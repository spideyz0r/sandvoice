import shutil
import unittest
import tempfile
import os
import yaml
from unittest.mock import patch
from common.configuration import Config


class TestConfigurationValidation(unittest.TestCase):
    def setUp(self):
        """Create a temporary config file for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.yaml")

        # Mock HOME environment variable
        self.original_home = os.environ.get('HOME')
        os.environ['HOME'] = self.temp_dir

        # Create .sandvoice directory
        os.makedirs(os.path.join(self.temp_dir, ".sandvoice"), exist_ok=True)

    def tearDown(self):
        """Clean up temporary files"""
        if self.original_home:
            os.environ['HOME'] = self.original_home
        else:
            del os.environ['HOME']

        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_config(self, config_dict):
        """Helper to write config to temp file"""
        config_path = os.path.join(self.temp_dir, ".sandvoice", "config.yaml")
        with open(config_path, 'w') as f:
            yaml.dump(config_dict, f)

    def test_valid_default_configuration(self):
        """Test that default configuration is valid"""
        config = Config()
        # Should not raise any exceptions
        self.assertIsNotNone(config)

    def test_invalid_channels_value(self):
        """Test that invalid channels value raises error"""
        self.write_config({"channels": 5})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("channels must be 1 or 2", str(context.exception))

    def test_invalid_channels_type(self):
        """Test that invalid channels type raises error"""
        self.write_config({"channels": "invalid"})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("channels must be", str(context.exception))

    def test_invalid_bitrate_range(self):
        """Test that bitrate outside valid range raises error"""
        self.write_config({"bitrate": 500})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("bitrate must be between 32 and 320", str(context.exception))

    def test_invalid_rate_value(self):
        """Test that rate below minimum raises error"""
        self.write_config({"rate": 1000})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("rate must be at least 8000", str(context.exception))

    def test_invalid_chunk_value(self):
        """Test that chunk below minimum raises error"""
        self.write_config({"chunk": 100})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("chunk must be at least 256", str(context.exception))

    def test_invalid_api_timeout(self):
        """Test that invalid api_timeout raises error"""
        self.write_config({"api_timeout": 0})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("api_timeout must be at least 1", str(context.exception))

    def test_invalid_api_retry_attempts(self):
        """Test that invalid api_retry_attempts raises error"""
        self.write_config({"api_retry_attempts": -1})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("api_retry_attempts must be at least 1", str(context.exception))

    def test_empty_botname(self):
        """Test that empty botname raises error"""
        self.write_config({"botname": ""})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("botname must be a non-empty string", str(context.exception))

    def test_empty_language(self):
        """Test that empty language raises error"""
        self.write_config({"language": ""})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("language must be a non-empty string", str(context.exception))

    def test_default_verbosity_is_brief(self):
        """Test that verbosity defaults to brief"""
        config = Config()
        self.assertEqual(config.verbosity, "brief")

    def test_valid_verbosity_values(self):
        """Test that supported verbosity values are accepted"""
        for v in ["brief", "normal", "detailed", "BRIEF", " Normal "]:
            with self.subTest(verbosity=v):
                self.write_config({"verbosity": v})
                config = Config()
                self.assertIn(config.verbosity, ["brief", "normal", "detailed"])

    def test_invalid_verbosity_value(self):
        """Test that invalid verbosity raises error"""
        self.write_config({"verbosity": "verbose"})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("verbosity must be 'brief', 'normal', or 'detailed'", str(context.exception))

    def test_stream_tts_boundary_must_be_valid(self):
        self.write_config({
            "stream_tts_boundary": "invalid",
        })

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("stream_tts_boundary must be", str(context.exception))

    def test_stream_tts_first_chunk_target_s_must_be_positive_int(self):
        self.write_config({"stream_tts_first_chunk_target_s": 0})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("stream_tts_first_chunk_target_s must be", str(context.exception))

    def test_voice_ack_earcon_validation_only_when_enabled(self):
        """Freq/duration are only validated when earcon is enabled."""
        self.write_config({"voice_ack_earcon": "disabled", "voice_ack_earcon_freq": 0, "voice_ack_earcon_duration": 0})
        Config()  # should not raise

        self.write_config({"voice_ack_earcon": "enabled", "voice_ack_earcon_freq": 0, "voice_ack_earcon_duration": 0.06})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("voice_ack_earcon_freq must be a positive integer", str(context.exception))

    def test_invalid_beep_freq(self):
        self.write_config({"wake_confirmation_beep_freq": -100})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("wake_confirmation_beep_freq must be a positive integer", str(context.exception))

    def test_bool_beep_freq_rejected(self):
        """True is a bool (subclass of int), should not pass as a valid frequency."""
        self.write_config({"wake_confirmation_beep_freq": True})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("wake_confirmation_beep_freq must be a positive integer", str(context.exception))

    def test_bool_earcon_freq_rejected(self):
        """True is a bool (subclass of int), should not pass as a valid frequency."""
        self.write_config({"voice_ack_earcon": "enabled", "voice_ack_earcon_freq": True, "voice_ack_earcon_duration": 0.06})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("voice_ack_earcon_freq must be a positive integer", str(context.exception))

    def test_bool_beep_duration_rejected(self):
        """True is a bool (subclass of int), should not pass as a valid duration."""
        self.write_config({"wake_confirmation_beep_duration": True})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("wake_confirmation_beep_duration must be a positive number", str(context.exception))

    def test_bool_earcon_duration_rejected(self):
        """True is a bool (subclass of int), should not pass as a valid duration."""
        self.write_config({"voice_ack_earcon": "enabled", "voice_ack_earcon_freq": 600, "voice_ack_earcon_duration": True})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("voice_ack_earcon_duration must be a positive number", str(context.exception))

    def test_nan_beep_duration_rejected(self):
        """NaN should not pass as a valid duration."""
        self.write_config({"wake_confirmation_beep_duration": float("nan")})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("wake_confirmation_beep_duration must be a positive number", str(context.exception))

    def test_inf_earcon_duration_rejected(self):
        """Inf should not pass as a valid duration."""
        self.write_config({"voice_ack_earcon": "enabled", "voice_ack_earcon_freq": 600, "voice_ack_earcon_duration": float("inf")})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("voice_ack_earcon_duration must be a positive number", str(context.exception))

    def test_invalid_beep_duration(self):
        self.write_config({"wake_confirmation_beep_duration": -0.5})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("wake_confirmation_beep_duration must be a positive number", str(context.exception))

    def test_voice_ack_earcon_accepts_boolean_values(self):
        """Test that voice_ack_earcon can be specified as YAML boolean."""
        self.write_config({"voice_ack_earcon": True})
        config = Config()
        self.assertTrue(config.voice_ack_earcon)

        self.write_config({"voice_ack_earcon": False})
        config = Config()
        self.assertFalse(config.voice_ack_earcon)

    def test_invalid_falsy_verbosity_values(self):
        """Test that explicitly provided falsy verbosity values still fail validation"""
        for v in ["", "   ", False]:
            with self.subTest(verbosity=v):
                self.write_config({"verbosity": v})

                with self.assertRaises(ValueError) as context:
                    Config()

                self.assertIn("verbosity must be 'brief', 'normal', or 'detailed'", str(context.exception))

    def test_empty_location(self):
        """Test that empty location raises error"""
        self.write_config({"location": ""})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("location must be a non-empty string", str(context.exception))

    def test_invalid_unit(self):
        """Test that invalid unit value raises error"""
        self.write_config({"unit": "fahrenheit"})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("unit must be 'metric' or 'imperial'", str(context.exception))

    def test_invalid_speech_to_text_task(self):
        """Test that invalid speech_to_text_task raises error"""
        self.write_config({"speech_to_text_task": "invalid"})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("speech_to_text_task must be 'translate' or 'transcribe'", str(context.exception))

    def test_invalid_speech_to_text_translate_provider(self):
        """Test that invalid speech_to_text_translate_provider raises error"""
        self.write_config({"speech_to_text_translate_provider": "invalid"})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("speech_to_text_translate_provider must be 'whisper' or 'gpt'", str(context.exception))

    def test_empty_speech_to_text_translate_model(self):
        """Test that empty speech_to_text_translate_model raises error"""
        self.write_config({"speech_to_text_translate_model": ""})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("speech_to_text_translate_model must be a non-empty string", str(context.exception))

    def test_valid_metric_unit(self):
        """Test that metric unit is valid"""
        self.write_config({"unit": "metric"})
        config = Config()
        self.assertEqual(config.unit, "metric")

    def test_valid_imperial_unit(self):
        """Test that imperial unit is valid"""
        self.write_config({"unit": "imperial"})
        config = Config()
        self.assertEqual(config.unit, "imperial")

    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are reported together"""
        self.write_config({
            "channels": 5,
            "bitrate": 500,
            "unit": "invalid"
        })

        with self.assertRaises(ValueError) as context:
            Config()

        error_message = str(context.exception)
        self.assertIn("channels must be 1 or 2", error_message)
        self.assertIn("bitrate must be between 32 and 320", error_message)
        self.assertIn("unit must be 'metric' or 'imperial'", error_message)

    def test_valid_custom_configuration(self):
        """Test that valid custom configuration is accepted"""
        self.write_config({
            "channels": 1,
            "bitrate": 192,
            "rate": 48000,
            "chunk": 2048,
            "botname": "TestBot",
            "language": "Spanish",
            "location": "Madrid, Spain",
            "unit": "metric",
            "api_timeout": 30,
            "api_retry_attempts": 5
        })

        config = Config()
        self.assertEqual(config.channels, 1)
        self.assertEqual(config.bitrate, 192)
        self.assertEqual(config.rate, 48000)
        self.assertEqual(config.chunk, 2048)
        self.assertEqual(config.botname, "TestBot")
        self.assertEqual(config.language, "Spanish")
        self.assertEqual(config.location, "Madrid, Spain")
        self.assertEqual(config.unit, "metric")
        self.assertEqual(config.api_timeout, 30)
        self.assertEqual(config.api_retry_attempts, 5)

    @patch('common.configuration.get_optimal_channels')
    def test_auto_detect_channels_when_not_configured(self, mock_get_optimal):
        """Test that channels are auto-detected when not in config"""
        mock_get_optimal.return_value = 1

        # Don't set channels in config - should auto-detect
        self.write_config({"botname": "TestBot"})

        config = Config()

        # Should have called auto-detection with no arguments
        mock_get_optimal.assert_called_once_with()
        self.assertEqual(config.channels, 1)

    @patch('common.configuration.get_optimal_channels')
    def test_explicit_channels_overrides_auto_detect(self, mock_get_optimal):
        """Test that explicit channels config overrides auto-detection"""
        mock_get_optimal.return_value = 1

        # Explicitly set channels to 2
        self.write_config({"channels": 2})

        config = Config()

        # Should NOT have called auto-detection
        mock_get_optimal.assert_not_called()
        self.assertEqual(config.channels, 2)

    @patch('common.configuration.get_optimal_channels')
    def test_auto_detect_fallback_on_exception(self, mock_get_optimal):
        """Test that auto-detection falls back to 2 channels on exception"""
        mock_get_optimal.side_effect = Exception("PyAudio not available")

        # Don't set channels in config - should auto-detect and fallback
        self.write_config({"botname": "TestBot"})

        config = Config()

        # Should have attempted auto-detection
        mock_get_optimal.assert_called_once_with()
        # Should have fallen back to 2 channels
        self.assertEqual(config.channels, 2)

    def test_wake_word_default_configuration(self):
        """Test that default wake word configuration is valid"""
        config = Config()

        self.assertTrue(config.wake_word_enabled)
        self.assertEqual(config.wake_phrase, "hey sandvoice")
        self.assertEqual(config.wake_word_sensitivity, 0.5)
        self.assertEqual(config.porcupine_access_key, "")
        self.assertTrue(config.vad_enabled)
        self.assertEqual(config.vad_aggressiveness, 3)
        self.assertEqual(config.vad_silence_duration, 1.5)
        self.assertEqual(config.vad_frame_duration, 30)
        self.assertEqual(config.vad_timeout, 30)
        self.assertTrue(config.wake_confirmation_beep)
        self.assertEqual(config.wake_confirmation_beep_freq, 800)
        self.assertEqual(config.wake_confirmation_beep_duration, 0.1)
        self.assertTrue(config.visual_state_indicator)

    def test_invalid_wake_word_sensitivity_high(self):
        """Test that wake_word_sensitivity above 1.0 raises error"""
        self.write_config({"wake_word_sensitivity": 1.5})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("wake_word_sensitivity must be between 0.0 and 1.0", str(context.exception))

    def test_invalid_wake_word_sensitivity_low(self):
        """Test that wake_word_sensitivity below 0.0 raises error"""
        self.write_config({"wake_word_sensitivity": -0.1})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("wake_word_sensitivity must be between 0.0 and 1.0", str(context.exception))

    def test_empty_wake_phrase(self):
        """Test that empty wake_phrase raises error"""
        self.write_config({"wake_phrase": ""})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("wake_phrase must be a non-empty string", str(context.exception))

    def test_invalid_vad_aggressiveness_high(self):
        """Test that vad_aggressiveness above 3 raises error"""
        self.write_config({"vad_aggressiveness": 5})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("vad_aggressiveness must be between 0 and 3", str(context.exception))

    def test_invalid_vad_aggressiveness_low(self):
        """Test that vad_aggressiveness below 0 raises error"""
        self.write_config({"vad_aggressiveness": -1})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("vad_aggressiveness must be between 0 and 3", str(context.exception))

    def test_invalid_vad_silence_duration(self):
        """Test that negative vad_silence_duration raises error"""
        self.write_config({"vad_silence_duration": -1.0})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("vad_silence_duration must be a positive number", str(context.exception))

    def test_invalid_vad_frame_duration(self):
        """Test that invalid vad_frame_duration raises error"""
        self.write_config({"vad_frame_duration": 15})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("vad_frame_duration must be 10, 20, or 30", str(context.exception))

    def test_valid_vad_frame_durations(self):
        """Test that valid vad_frame_duration values are accepted"""
        for duration in [10, 20, 30]:
            with self.subTest(vad_frame_duration=duration):
                self.write_config({"vad_frame_duration": duration})
                config = Config()
                self.assertEqual(config.vad_frame_duration, duration)

    def test_invalid_vad_timeout(self):
        """Test that negative vad_timeout raises error"""
        self.write_config({"vad_timeout": -5})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("vad_timeout must be a positive number", str(context.exception))

    def test_valid_wake_word_configuration(self):
        """Test that valid custom wake word configuration is accepted"""
        self.write_config({
            "wake_word_enabled": "enabled",
            "wake_phrase": "hey assistant",
            "wake_word_sensitivity": 0.7,
            "porcupine_access_key": "test_key_123",
            "vad_enabled": "disabled",
            "vad_aggressiveness": 1,
            "vad_silence_duration": 2.0,
            "vad_frame_duration": 20,
            "vad_timeout": 45,
            "wake_confirmation_beep": "disabled",
            "wake_confirmation_beep_freq": 1000,
            "wake_confirmation_beep_duration": 0.2,
            "visual_state_indicator": "disabled"
        })

        config = Config()
        self.assertTrue(config.wake_word_enabled)
        self.assertEqual(config.wake_phrase, "hey assistant")
        self.assertEqual(config.wake_word_sensitivity, 0.7)
        self.assertEqual(config.porcupine_access_key, "test_key_123")
        self.assertFalse(config.vad_enabled)
        self.assertEqual(config.vad_aggressiveness, 1)
        self.assertEqual(config.vad_silence_duration, 2.0)
        self.assertEqual(config.vad_frame_duration, 20)
        self.assertEqual(config.vad_timeout, 45)
        self.assertFalse(config.wake_confirmation_beep)
        self.assertEqual(config.wake_confirmation_beep_freq, 1000)
        self.assertEqual(config.wake_confirmation_beep_duration, 0.2)
        self.assertFalse(config.visual_state_indicator)


class _TempHomeBase(unittest.TestCase):
    """Shared base: create a temporary HOME with a .sandvoice directory."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_home = os.environ.get('HOME')
        os.environ['HOME'] = self.temp_dir
        os.makedirs(os.path.join(self.temp_dir, ".sandvoice"), exist_ok=True)

    def tearDown(self):
        if self.original_home:
            os.environ['HOME'] = self.original_home
        else:
            del os.environ['HOME']
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_config(self, config_dict):
        config_path = os.path.join(self.temp_dir, ".sandvoice", "config.yaml")
        with open(config_path, 'w') as f:
            yaml.dump(config_dict, f)


class TestSchedulerEnabledFlag(_TempHomeBase):
    """scheduler_enabled must accept booleans and common truthy/falsy strings."""

    def test_scheduler_enabled_string_enabled(self):
        self.write_config({"scheduler_enabled": "enabled"})
        config = Config()
        self.assertTrue(config.scheduler_enabled)

    def test_scheduler_enabled_string_true(self):
        self.write_config({"scheduler_enabled": "true"})
        config = Config()
        self.assertTrue(config.scheduler_enabled)

    def test_scheduler_enabled_string_yes(self):
        self.write_config({"scheduler_enabled": "yes"})
        config = Config()
        self.assertTrue(config.scheduler_enabled)

    def test_scheduler_enabled_string_1(self):
        self.write_config({"scheduler_enabled": "1"})
        config = Config()
        self.assertTrue(config.scheduler_enabled)

    def test_scheduler_enabled_string_on(self):
        self.write_config({"scheduler_enabled": "on"})
        config = Config()
        self.assertTrue(config.scheduler_enabled)

    def test_scheduler_enabled_bool_true(self):
        self.write_config({"scheduler_enabled": True})
        config = Config()
        self.assertTrue(config.scheduler_enabled)

    def test_scheduler_enabled_bool_false(self):
        self.write_config({"scheduler_enabled": False})
        config = Config()
        self.assertFalse(config.scheduler_enabled)

    def test_scheduler_enabled_string_disabled(self):
        self.write_config({"scheduler_enabled": "disabled"})
        config = Config()
        self.assertFalse(config.scheduler_enabled)

    def test_scheduler_enabled_default_is_false(self):
        # No override — default is "disabled"
        config = Config()
        self.assertFalse(config.scheduler_enabled)


class TestTasksFileConfig(unittest.TestCase):
    """tasks_file_path and tasks.yaml loading must behave predictably."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_home = os.environ.get('HOME')
        os.environ['HOME'] = self.temp_dir
        os.makedirs(os.path.join(self.temp_dir, '.sandvoice'), exist_ok=True)
        self.config_path = os.path.join(self.temp_dir, '.sandvoice', 'config.yaml')

    def tearDown(self):
        if self.original_home is not None:
            os.environ['HOME'] = self.original_home
        else:
            del os.environ['HOME']
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_config(self, data):
        import yaml
        with open(self.config_path, 'w') as f:
            yaml.dump(data, f)

    def test_tasks_file_path_default(self):
        config = Config()
        expected = os.path.join(self.temp_dir, ".sandvoice", "tasks.yaml")
        self.assertEqual(config.tasks_file_path, expected)
        self.assertFalse(config.tasks_file_exists)
        self.assertEqual(config.tasks, [])

    def test_tasks_file_path_custom_value_is_expanded(self):
        self.write_config({"tasks_file_path": "~/.sandvoice/custom-tasks.yaml"})
        config = Config()
        expected = os.path.join(self.temp_dir, ".sandvoice", "custom-tasks.yaml")
        self.assertEqual(config.tasks_file_path, expected)

    def test_tasks_file_missing_returns_empty_list(self):
        config = Config()
        self.assertFalse(config.tasks_file_exists)
        self.assertEqual(config.tasks, [])

    def test_tasks_file_parses_yaml_list(self):
        tasks_path = os.path.join(self.temp_dir, ".sandvoice", "tasks.yaml")
        with open(tasks_path, "w") as f:
            yaml.dump([
                {"name": "t1", "schedule_type": "interval", "schedule_value": "60",
                 "action_type": "speak", "action_payload": {"text": "hello"}},
            ], f)
        config = Config()
        self.assertTrue(config.tasks_file_exists)
        self.assertEqual(len(config.tasks), 1)
        self.assertEqual(config.tasks[0]["name"], "t1")

    def test_tasks_file_null_yields_empty_list(self):
        tasks_path = os.path.join(self.temp_dir, ".sandvoice", "tasks.yaml")
        with open(tasks_path, "w") as f:
            yaml.dump(None, f)
        config = Config()
        self.assertEqual(config.tasks, [])

    def test_tasks_file_non_list_raises_value_error(self):
        tasks_path = os.path.join(self.temp_dir, ".sandvoice", "tasks.yaml")
        with open(tasks_path, "w") as f:
            yaml.dump({"name": "bad"}, f)
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("tasks file must contain a YAML list", str(context.exception))
        self.assertIn(tasks_path, str(context.exception))

    def test_tasks_file_path_directory_raises_value_error(self):
        tasks_dir = os.path.join(self.temp_dir, ".sandvoice", "tasks-dir")
        os.makedirs(tasks_dir, exist_ok=True)
        self.write_config({"tasks_file_path": "~/.sandvoice/tasks-dir"})
        with self.assertRaises(ValueError) as context:
            Config()
        self.assertIn("tasks_file_path must point to a file", str(context.exception))
        self.assertIn(tasks_dir, str(context.exception))

    def test_legacy_tasks_key_logs_warning(self):
        self.write_config({"tasks": []})
        with self.assertLogs("common.configuration", level="WARNING") as cm:
            config = Config()
        self.assertEqual(config.tasks, [])
        self.assertTrue(any("tasks" in line and "ignored" in line for line in cm.output))


class TestCacheConfig(_TempHomeBase):
    """cache_enabled, cache_weather_ttl_s, cache_weather_max_stale_s defaults and clamping."""

    def test_cache_disabled_by_default(self):
        self.write_config({})
        config = Config()
        self.assertFalse(config.cache_enabled)

    def test_cache_enabled_string(self):
        self.write_config({"cache_enabled": "enabled"})
        config = Config()
        self.assertTrue(config.cache_enabled)

    def test_cache_enabled_bool_true(self):
        self.write_config({"cache_enabled": True})
        config = Config()
        self.assertTrue(config.cache_enabled)

    def test_cache_weather_ttl_default(self):
        self.write_config({})
        config = Config()
        self.assertEqual(config.cache_weather_ttl_s, 10800)

    def test_cache_weather_max_stale_default(self):
        self.write_config({})
        config = Config()
        self.assertEqual(config.cache_weather_max_stale_s, 21600)

    def test_cache_max_stale_clamped_to_ttl_when_smaller(self):
        # max_stale < ttl → should be clamped to ttl
        self.write_config({"cache_weather_ttl_s": 7200, "cache_weather_max_stale_s": 3600})
        config = Config()
        self.assertEqual(config.cache_weather_max_stale_s, config.cache_weather_ttl_s)

    def test_cache_max_stale_equals_ttl_is_valid(self):
        self.write_config({"cache_weather_ttl_s": 3600, "cache_weather_max_stale_s": 3600})
        config = Config()
        self.assertEqual(config.cache_weather_max_stale_s, 3600)

    def test_cache_ttl_invalid_falls_back_to_default(self):
        self.write_config({"cache_weather_ttl_s": "bad"})
        config = Config()
        self.assertEqual(config.cache_weather_ttl_s, 10800)

    def test_cache_enabled_truthy_variants(self):
        """All truthy strings accepted by scheduler_enabled must also work for cache_enabled."""
        for value in ("true", "yes", "1", "on"):
            with self.subTest(value=value):
                self.write_config({"cache_enabled": value})
                config = Config()
                self.assertTrue(config.cache_enabled, msg=f"cache_enabled={value!r} should be truthy")


class TestLogLevel(_TempHomeBase):
    """Tests for log_level config key and config.debug property (Plan 28)."""

    def test_log_level_default_is_warning(self):
        """Default log_level is 'warning'."""
        config = Config()
        self.assertEqual(config.log_level, "warning")

    def test_log_level_info(self):
        """log_level: info is stored correctly."""
        self.write_config({"log_level": "info"})
        config = Config()
        self.assertEqual(config.log_level, "info")

    def test_log_level_debug(self):
        """log_level: debug is stored correctly."""
        self.write_config({"log_level": "debug"})
        config = Config()
        self.assertEqual(config.log_level, "debug")

    def test_log_level_invalid_falls_back_to_warning(self):
        """An unrecognised log_level value is silently normalised to 'warning'."""
        self.write_config({"log_level": "verbose"})
        config = Config()
        self.assertEqual(config.log_level, "warning")

    def test_debug_property_false_when_warning(self):
        """config.debug is False when log_level is 'warning'."""
        config = Config()
        self.assertFalse(config.debug)

    def test_debug_property_false_when_info(self):
        """config.debug is False when log_level is 'info'."""
        self.write_config({"log_level": "info"})
        config = Config()
        self.assertFalse(config.debug)

    def test_debug_property_true_when_debug(self):
        """config.debug is True when log_level is 'debug'."""
        self.write_config({"log_level": "debug"})
        config = Config()
        self.assertTrue(config.debug)

class TestMergePluginDefaults(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_home = os.environ.get('HOME')
        os.environ['HOME'] = self.temp_dir
        os.makedirs(os.path.join(self.temp_dir, ".sandvoice"), exist_ok=True)
        self.config_file = os.path.join(self.temp_dir, ".sandvoice", "config.yaml")

    def tearDown(self):
        if self.original_home is not None:
            os.environ['HOME'] = self.original_home
        else:
            os.environ.pop('HOME', None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_config(self, data):
        with open(self.config_file, "w") as f:
            yaml.dump(data, f)

    def _make_manifest(self, defaults):
        from common.plugin_loader import PluginManifest
        return PluginManifest(name="test", route_description="test", config_defaults=defaults)

    def test_plugin_default_fills_builtin_default_key_when_user_not_set(self):
        """Plugin manifest can override a built-in default when the user hasn't set the key."""
        self.write_config({"openai_api_key": "key"})
        config = Config()
        manifest = self._make_manifest({"location": "Paris, FR"})
        config.merge_plugin_defaults([manifest])
        self.assertEqual(config.location, "Paris, FR")

    def test_user_config_wins_over_plugin_default(self):
        """User-set keys always take priority over plugin manifest defaults."""
        self.write_config({"openai_api_key": "key", "location": "Berlin, DE"})
        config = Config()
        manifest = self._make_manifest({"location": "Paris, FR"})
        config.merge_plugin_defaults([manifest])
        self.assertEqual(config.location, "Berlin, DE")

    def test_first_plugin_wins_for_same_key(self):
        """When two manifests provide the same key, the first one wins."""
        self.write_config({"openai_api_key": "key"})
        config = Config()
        m1 = self._make_manifest({"location": "Paris, FR"})
        m2 = self._make_manifest({"location": "Tokyo, JP"})
        config.merge_plugin_defaults([m1, m2])
        self.assertEqual(config.location, "Paris, FR")

    def test_plugin_only_key_applied(self):
        """A key not in built-in defaults and not set by user is applied from manifest."""
        self.write_config({"openai_api_key": "key"})
        config = Config()
        manifest = self._make_manifest({"my_plugin_key": "plugin_value"})
        config.merge_plugin_defaults([manifest])
        self.assertEqual(config.get("my_plugin_key"), "plugin_value")


class TestVoiceFillerConfig(_TempHomeBase):
    """Tests for voice_filler_delay_ms and voice_filler_phrases config parsing."""

    def test_delay_default(self):
        config = Config()
        self.assertEqual(config.voice_filler_delay_ms, 800)

    def test_delay_valid_custom(self):
        self.write_config({"voice_filler_delay_ms": 500})
        config = Config()
        self.assertEqual(config.voice_filler_delay_ms, 500)

    def test_delay_negative_clamped_to_zero(self):
        self.write_config({"voice_filler_delay_ms": -100})
        config = Config()
        self.assertEqual(config.voice_filler_delay_ms, 0)

    def test_delay_non_int_falls_back_to_default(self):
        self.write_config({"voice_filler_delay_ms": "fast"})
        config = Config()
        self.assertEqual(config.voice_filler_delay_ms, 800)

    def test_delay_bool_falls_back_to_default(self):
        self.write_config({"voice_filler_delay_ms": True})
        config = Config()
        self.assertEqual(config.voice_filler_delay_ms, 800)

    def test_delay_zero_is_valid(self):
        self.write_config({"voice_filler_delay_ms": 0})
        config = Config()
        self.assertEqual(config.voice_filler_delay_ms, 0)

    def test_phrases_default_is_nonempty_list(self):
        config = Config()
        self.assertIsInstance(config.voice_filler_phrases, list)
        self.assertGreater(len(config.voice_filler_phrases), 0)

    def test_phrases_empty_list_disables_feature(self):
        self.write_config({"voice_filler_phrases": []})
        config = Config()
        self.assertEqual(config.voice_filler_phrases, [])

    def test_phrases_custom_list(self):
        self.write_config({"voice_filler_phrases": ["Hold on.", "One sec."]})
        config = Config()
        self.assertEqual(config.voice_filler_phrases, ["Hold on.", "One sec."])

    def test_phrases_none_falls_back_to_defaults(self):
        self.write_config({"voice_filler_phrases": None})
        config = Config()
        self.assertGreater(len(config.voice_filler_phrases), 0)

    def test_phrases_non_list_falls_back_to_defaults(self):
        self.write_config({"voice_filler_phrases": "One sec."})
        config = Config()
        self.assertIsInstance(config.voice_filler_phrases, list)
        self.assertGreater(len(config.voice_filler_phrases), 0)

    def test_phrases_filters_empty_strings(self):
        self.write_config({"voice_filler_phrases": ["Valid phrase.", "", None, "   ", "Another."]})
        config = Config()
        # Empty strings, None, and whitespace-only entries are filtered; valid phrases kept
        self.assertEqual(config.voice_filler_phrases, ["Valid phrase.", "Another."])

    def test_phrases_strips_surrounding_whitespace(self):
        self.write_config({"voice_filler_phrases": ["  One sec.  ", "Got it."]})
        config = Config()
        self.assertEqual(config.voice_filler_phrases, ["One sec.", "Got it."])


class TestCacheAutoRefreshConfig(_TempHomeBase):
    """cache_auto_refresh parsing and validation."""

    def test_defaults_to_empty_list(self):
        self.write_config({})
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_valid_minimal_entry(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "hacker-news", "interval_s": 28800},
            ]
        })
        config = Config()
        self.assertEqual(len(config.cache_auto_refresh), 1)
        entry = config.cache_auto_refresh[0]
        self.assertEqual(entry["plugin"], "hacker-news")
        self.assertEqual(entry["interval_s"], 28800)
        self.assertEqual(entry["ttl_s"], 28800)          # defaults to interval_s
        self.assertEqual(entry["max_stale_s"], 43200)    # int(28800 * 1.5)
        self.assertEqual(entry["query"], "hacker-news")  # defaults to plugin

    def test_explicit_ttl_and_max_stale(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "ttl_s": 3600, "max_stale_s": 10800},
            ]
        })
        config = Config()
        entry = config.cache_auto_refresh[0]
        self.assertEqual(entry["ttl_s"], 3600)
        self.assertEqual(entry["max_stale_s"], 10800)

    def test_optional_rss_url_forwarded(self):
        url = "https://example.com/rss"
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "rss_url": url},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["rss_url"], url)

    def test_query_defaults_to_plugin_name(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "weather", "interval_s": 10800},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["query"], "weather")

    def test_explicit_query_preserved(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "weather", "interval_s": 10800, "query": "current weather"},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["query"], "current weather")

    def test_missing_plugin_field_skips_entry(self):
        self.write_config({
            "cache_auto_refresh": [
                {"interval_s": 3600},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_missing_interval_s_skips_entry(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news"},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_non_positive_interval_s_skips_entry(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 0},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_invalid_entry_type_skips(self):
        self.write_config({"cache_auto_refresh": ["not-a-dict"]})
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_non_list_value_ignored(self):
        self.write_config({"cache_auto_refresh": "not-a-list"})
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_multiple_entries(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "hacker-news", "interval_s": 28800},
                {"plugin": "news", "interval_s": 7200},
            ]
        })
        config = Config()
        self.assertEqual(len(config.cache_auto_refresh), 2)
        self.assertEqual(config.cache_auto_refresh[0]["plugin"], "hacker-news")
        self.assertEqual(config.cache_auto_refresh[1]["plugin"], "news")

    def test_invalid_ttl_falls_back_to_interval(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "ttl_s": "bad"},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["ttl_s"], 7200)

    def test_whitespace_only_plugin_skips_entry(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "   ", "interval_s": 7200},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_empty_rss_url_not_included(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "rss_url": ""},
            ]
        })
        config = Config()
        self.assertNotIn("rss_url", config.cache_auto_refresh[0])

    def test_whitespace_rss_url_not_included(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "rss_url": "   "},
            ]
        })
        config = Config()
        self.assertNotIn("rss_url", config.cache_auto_refresh[0])

    def test_max_stale_clamped_to_ttl_when_smaller(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "ttl_s": 5000, "max_stale_s": 3000},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["max_stale_s"], 5000)

    def test_max_stale_default_is_integer(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200},
            ]
        })
        config = Config()
        self.assertIsInstance(config.cache_auto_refresh[0]["max_stale_s"], int)

    def test_bool_interval_s_skips_entry(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": True},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_bool_ttl_s_falls_back_to_interval(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "ttl_s": True},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["ttl_s"], 7200)

    def test_bool_max_stale_s_falls_back_to_default(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "max_stale_s": True},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["max_stale_s"], int(7200 * 1.5))

    def test_float_interval_s_skips_entry(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 1.9},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh, [])

    def test_whole_float_interval_s_accepted(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200.0},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["interval_s"], 7200)

    def test_float_ttl_s_falls_back_to_interval(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "ttl_s": 1.9},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["ttl_s"], 7200)

    def test_float_max_stale_s_falls_back_to_default(self):
        self.write_config({
            "cache_auto_refresh": [
                {"plugin": "news", "interval_s": 7200, "max_stale_s": 1.9},
            ]
        })
        config = Config()
        self.assertEqual(config.cache_auto_refresh[0]["max_stale_s"], int(7200 * 1.5))


class TestCacheWarmupConfig(_TempHomeBase):
    """cache_warmup_timeout_s, cache_warmup_retries, cache_warmup_retry_delay_s defaults and validation."""

    def test_defaults(self):
        self.write_config({})
        config = Config()
        self.assertEqual(config.cache_warmup_timeout_s, 15)
        self.assertEqual(config.cache_warmup_retries, 3)
        self.assertAlmostEqual(config.cache_warmup_retry_delay_s, 2.0)

    def test_custom_timeout(self):
        self.write_config({"cache_warmup_timeout_s": 30})
        config = Config()
        self.assertEqual(config.cache_warmup_timeout_s, 30)

    def test_timeout_zero_allowed(self):
        self.write_config({"cache_warmup_timeout_s": 0})
        config = Config()
        self.assertEqual(config.cache_warmup_timeout_s, 0)

    def test_negative_timeout_clamped_to_zero(self):
        self.write_config({"cache_warmup_timeout_s": -5})
        config = Config()
        self.assertEqual(config.cache_warmup_timeout_s, 0)

    def test_invalid_timeout_falls_back_to_default(self):
        self.write_config({"cache_warmup_timeout_s": "bad"})
        config = Config()
        self.assertEqual(config.cache_warmup_timeout_s, 15)

    def test_custom_retries(self):
        self.write_config({"cache_warmup_retries": 5})
        config = Config()
        self.assertEqual(config.cache_warmup_retries, 5)

    def test_retries_zero_allowed(self):
        self.write_config({"cache_warmup_retries": 0})
        config = Config()
        self.assertEqual(config.cache_warmup_retries, 0)

    def test_negative_retries_clamped_to_zero(self):
        self.write_config({"cache_warmup_retries": -1})
        config = Config()
        self.assertEqual(config.cache_warmup_retries, 0)

    def test_invalid_retries_falls_back_to_default(self):
        self.write_config({"cache_warmup_retries": "bad"})
        config = Config()
        self.assertEqual(config.cache_warmup_retries, 3)

    def test_custom_retry_delay(self):
        self.write_config({"cache_warmup_retry_delay_s": 5.0})
        config = Config()
        self.assertAlmostEqual(config.cache_warmup_retry_delay_s, 5.0)

    def test_retry_delay_zero_allowed(self):
        self.write_config({"cache_warmup_retry_delay_s": 0})
        config = Config()
        self.assertAlmostEqual(config.cache_warmup_retry_delay_s, 0.0)

    def test_negative_retry_delay_clamped_to_zero(self):
        self.write_config({"cache_warmup_retry_delay_s": -1})
        config = Config()
        self.assertAlmostEqual(config.cache_warmup_retry_delay_s, 0.0)

    def test_invalid_retry_delay_falls_back_to_default(self):
        self.write_config({"cache_warmup_retry_delay_s": "bad"})
        config = Config()
        self.assertAlmostEqual(config.cache_warmup_retry_delay_s, 2.0)


if __name__ == '__main__':
    unittest.main()
