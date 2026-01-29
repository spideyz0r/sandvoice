import unittest
from unittest.mock import Mock, patch, MagicMock
from common.audio_device_detection import (
    get_audio_instance,
    get_device_count,
    get_default_input_device,
    get_default_output_device,
    get_optimal_channels,
    get_all_devices,
    get_device_summary,
    log_device_info
)


class TestGetAudioInstance(unittest.TestCase):
    @patch('common.audio_device_detection.pyaudio.PyAudio')
    def test_success(self, mock_pyaudio):
        """Test successful PyAudio instance creation"""
        mock_instance = Mock()
        mock_pyaudio.return_value = mock_instance

        result = get_audio_instance()

        self.assertEqual(result, mock_instance)
        mock_pyaudio.assert_called_once()

    @patch('common.audio_device_detection.pyaudio.PyAudio')
    def test_failure(self, mock_pyaudio):
        """Test PyAudio instance creation failure"""
        mock_pyaudio.side_effect = Exception("PyAudio not available")

        result = get_audio_instance()

        self.assertIsNone(result)


class TestGetDeviceCount(unittest.TestCase):
    def test_with_audio_instance(self):
        """Test getting device count with provided audio instance"""
        mock_audio = Mock()
        mock_audio.get_device_count.return_value = 5

        result = get_device_count(mock_audio)

        self.assertEqual(result, 5)
        mock_audio.get_device_count.assert_called_once()
        mock_audio.terminate.assert_not_called()

    @patch('common.audio_device_detection.get_audio_instance')
    def test_without_audio_instance(self, mock_get_audio):
        """Test getting device count without provided audio instance"""
        mock_audio = Mock()
        mock_audio.get_device_count.return_value = 3
        mock_get_audio.return_value = mock_audio

        result = get_device_count()

        self.assertEqual(result, 3)
        mock_audio.terminate.assert_called_once()

    @patch('common.audio_device_detection.get_audio_instance')
    def test_pyaudio_unavailable(self, mock_get_audio):
        """Test device count when PyAudio unavailable"""
        mock_get_audio.return_value = None

        result = get_device_count()

        self.assertEqual(result, 0)

    def test_exception_handling(self):
        """Test device count when get_device_count raises exception"""
        mock_audio = Mock()
        mock_audio.get_device_count.side_effect = Exception("Error")

        result = get_device_count(mock_audio)

        self.assertEqual(result, 0)


class TestGetDefaultInputDevice(unittest.TestCase):
    def test_success(self):
        """Test getting default input device successfully"""
        mock_audio = Mock()
        device_info = {'name': 'Built-in Microphone', 'index': 0, 'maxInputChannels': 2}
        mock_audio.get_default_input_device_info.return_value = device_info

        result = get_default_input_device(mock_audio)

        self.assertEqual(result, device_info)
        mock_audio.terminate.assert_not_called()

    @patch('common.audio_device_detection.get_audio_instance')
    def test_with_cleanup(self, mock_get_audio):
        """Test getting default input device with automatic cleanup"""
        mock_audio = Mock()
        device_info = {'name': 'USB Microphone', 'index': 1}
        mock_audio.get_default_input_device_info.return_value = device_info
        mock_get_audio.return_value = mock_audio

        result = get_default_input_device()

        self.assertEqual(result, device_info)
        mock_audio.terminate.assert_called_once()

    @patch('common.audio_device_detection.get_audio_instance')
    def test_pyaudio_unavailable(self, mock_get_audio):
        """Test when PyAudio is unavailable"""
        mock_get_audio.return_value = None

        result = get_default_input_device()

        self.assertIsNone(result)

    def test_exception_handling(self):
        """Test when getting default input device raises exception"""
        mock_audio = Mock()
        mock_audio.get_default_input_device_info.side_effect = Exception("No input device")

        result = get_default_input_device(mock_audio)

        self.assertIsNone(result)


class TestGetDefaultOutputDevice(unittest.TestCase):
    def test_success(self):
        """Test getting default output device successfully"""
        mock_audio = Mock()
        device_info = {'name': 'Built-in Speaker', 'index': 0, 'maxOutputChannels': 2}
        mock_audio.get_default_output_device_info.return_value = device_info

        result = get_default_output_device(mock_audio)

        self.assertEqual(result, device_info)

    @patch('common.audio_device_detection.get_audio_instance')
    def test_pyaudio_unavailable(self, mock_get_audio):
        """Test when PyAudio is unavailable"""
        mock_get_audio.return_value = None

        result = get_default_output_device()

        self.assertIsNone(result)

    def test_exception_handling(self):
        """Test when getting default output device raises exception"""
        mock_audio = Mock()
        mock_audio.get_default_output_device_info.side_effect = Exception("No output device")

        result = get_default_output_device(mock_audio)

        self.assertIsNone(result)


class TestGetOptimalChannels(unittest.TestCase):
    @patch('common.audio_device_detection.is_macos')
    def test_macos_always_mono(self, mock_is_macos):
        """Test macOS always returns 1 channel (mono)"""
        mock_is_macos.return_value = True

        result = get_optimal_channels()

        self.assertEqual(result, 1)

    @patch('common.audio_device_detection.is_macos')
    def test_macos_ignores_device_info(self, mock_is_macos):
        """Test macOS returns mono even with stereo device"""
        mock_is_macos.return_value = True
        device_info = {'maxInputChannels': 2}

        result = get_optimal_channels(device_info)

        self.assertEqual(result, 1)

    @patch('common.audio_device_detection.is_macos')
    def test_linux_stereo_device(self, mock_is_macos):
        """Test Linux with stereo device returns 2 channels"""
        mock_is_macos.return_value = False
        device_info = {'maxInputChannels': 2}

        result = get_optimal_channels(device_info)

        self.assertEqual(result, 2)

    @patch('common.audio_device_detection.is_macos')
    def test_linux_mono_device(self, mock_is_macos):
        """Test Linux with mono device returns 1 channel"""
        mock_is_macos.return_value = False
        device_info = {'maxInputChannels': 1}

        result = get_optimal_channels(device_info)

        self.assertEqual(result, 1)

    @patch('common.audio_device_detection.is_macos')
    def test_linux_no_device_info(self, mock_is_macos):
        """Test Linux without device info defaults to stereo"""
        mock_is_macos.return_value = False

        result = get_optimal_channels()

        self.assertEqual(result, 2)

    @patch('common.audio_device_detection.is_macos')
    def test_linux_multichannel_device(self, mock_is_macos):
        """Test Linux with multi-channel device returns stereo"""
        mock_is_macos.return_value = False
        device_info = {'maxInputChannels': 8}

        result = get_optimal_channels(device_info)

        self.assertEqual(result, 2)


class TestGetAllDevices(unittest.TestCase):
    def test_multiple_devices(self):
        """Test getting all devices successfully"""
        mock_audio = Mock()
        mock_audio.get_device_count.return_value = 3
        mock_audio.get_device_info_by_index.side_effect = [
            {'name': 'Device 1', 'index': 0},
            {'name': 'Device 2', 'index': 1},
            {'name': 'Device 3', 'index': 2},
        ]

        result = get_all_devices(mock_audio)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['name'], 'Device 1')
        self.assertEqual(result[2]['name'], 'Device 3')

    def test_skip_invalid_device(self):
        """Test that invalid devices are skipped"""
        mock_audio = Mock()
        mock_audio.get_device_count.return_value = 3
        mock_audio.get_device_info_by_index.side_effect = [
            {'name': 'Device 1', 'index': 0},
            Exception("Invalid device"),
            {'name': 'Device 3', 'index': 2},
        ]

        result = get_all_devices(mock_audio)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'Device 1')
        self.assertEqual(result[1]['name'], 'Device 3')

    @patch('common.audio_device_detection.get_audio_instance')
    def test_pyaudio_unavailable(self, mock_get_audio):
        """Test when PyAudio is unavailable"""
        mock_get_audio.return_value = None

        result = get_all_devices()

        self.assertEqual(result, [])

    def test_exception_handling(self):
        """Test when get_device_count raises exception"""
        mock_audio = Mock()
        mock_audio.get_device_count.side_effect = Exception("Error")

        result = get_all_devices(mock_audio)

        self.assertEqual(result, [])


class TestGetDeviceSummary(unittest.TestCase):
    @patch('common.audio_device_detection.get_audio_instance')
    def test_pyaudio_unavailable(self, mock_get_audio):
        """Test device summary when PyAudio unavailable"""
        mock_get_audio.return_value = None

        result = get_device_summary()

        self.assertFalse(result['pyaudio_available'])
        self.assertEqual(result['device_count'], 0)
        self.assertIsNone(result['default_input'])
        self.assertIsNone(result['default_output'])
        self.assertIn(result['optimal_channels'], [1, 2])

    @patch('common.audio_device_detection.get_device_count')
    @patch('common.audio_device_detection.get_default_output_device')
    @patch('common.audio_device_detection.get_default_input_device')
    @patch('common.audio_device_detection.get_audio_instance')
    def test_full_summary(self, mock_get_audio, mock_get_input, mock_get_output, mock_get_count):
        """Test complete device summary with all info"""
        mock_audio = Mock()
        mock_get_audio.return_value = mock_audio
        mock_get_count.return_value = 5

        input_device = {
            'name': 'Built-in Microphone',
            'index': 0,
            'maxInputChannels': 2
        }
        output_device = {
            'name': 'Built-in Speaker',
            'index': 1,
            'maxOutputChannels': 2
        }
        mock_get_input.return_value = input_device
        mock_get_output.return_value = output_device

        result = get_device_summary()

        self.assertTrue(result['pyaudio_available'])
        self.assertEqual(result['device_count'], 5)
        self.assertEqual(result['default_input']['name'], 'Built-in Microphone')
        self.assertEqual(result['default_input']['index'], 0)
        self.assertEqual(result['default_input']['max_channels'], 2)
        self.assertEqual(result['default_output']['name'], 'Built-in Speaker')
        mock_audio.terminate.assert_called_once()

    @patch('common.audio_device_detection.get_device_count')
    @patch('common.audio_device_detection.get_default_output_device')
    @patch('common.audio_device_detection.get_default_input_device')
    @patch('common.audio_device_detection.get_audio_instance')
    def test_no_devices(self, mock_get_audio, mock_get_input, mock_get_output, mock_get_count):
        """Test device summary with no devices"""
        mock_audio = Mock()
        mock_get_audio.return_value = mock_audio
        mock_get_count.return_value = 0
        mock_get_input.return_value = None
        mock_get_output.return_value = None

        result = get_device_summary()

        self.assertTrue(result['pyaudio_available'])
        self.assertEqual(result['device_count'], 0)
        self.assertIsNone(result['default_input'])
        self.assertIsNone(result['default_output'])


class TestLogDeviceInfo(unittest.TestCase):
    @patch('builtins.print')
    @patch('common.audio_device_detection.get_device_summary')
    def test_debug_enabled(self, mock_get_summary, mock_print):
        """Test logging when debug is enabled"""
        mock_config = Mock()
        mock_config.debug = True

        mock_get_summary.return_value = {
            'pyaudio_available': True,
            'device_count': 2,
            'default_input': {
                'name': 'USB Microphone',
                'index': 1,
                'max_channels': 1
            },
            'default_output': {
                'name': 'Speakers',
                'index': 0,
                'max_channels': 2
            },
            'optimal_channels': 1
        }

        log_device_info(mock_config)

        # Verify print was called multiple times
        self.assertGreater(mock_print.call_count, 5)

    @patch('builtins.print')
    @patch('common.audio_device_detection.get_device_summary')
    def test_debug_disabled(self, mock_get_summary, mock_print):
        """Test logging when debug is disabled"""
        mock_config = Mock()
        mock_config.debug = False

        log_device_info(mock_config)

        mock_print.assert_not_called()
        mock_get_summary.assert_not_called()

    @patch('builtins.print')
    @patch('common.audio_device_detection.get_device_summary')
    def test_no_config(self, mock_get_summary, mock_print):
        """Test logging when no config provided"""
        log_device_info()

        mock_print.assert_not_called()
        mock_get_summary.assert_not_called()

    @patch('builtins.print')
    @patch('common.audio_device_detection.get_device_summary')
    def test_no_devices_found(self, mock_get_summary, mock_print):
        """Test logging when no devices found"""
        mock_config = Mock()
        mock_config.debug = True

        mock_get_summary.return_value = {
            'pyaudio_available': True,
            'device_count': 0,
            'default_input': None,
            'default_output': None,
            'optimal_channels': 1
        }

        log_device_info(mock_config)

        # Should still print, showing "None" for devices
        self.assertGreater(mock_print.call_count, 5)


if __name__ == '__main__':
    unittest.main()
