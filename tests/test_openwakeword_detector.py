import logging
import unittest
from math import gcd
from unittest.mock import MagicMock, Mock, patch

import numpy as np


class TestOpenWakeWordDetectorInit(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_mock_model(self):
        mock_model = Mock()
        mock_model.predict.return_value = {"hey_jarvis": 0.0}
        return mock_model

    @patch('common.openwakeword_detector.OpenWakeWordDetector.__init__', return_value=None)
    def test_import_succeeds(self, _):
        from common.openwakeword_detector import OpenWakeWordDetector
        self.assertTrue(True)

    def test_sample_rate_constant(self):
        from common.openwakeword_detector import _SAMPLE_RATE
        self.assertEqual(_SAMPLE_RATE, 16000)

    def test_frame_length_constant(self):
        from common.openwakeword_detector import _FRAME_LENGTH
        self.assertEqual(_FRAME_LENGTH, 1280)

    @patch('openwakeword.model.Model')
    def test_init_stores_model_name_and_threshold(self, mock_model_class):
        mock_model = self._make_mock_model()
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        d = OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5)

        self.assertEqual(d._model_name, "hey_jarvis")
        self.assertEqual(d._threshold, 0.5)

    @patch('openwakeword.model.Model')
    def test_init_default_device_rate_is_16000(self, mock_model_class):
        mock_model = self._make_mock_model()
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        d = OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5)

        from common.openwakeword_detector import _SAMPLE_RATE
        self.assertEqual(d._device_rate, _SAMPLE_RATE)

    @patch('openwakeword.model.Model')
    def test_init_custom_device_rate_stored(self, mock_model_class):
        mock_model = Mock()
        mock_model.predict.return_value = {"hey_jarvis": 0.0}
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        d = OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5, device_sample_rate=48000)

        self.assertEqual(d._device_rate, 48000)

    @patch('openwakeword.model.Model')
    def test_init_computes_resample_ratio_when_rate_differs(self, mock_model_class):
        mock_model = Mock()
        mock_model.predict.return_value = {"hey_jarvis": 0.0}
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        d = OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5, device_sample_rate=48000)

        _g = gcd(48000, 16000)
        self.assertEqual(d._resample_up, 16000 // _g)
        self.assertEqual(d._resample_down, 48000 // _g)

    @patch('openwakeword.model.Model')
    def test_init_no_resample_when_rate_matches(self, mock_model_class):
        mock_model = Mock()
        mock_model.predict.return_value = {"hey_jarvis": 0.0}
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        d = OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5, device_sample_rate=16000)

        self.assertIsNone(d._resample_up)
        self.assertIsNone(d._resample_down)

    @patch('openwakeword.model.Model')
    def test_init_warms_up_model(self, mock_model_class):
        mock_model = Mock()
        mock_model.predict.return_value = {"hey_jarvis": 0.0}
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5)

        # predict should be called once with zeros during warmup
        mock_model.predict.assert_called_once()
        warmup_arg = mock_model.predict.call_args[0][0]
        self.assertEqual(warmup_arg.dtype, np.int16)
        from common.openwakeword_detector import _FRAME_LENGTH
        self.assertEqual(len(warmup_arg), _FRAME_LENGTH)
        self.assertTrue(np.all(warmup_arg == 0))

    @patch('openwakeword.model.Model')
    def test_init_onnx_path_uses_wakeword_model_paths(self, mock_model_class):
        mock_model = Mock()
        mock_model.predict.return_value = {"my_model": 0.0}
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        d = OpenWakeWordDetector(model_name="/path/to/my_model.onnx", threshold=0.5)

        mock_model_class.assert_called_once_with(
            wakeword_model_paths=["/path/to/my_model.onnx"],
            inference_framework="onnx",
        )
        self.assertEqual(d._prediction_key, "my_model")

    @patch('openwakeword.model.Model')
    def test_init_named_model_uses_wakeword_models(self, mock_model_class):
        mock_model = Mock()
        mock_model.predict.return_value = {"hey_jarvis": 0.0}
        mock_model_class.return_value = mock_model

        from common.openwakeword_detector import OpenWakeWordDetector
        d = OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5)

        mock_model_class.assert_called_once_with(
            wakeword_models=["hey_jarvis"],
            inference_framework="onnx",
        )
        self.assertEqual(d._prediction_key, "hey_jarvis")


class TestOpenWakeWordDetectorProperties(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self, device_sample_rate=16000):
        with patch('openwakeword.model.Model') as mock_model_class:
            mock_model = Mock()
            mock_model.predict.return_value = {"hey_jarvis": 0.0}
            mock_model_class.return_value = mock_model
            from common.openwakeword_detector import OpenWakeWordDetector
            return OpenWakeWordDetector(
                model_name="hey_jarvis",
                threshold=0.5,
                device_sample_rate=device_sample_rate,
            )

    def test_sample_rate_property(self):
        d = self._make_detector()
        from common.openwakeword_detector import _SAMPLE_RATE
        self.assertEqual(d.sample_rate, _SAMPLE_RATE)

    def test_device_sample_rate_property(self):
        d = self._make_detector(device_sample_rate=48000)
        self.assertEqual(d.device_sample_rate, 48000)

    def test_frame_length_no_resample(self):
        d = self._make_detector(device_sample_rate=16000)
        from common.openwakeword_detector import _FRAME_LENGTH
        self.assertEqual(d.frame_length, _FRAME_LENGTH)

    def test_frame_length_with_resample(self):
        d = self._make_detector(device_sample_rate=48000)
        from common.openwakeword_detector import _FRAME_LENGTH, _SAMPLE_RATE
        expected = int(_FRAME_LENGTH * 48000 / _SAMPLE_RATE)
        self.assertEqual(d.frame_length, expected)


class TestOpenWakeWordDetectorProcess(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self, device_sample_rate=16000, threshold=0.5):
        with patch('openwakeword.model.Model') as mock_model_class:
            mock_model = Mock()
            mock_model.predict.return_value = {"hey_jarvis": 0.0}
            mock_model_class.return_value = mock_model
            from common.openwakeword_detector import OpenWakeWordDetector
            return OpenWakeWordDetector(
                model_name="hey_jarvis",
                threshold=threshold,
                device_sample_rate=device_sample_rate,
            )

    def test_process_returns_minus_one_below_threshold(self):
        d = self._make_detector()
        d._model.predict.return_value = {"hey_jarvis": 0.1}
        from common.openwakeword_detector import _FRAME_LENGTH
        pcm = [0] * _FRAME_LENGTH
        result = d.process(pcm)
        self.assertEqual(result, -1)

    def test_process_returns_zero_at_threshold(self):
        d = self._make_detector(threshold=0.5)
        d._model.predict.return_value = {"hey_jarvis": 0.5}
        from common.openwakeword_detector import _FRAME_LENGTH
        pcm = [0] * _FRAME_LENGTH
        result = d.process(pcm)
        self.assertEqual(result, 0)

    def test_process_returns_zero_above_threshold(self):
        d = self._make_detector(threshold=0.5)
        d._model.predict.return_value = {"hey_jarvis": 0.9}
        from common.openwakeword_detector import _FRAME_LENGTH
        pcm = [0] * _FRAME_LENGTH
        result = d.process(pcm)
        self.assertEqual(result, 0)

    def test_process_no_resample_passes_int16_array(self):
        d = self._make_detector(device_sample_rate=16000)
        d._model.predict.return_value = {"hey_jarvis": 0.0}
        from common.openwakeword_detector import _FRAME_LENGTH
        pcm = [100] * _FRAME_LENGTH
        d.process(pcm)
        call_arg = d._model.predict.call_args[0][0]
        self.assertEqual(call_arg.dtype, np.int16)
        self.assertEqual(len(call_arg), _FRAME_LENGTH)

    @patch('scipy.signal.resample_poly')
    def test_process_resamples_when_device_rate_differs(self, mock_resample):
        mock_resample.return_value = np.zeros(1280, dtype=np.float64)
        d = self._make_detector(device_sample_rate=48000)
        d._model.predict.return_value = {"hey_jarvis": 0.0}

        # frame_length at 48kHz = 3840
        pcm = [0] * d.frame_length
        d.process(pcm)

        mock_resample.assert_called_once()
        args = mock_resample.call_args[0]
        self.assertEqual(args[1], d._resample_up)
        self.assertEqual(args[2], d._resample_down)

    def test_process_missing_key_returns_minus_one(self):
        d = self._make_detector()
        d._model.predict.return_value = {}  # key not present
        from common.openwakeword_detector import _FRAME_LENGTH
        pcm = [0] * _FRAME_LENGTH
        result = d.process(pcm)
        self.assertEqual(result, -1)


class TestOpenWakeWordDetectorResetDelete(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        with patch('openwakeword.model.Model') as mock_model_class:
            mock_model = Mock()
            mock_model.predict.return_value = {"hey_jarvis": 0.0}
            mock_model_class.return_value = mock_model
            from common.openwakeword_detector import OpenWakeWordDetector
            return OpenWakeWordDetector(model_name="hey_jarvis", threshold=0.5)

    def test_reset_calls_model_reset(self):
        d = self._make_detector()
        d._model.reset = Mock()
        d.reset()
        d._model.reset.assert_called_once()

    def test_reset_suppresses_exception(self):
        d = self._make_detector()
        d._model.reset = Mock(side_effect=Exception("reset failed"))
        # Should not raise
        d.reset()

    def test_delete_is_noop(self):
        d = self._make_detector()
        # Should not raise and return None
        result = d.delete()
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
