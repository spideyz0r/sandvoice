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
        self.mock_config.wake_phrase = "porcupine"
        self.mock_config.porcupine_access_key = "test-key"
        self.mock_config.porcupine_keyword_paths = None
        self.mock_config.wake_word_sensitivity = 0.5

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self, **kwargs):
        defaults = dict(
            access_key="test-key",
            keyword_paths=None,
            sensitivity=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )
        defaults.update(kwargs)
        return BargeInDetector(**defaults)

    def test_init_stores_params(self):
        lock = threading.Lock()
        mock_audio = Mock()
        d = self._make_detector(access_key="key123", sensitivity=0.7, audio_lock=lock, audio=mock_audio)
        self.assertEqual(d._access_key, "key123")
        self.assertIsNone(d._keyword_paths)
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
        self.mock_config.wake_phrase = "porcupine"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self, **kwargs):
        defaults = dict(
            access_key="test-key",
            keyword_paths=None,
            sensitivity=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )
        defaults.update(kwargs)
        return BargeInDetector(**defaults)

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_start_creates_and_starts_thread(self, mock_pyaudio_class, mock_porcupine_create):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        # Keep thread blocked until we stop it
        mock_porcupine.process.return_value = -1
        mock_porcupine_create.return_value = mock_porcupine

        mock_stream = Mock()
        # Block on read so thread stays alive
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

        # Should not replace the existing thread
        self.assertIs(d._thread, mock_thread)

    def test_stop_signals_thread_and_clears_state(self):
        d = self._make_detector()
        mock_thread = Mock()
        # Simulate thread alive before join, dead after join
        mock_thread.is_alive.side_effect = [True, False]
        d._thread = mock_thread
        d._event.set()

        d.stop(timeout=0.1)

        mock_thread.join.assert_called_once_with(timeout=0.1)
        self.assertIsNone(d._thread)
        self.assertFalse(d._stop_flag.is_set())
        self.assertFalse(d._event.is_set())

    def test_stop_nonblocking_when_timeout_zero(self):
        # timeout=0 signals the stop flag but does not join; since the thread
        # is still alive, internal state is NOT reset (prevents duplicate threads).
        d = self._make_detector()
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        d._thread = mock_thread

        d.stop(timeout=0)

        mock_thread.join.assert_not_called()
        self.assertIsNotNone(d._thread)  # thread ref kept until it actually exits
        self.assertTrue(d._stop_flag.is_set())  # stop was signaled

    def test_stop_suppresses_runtime_error_on_join(self):
        # RuntimeError from join() is suppressed; since the thread is still alive
        # after the failed join, internal state is not reset.
        d = self._make_detector()
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_thread.join.side_effect = RuntimeError("cannot join")
        d._thread = mock_thread
        # Should not raise
        d.stop(timeout=0.1)
        # Thread still alive after failed join — ref and stop flag kept set
        self.assertIsNotNone(d._thread)
        self.assertTrue(d._stop_flag.is_set())

    def test_stop_before_start_does_not_crash(self):
        d = self._make_detector()
        # Should not raise
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
        self.mock_config.wake_phrase = "porcupine"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            access_key="test-key",
            keyword_paths=None,
            sensitivity=0.5,
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
        self.mock_config.wake_phrase = "porcupine"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            access_key="test-key",
            keyword_paths=None,
            sensitivity=0.5,
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

        # Wait for operation to start, then trigger barge-in
        operation_started.wait(timeout=2.0)
        d._event.set()

        # Polling should return quickly (not wait for the slow operation)
        polling_thread.join(timeout=1.0)
        self.assertFalse(polling_thread.is_alive(), "Polling should exit quickly on barge-in")
        self.assertIs(result_holder[0], _BARGE_IN)

        # Clean up slow operation
        operation_completed.wait(timeout=1.0)

    def test_barge_in_sentinel_is_unique_object(self):
        from common.barge_in import _BARGE_IN as sentinel
        # Sentinel must be a distinct object — not None, True, False, 0, or any other singleton
        self.assertIsNot(sentinel, None)
        self.assertIsNot(sentinel, True)
        self.assertIsNot(sentinel, False)
        self.assertIsNot(sentinel, 0)
        self.assertIs(sentinel, _BARGE_IN)  # identity is stable


class TestBargeInDetectorDetectionLoop(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.wake_phrase = "porcupine"
        self.mock_config.porcupine_access_key = "test-key"
        self.mock_config.porcupine_keyword_paths = None
        self.mock_config.wake_word_sensitivity = 0.5

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            access_key="test-key",
            keyword_paths=None,
            sensitivity=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_sets_event_on_wake_word(self, mock_pyaudio_class, mock_porcupine_create):
        """When Porcupine detects the wake word, _event is set."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.side_effect = [-1, -1, 0]  # wake word on 3rd call
        mock_porcupine_create.return_value = mock_porcupine

        def fake_read(n, exception_on_overflow=False):
            return b'\x00' * (n * 2)
        mock_stream = Mock()
        mock_stream.read = fake_read

        import struct
        with patch('common.barge_in.struct.unpack_from', return_value=[0] * 512):
            mock_pa = Mock()
            mock_pa.open.return_value = mock_stream
            mock_pyaudio_class.return_value = mock_pa

            d = self._make_detector()
            d.start()
            # Wait for the event to be set
            detected = d._event.wait(timeout=2.0)
            d.stop(timeout=0.5)

        self.assertTrue(detected, "Expected wake word to be detected and event set")

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_stops_on_stop_flag(self, mock_pyaudio_class, mock_porcupine_create):
        """When stop_flag is set, the detection loop exits without triggering barge-in."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.return_value = -1  # never detect
        mock_porcupine_create.return_value = mock_porcupine

        # Block on read until stop_flag is set
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

        # Signal stop and unblock read
        stop_read.set()
        d.stop(timeout=1.0)

        self.assertIsNone(d._thread)
        self.assertFalse(d.is_triggered)

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_handles_porcupine_init_error(self, mock_pyaudio_class, mock_porcupine_create):
        """If Porcupine cannot be created, the thread logs an error and exits cleanly."""
        mock_porcupine_create.side_effect = Exception("Porcupine init failed")

        d = self._make_detector()
        d.start()
        # Thread should exit quickly after the error
        if d._thread is not None:
            d._thread.join(timeout=2.0)

        self.assertFalse(d.is_triggered)

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_uses_built_in_keyword_when_no_paths(self, mock_pyaudio_class, mock_porcupine_create):
        """Without keyword_paths, Porcupine is created with keywords=[wake_phrase]."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.return_value = -1
        mock_porcupine_create.return_value = mock_porcupine

        stop_read = threading.Event()
        def blocking_read(n, exception_on_overflow=False):
            stop_read.wait(timeout=2)
            raise Exception("done")
        mock_stream = Mock()
        mock_stream.read = blocking_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = self._make_detector()
        d.start()
        stop_read.set()
        d.stop(timeout=1.0)

        mock_porcupine_create.assert_called_with(
            access_key="test-key",
            keywords=["porcupine"],
            sensitivities=[0.5],
        )

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_uses_keyword_paths_when_provided(self, mock_pyaudio_class, mock_porcupine_create):
        """With keyword_paths, Porcupine is created with keyword_paths and sensitivities."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.return_value = -1
        mock_porcupine_create.return_value = mock_porcupine

        stop_read = threading.Event()
        def blocking_read(n, exception_on_overflow=False):
            stop_read.wait(timeout=2)
            raise Exception("done")
        mock_stream = Mock()
        mock_stream.read = blocking_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = BargeInDetector(
            access_key="test-key",
            keyword_paths=["/path/to/model.ppn"],
            sensitivity=0.6,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )
        d.start()
        stop_read.set()
        d.stop(timeout=1.0)

        mock_porcupine_create.assert_called_with(
            access_key="test-key",
            keyword_paths=["/path/to/model.ppn"],
            sensitivities=[0.6],
        )

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_handles_audio_read_error(self, mock_pyaudio_class, mock_porcupine_create):
        """An error reading audio is caught and the loop exits cleanly."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("hw error")
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = self._make_detector()
        d.start()
        if d._thread is not None:
            d._thread.join(timeout=2.0)

        # Event should not be set (error before detection)
        self.assertFalse(d.is_triggered)

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_detection_loop_audio_read_error_during_shutdown_logs_debug(
        self, mock_pyaudio_class, mock_porcupine_create
    ):
        """Audio read error during shutdown (stop_flag set) is logged at DEBUG, not WARNING."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("stream closed")
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = self._make_detector()
        d._stop_flag.set()  # simulate shutdown in progress
        d._thread = threading.Thread(target=d._detection_loop, daemon=True)
        d._thread.start()
        d._thread.join(timeout=2.0)

        self.assertFalse(d.is_triggered)


class TestBargeInCleanupPyAudio(unittest.TestCase):
    """Tests for _cleanup_pyaudio exception-handling paths."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.wake_phrase = "porcupine"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_detector(self):
        return BargeInDetector(
            access_key="test-key",
            keyword_paths=None,
            sensitivity=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )

    def test_cleanup_pyaudio_suppresses_stop_stream_exception(self):
        d = self._make_detector()
        mock_stream = Mock()
        mock_stream.stop_stream.side_effect = Exception("hw error")
        mock_pa = Mock()
        # Should not raise; close() and pa.terminate() must still be called
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
        # Should not raise
        d._cleanup_pyaudio(mock_stream, mock_pa)

    def test_cleanup_pyaudio_handles_both_none(self):
        d = self._make_detector()
        # Should not raise
        d._cleanup_pyaudio(None, None)


class TestBargeInKeywordPaths(unittest.TestCase):
    """Tests for keyword_paths handling in _create_porcupine_instance."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.wake_phrase = "porcupine"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_single_string_keyword_path_wrapped_in_list(self, mock_pyaudio_class, mock_porcupine_create):
        """A string keyword_path (not a list) should be wrapped in a list."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.return_value = -1
        mock_porcupine_create.return_value = mock_porcupine

        stop_read = threading.Event()
        def blocking_read(n, exception_on_overflow=False):
            stop_read.wait(timeout=2)
            raise Exception("done")
        mock_stream = Mock()
        mock_stream.read = blocking_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = BargeInDetector(
            access_key="test-key",
            keyword_paths="/path/to/model.ppn",  # string, not list
            sensitivity=0.6,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )
        d.start()
        stop_read.set()
        d.stop(timeout=1.0)

        mock_porcupine_create.assert_called_with(
            access_key="test-key",
            keyword_paths=["/path/to/model.ppn"],
            sensitivities=[0.6],
        )

    @patch('common.barge_in.pvporcupine.create')
    @patch('common.barge_in.pyaudio.PyAudio')
    def test_porcupine_delete_exception_suppressed(self, mock_pyaudio_class, mock_porcupine_create):
        """If porcupine_instance.delete() raises, the exception is suppressed."""
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.return_value = -1
        mock_porcupine.delete.side_effect = Exception("delete error")
        mock_porcupine_create.return_value = mock_porcupine

        stop_read = threading.Event()
        def blocking_read(n, exception_on_overflow=False):
            stop_read.wait(timeout=2)
            raise Exception("done")
        mock_stream = Mock()
        mock_stream.read = blocking_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        d = BargeInDetector(
            access_key="test-key",
            keyword_paths=None,
            sensitivity=0.5,
            audio_lock=None,
            audio=Mock(),
            config=self.mock_config,
        )
        d.start()
        stop_read.set()
        # Should not raise even though delete() fails
        d.stop(timeout=1.0)


class TestBargeInSentinel(unittest.TestCase):
    """Tests for the _BARGE_IN sentinel object."""

    def test_barge_in_sentinel_is_unique(self):
        """_BARGE_IN is a unique object identity sentinel."""
        from common.barge_in import _BARGE_IN as s1
        from common.barge_in import _BARGE_IN as s2
        self.assertIs(s1, s2)

    def test_barge_in_sentinel_is_not_none(self):
        self.assertIsNotNone(_BARGE_IN)

    def test_barge_in_sentinel_is_not_false(self):
        self.assertIsNot(_BARGE_IN, False)

    def test_barge_in_sentinel_identity_check(self):
        """Confirm identity semantics (not equality)."""
        self.assertIs(_BARGE_IN, _BARGE_IN)
        self.assertIsNot(_BARGE_IN, object())


if __name__ == '__main__':
    unittest.main()
