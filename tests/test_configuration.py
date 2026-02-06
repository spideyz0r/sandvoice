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
    @patch('builtins.print')
    def test_deprecation_warning_for_linux_warnings(self, mock_print, mock_get_optimal):
        """Test that linux_warnings config triggers deprecation warning"""
        mock_get_optimal.return_value = 2

        # Set linux_warnings to a non-default value
        self.write_config({"linux_warnings": "disabled"})

        Config()

        # Should have printed deprecation warning
        warning_calls = [call for call in mock_print.call_args_list
                        if len(call[0]) > 0 and 'deprecated' in call[0][0].lower()]
        self.assertGreater(len(warning_calls), 0, "Should print deprecation warning")

    @patch('common.configuration.get_optimal_channels')
    @patch('builtins.print')
    def test_no_warning_when_linux_warnings_not_set(self, mock_print, mock_get_optimal):
        """Test that no deprecation warning when linux_warnings not explicitly set"""
        mock_get_optimal.return_value = 2

        # Don't set linux_warnings - uses default
        self.write_config({"channels": 2})

        config = Config()
        self.assertEqual(config.channels, 2)

        # Should NOT print deprecation warning
        warning_calls = [call for call in mock_print.call_args_list
                        if len(call[0]) > 0 and 'deprecated' in call[0][0].lower()]
        self.assertEqual(len(warning_calls), 0, "Should not print deprecation warning")

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

    def test_invalid_beep_freq(self):
        """Test that negative beep frequency raises error"""
        self.write_config({"wake_confirmation_beep_freq": -100})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("wake_confirmation_beep_freq must be a positive integer", str(context.exception))

    def test_invalid_beep_duration(self):
        """Test that negative beep duration raises error"""
        self.write_config({"wake_confirmation_beep_duration": -0.5})

        with self.assertRaises(ValueError) as context:
            Config()

        self.assertIn("wake_confirmation_beep_duration must be a positive number", str(context.exception))

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


if __name__ == '__main__':
    unittest.main()
