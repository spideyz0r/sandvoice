import logging
import threading
import time
import unittest
from unittest.mock import Mock, patch

from common.barge_in import BargeInDetector, _BARGE_IN


class TestBargeInDetectorInit(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.wake_phrase = "hey jarvis"
        self.mock_config.wake_word_sensitivity = 0.5
        self.mock_config.openwakeword_model = "hey_jarvis"
        self.mock_config.rate = 16000

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self, **kwargs):
        defaults = dict(
            model_name="hey_jarvis",
            threshold=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )
        defaults.update(kwargs)
        return BargeInDetector(**defaults)

    def test_init_stores_params(self):
        lock = threading.Lock()
        mock_audio = Mock()
        d = self._make_detector(model_name="alexa", threshold=0.7, audio_lock=lock, audio=mock_audio)
        self.assertEqual(d._model_name, "alexa")
        self.assertEqual(d._sensitivity, 0.7)
        self.assertIs(d._audio_lock, lock)
        self.assertIs(d._audio, mock_audio)

    def test_init_creates_events_and_no_thread(self):
        d = self._make_detector()
        self.assertIsInstance(d._event, threading.Event)
        self.assertIsInstance(d._stop_flag, threading.Event)
        self.assertIsNone(d._thread)

    def test_is_triggered_false_initially(self):
        d = self._make_detector()
        self.assertFalse(d.is_triggered)

    def test_event_property_returns_event(self):
        d = self._make_detector()
        self.assertIs(d.event, d._event)


class TestBargeInDetectorStartStop(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.wake_phrase = "hey jarvis"
        self.mock_config.rate = 16000

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self, **kwargs):
        defaults = dict(
            model_name="hey_jarvis",
            threshold=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )
        defaults.update(kwargs)
        return BargeInDetector(**defaults)

    @patch('common.barge_in.OpenWakeWordDetector')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_start_creates_and_starts_thread(self, mock_pyaudio_class, mock_detector_class):
        mock_detector = Mock()
        mock_detector.sample_rate = 16000
        mock_detector.frame_length = 1280
        mock_detector.process.return_value = -1
        mock_detector_class.return_value = mock_detector

        mock_stream = Mock()
        stop_event = threading.Event()
        def blocking_read(n, exception_on_overflow=False):
            stop_event.wait(timeout=5)
            raise Exception("stopped")
        mock_stream.read = blocking_read

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = self._make_detector()
        d.start()
        try:
            self.assertIsNotNone(d._thread)
            self.assertTrue(d._thread.is_alive())
        finally:
            stop_event.set()
            d.stop(timeout=1.0)

    def test_start_noop_when_already_running(self):
        d = self._make_detector()
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        d._thread = mock_thread

        d.start()

        self.assertIs(d._thread, mock_thread)

    def test_stop_signals_thread_and_clears_state(self):
        d = self._make_detector()
        mock_thread = Mock()
        mock_thread.is_alive.side_effect = [True, False]
        d._thread = mock_thread
        d._event.set()

        d.stop(timeout=0.1)

        mock_thread.join.assert_called_once_with(timeout=0.1)
        self.assertIsNone(d._thread)
        self.assertFalse(d._stop_flag.is_set())
        self.assertFalse(d._event.is_set())

    def test_stop_nonblocking_when_timeout_zero(self):
        d = self._make_detector()
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        d._thread = mock_thread

        d.stop(timeout=0)

        mock_thread.join.assert_not_called()
        self.assertIsNotNone(d._thread)
        self.assertTrue(d._stop_flag.is_set())

    def test_stop_suppresses_runtime_error_on_join(self):
        d = self._make_detector()
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_thread.join.side_effect = RuntimeError("cannot join")
        d._thread = mock_thread
        d.stop(timeout=0.1)
        self.assertIsNotNone(d._thread)
        self.assertTrue(d._stop_flag.is_set())

    def test_stop_before_start_does_not_crash(self):
        d = self._make_detector()
        d.stop()

    def test_double_start_does_not_spawn_extra_threads(self):
        d = self._make_detector()
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        d._thread = mock_thread

        original_thread = d._thread
        d.start()
        d.start()

        self.assertIs(d._thread, original_thread)


class TestBargeInDetectorIsTriggered(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.rate = 16000

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            model_name="hey_jarvis",
            threshold=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )

    def test_is_triggered_false_when_event_not_set(self):
        d = self._make_detector()
        self.assertFalse(d.is_triggered)

    def test_is_triggered_true_when_event_set(self):
        d = self._make_detector()
        d._event.set()
        self.assertTrue(d.is_triggered)

    def test_clear_resets_triggered_flag(self):
        d = self._make_detector()
        d._event.set()
        self.assertTrue(d.is_triggered)
        d.clear()
        self.assertFalse(d.is_triggered)


class TestBargeInDetectorRunWithPolling(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.rate = 16000

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            model_name="hey_jarvis",
            threshold=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )

    def test_run_with_polling_returns_operation_result(self):
        d = self._make_detector()
        result = d.run_with_polling(lambda: "hello", "test_op")
        self.assertEqual(result, "hello")

    def test_run_with_polling_returns_none_result(self):
        d = self._make_detector()
        result = d.run_with_polling(lambda: None, "test_op")
        self.assertIsNone(result)

    def test_run_with_polling_propagates_exception(self):
        d = self._make_detector()
        def failing_op():
            raise ValueError("boom")
        with self.assertRaises(ValueError):
            d.run_with_polling(failing_op, "failing_op")

    def test_run_with_polling_returns_barge_in_when_already_triggered(self):
        d = self._make_detector()
        d._event.set()
        result = d.run_with_polling(lambda: "should not run", "test_op")
        self.assertIs(result, _BARGE_IN)

    def test_run_with_polling_returns_barge_in_on_interrupt_during_operation(self):
        """Barge-in triggered while a slow operation is running → returns _BARGE_IN."""
        d = self._make_detector()

        operation_started = threading.Event()
        operation_completed = threading.Event()

        def slow_operation():
            operation_started.set()
            time.sleep(0.5)
            operation_completed.set()
            return "result"

        result_holder = [None]

        def run_polling():
            result_holder[0] = d.run_with_polling(slow_operation, "test")

        polling_thread = threading.Thread(target=run_polling)
        polling_thread.start()

        operation_started.wait(timeout=2.0)
        d._event.set()

        polling_thread.join(timeout=1.0)
        self.assertFalse(polling_thread.is_alive(), "Polling should exit quickly on barge-in")
        self.assertIs(result_holder[0], _BARGE_IN)

        operation_completed.wait(timeout=1.0)

    def test_barge_in_sentinel_is_unique_object(self):
        from common.barge_in import _BARGE_IN as sentinel
        self.assertIsNot(sentinel, None)
        self.assertIsNot(sentinel, True)
        self.assertIsNot(sentinel, False)
        self.assertIsNot(sentinel, 0)
        self.assertIs(sentinel, _BARGE_IN)

    def test_lead_fn_fires_after_delay_when_operation_slow(self):
        """lead_fn is called once the delay elapses while operation is still running."""
        d = self._make_detector()
        lead_called = threading.Event()

        def lead():
            lead_called.set()

        def slow_op():
            time.sleep(0.5)
            return "done"

        result = d.run_with_polling(slow_op, "test", lead_delay_s=0.05, lead_fn=lead)
        self.assertEqual(result, "done")
        self.assertTrue(lead_called.wait(timeout=1.0), "lead_fn should have been called")

    def test_lead_fn_not_fired_when_operation_completes_quickly(self):
        """lead_fn is NOT called when the operation finishes before the delay."""
        d = self._make_detector()
        lead_called = threading.Event()

        def lead():
            lead_called.set()

        result = d.run_with_polling(lambda: "quick", "test", lead_delay_s=10.0, lead_fn=lead)
        self.assertEqual(result, "quick")
        self.assertFalse(lead_called.is_set(), "lead_fn should not fire for a fast operation")

    def test_lead_fn_fires_only_once(self):
        """lead_fn is called exactly once, even across many polling cycles."""
        d = self._make_detector()
        call_count = [0]
        lock = threading.Lock()

        def lead():
            with lock:
                call_count[0] += 1

        def slow_op():
            time.sleep(0.4)
            return "done"

        d.run_with_polling(slow_op, "test", lead_delay_s=0.05, lead_fn=lead)
        time.sleep(0.1)
        with lock:
            self.assertEqual(call_count[0], 1)

    def test_lead_fn_exception_does_not_abort_polling(self):
        """An exception raised by lead_fn does not propagate out of run_with_polling."""
        d = self._make_detector()

        def bad_lead():
            raise RuntimeError("lead exploded")

        def slow_op():
            time.sleep(0.2)
            return "result"

        result = d.run_with_polling(slow_op, "test", lead_delay_s=0.05, lead_fn=bad_lead)
        self.assertEqual(result, "result")


class TestBargeInDetectorDetectionLoop(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.rate = 16000

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            model_name="hey_jarvis",
            threshold=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )

    @patch('common.barge_in.OpenWakeWordDetector')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_sets_event_on_wake_word(self, mock_pyaudio_class, mock_detector_class):
        """When OpenWakeWord detects the wake word, _event is set."""
        mock_detector = Mock()
        mock_detector.sample_rate = 16000
        mock_detector.frame_length = 1280
        mock_detector.process.side_effect = [-1, -1, 0]  # wake word on 3rd call
        mock_detector_class.return_value = mock_detector

        def fake_read(n, exception_on_overflow=False):
            return b'\x00' * (n * 2)
        mock_stream = Mock()
        mock_stream.read = fake_read

        import struct
        with patch('common.barge_in.struct.unpack_from', return_value=[0] * 1280):
            mock_pa = Mock()
            mock_pa.open.return_value = mock_stream
            mock_pyaudio_class.return_value = mock_pa

            d = self._make_detector()
            d.start()
            detected = d._event.wait(timeout=2.0)
            d.stop(timeout=0.5)

        self.assertTrue(detected, "Expected wake word to be detected and event set")

    @patch('common.barge_in.OpenWakeWordDetector')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_stops_on_stop_flag(self, mock_pyaudio_class, mock_detector_class):
        """When stop_flag is set, the detection loop exits without triggering barge-in."""
        mock_detector = Mock()
        mock_detector.sample_rate = 16000
        mock_detector.frame_length = 1280
        mock_detector.process.return_value = -1
        mock_detector_class.return_value = mock_detector

        stop_read = threading.Event()
        def blocking_read(n, exception_on_overflow=False):
            stop_read.wait(timeout=5)
            raise Exception("stopped by test")

        mock_stream = Mock()
        mock_stream.read = blocking_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = self._make_detector()
        d.start()
        self.assertTrue(d._thread.is_alive())

        stop_read.set()
        d.stop(timeout=1.0)

        self.assertIsNone(d._thread)
        self.assertFalse(d.is_triggered)

    @patch('common.barge_in.OpenWakeWordDetector')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_handles_detector_init_error(self, mock_pyaudio_class, mock_detector_class):
        """If OpenWakeWordDetector cannot be created, the thread logs an error and exits cleanly."""
        mock_detector_class.side_effect = Exception("detector init failed")

        d = self._make_detector()
        d.start()
        if d._thread is not None:
            d._thread.join(timeout=2.0)

        self.assertFalse(d.is_triggered)

    @patch('common.barge_in.OpenWakeWordDetector')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_handles_audio_read_error(self, mock_pyaudio_class, mock_detector_class):
        """An error reading audio is caught and the loop exits cleanly."""
        mock_detector = Mock()
        mock_detector.sample_rate = 16000
        mock_detector.frame_length = 1280
        mock_detector_class.return_value = mock_detector

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("hw error")
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = self._make_detector()
        d.start()
        if d._thread is not None:
            d._thread.join(timeout=2.0)

        self.assertFalse(d.is_triggered)

    @patch('common.barge_in.OpenWakeWordDetector')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_audio_read_error_during_shutdown_logs_debug(
        self, mock_pyaudio_class, mock_detector_class
    ):
        """Audio read error during shutdown (stop_flag set) is logged at DEBUG, not WARNING."""
        mock_detector = Mock()
        mock_detector.sample_rate = 16000
        mock_detector.frame_length = 1280
        mock_detector_class.return_value = mock_detector

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("stream closed")
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = self._make_detector()
        d._stop_flag.set()
        d._thread = threading.Thread(target=d._detection_loop, daemon=True)
        d._thread.start()
        d._thread.join(timeout=2.0)

        self.assertFalse(d.is_triggered)


class TestBargeInCleanupPyAudio(unittest.TestCase):
    """Tests for _cleanup_pyaudio exception-handling paths."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.rate = 16000

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            model_name="hey_jarvis",
            threshold=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )

    def test_cleanup_pyaudio_suppresses_stop_stream_exception(self):
        d = self._make_detector()
        mock_stream = Mock()
        mock_stream.stop_stream.side_effect = Exception("hw error")
        mock_pa = Mock()
        d._cleanup_pyaudio(mock_stream, mock_pa)
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    def test_cleanup_pyaudio_suppresses_close_exception(self):
        d = self._make_detector()
        mock_stream = Mock()
        mock_stream.close.side_effect = Exception("close error")
        mock_pa = Mock()
        d._cleanup_pyaudio(mock_stream, mock_pa)
        mock_pa.terminate.assert_called_once()

    def test_cleanup_pyaudio_suppresses_terminate_exception(self):
        d = self._make_detector()
        mock_stream = Mock()
        mock_pa = Mock()
        mock_pa.terminate.side_effect = Exception("terminate error")
        d._cleanup_pyaudio(mock_stream, mock_pa)

    def test_cleanup_pyaudio_handles_both_none(self):
        d = self._make_detector()
        d._cleanup_pyaudio(None, None)


class TestBargeInSentinel(unittest.TestCase):
    """Tests for the _BARGE_IN sentinel object."""

    def test_barge_in_sentinel_is_unique(self):
        from common.barge_in import _BARGE_IN as s1
        from common.barge_in import _BARGE_IN as s2
        self.assertIs(s1, s2)

    def test_barge_in_sentinel_is_not_none(self):
        self.assertIsNotNone(_BARGE_IN)

    def test_barge_in_sentinel_is_not_false(self):
        self.assertIsNot(_BARGE_IN, False)

    def test_barge_in_sentinel_identity_check(self):
        self.assertIs(_BARGE_IN, _BARGE_IN)
        self.assertIsNot(_BARGE_IN, object())


if __name__ == '__main__':
    unittest.main()
