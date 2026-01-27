import unittest
import tempfile
import os
import yaml
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


if __name__ == '__main__':
    unittest.main()
