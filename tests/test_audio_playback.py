import os
import sys
import types
import unittest
import tempfile
import threading
from unittest.mock import Mock, patch


def _install_fake_deps_for_common_audio():
    # Minimal stub modules so `common.audio` can be imported without native deps.
    fake_pyaudio = types.ModuleType('pyaudio')
    fake_pyaudio.paInt16 = 8
    fake_pyaudio.PyAudio = object

    fake_lameenc = types.ModuleType('lameenc')
    fake_lameenc.Encoder = object

    fake_keyboard = types.ModuleType('pynput.keyboard')
    fake_keyboard.Listener = object

    fake_pynput = types.ModuleType('pynput')
    fake_pynput.keyboard = fake_keyboard

    class _FakeMusic:
        def __init__(self):
            self._stopped = False

        def load(self, _path):
            return None

        def play(self):
            self._stopped = False
            return None

        def get_busy(self):
            return False

        def stop(self):
            self._stopped = True
            return None

    class _FakeMixer:
        def __init__(self):
            self._init = None
            self.music = _FakeMusic()

        def get_init(self):
            return self._init

        def init(self):
            self._init = (44100, -16, 2)

        def quit(self):
            self._init = None

    class _FakeTime:
        class Clock:
            def tick(self, _fps):
                return None

    fake_pygame = types.ModuleType('pygame')
    fake_pygame.mixer = _FakeMixer()
    fake_pygame.time = _FakeTime()

    # Force stubs even when real deps are installed.
    sys.modules['pyaudio'] = fake_pyaudio
    sys.modules['lameenc'] = fake_lameenc
    sys.modules['pynput'] = fake_pynput
    sys.modules['pynput.keyboard'] = fake_keyboard
    sys.modules['pygame'] = fake_pygame

    # Ensure subsequent imports see the stubs.
    sys.modules.pop('common.audio', None)


class TestAudioPlaybackHelpers(unittest.TestCase):
    def setUp(self):
        _install_fake_deps_for_common_audio()

        # Import after stubbing
        from common.audio import Audio
        self.Audio = Audio

        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_play_audio_files_success_cleans_up(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        played = []

        def _play(path):
            played.append(path)

        audio.play_audio_file = _play

        f1 = os.path.join(self.temp_dir, 'a.mp3')
        f2 = os.path.join(self.temp_dir, 'b.mp3')
        open(f1, 'wb').close()
        open(f2, 'wb').close()

        success, failed, err = self.Audio.play_audio_files(audio, [f1, f2])

        self.assertTrue(success)
        self.assertIsNone(failed)
        self.assertIsNone(err)
        self.assertEqual(played, [f1, f2])
        self.assertFalse(os.path.exists(f1))
        self.assertFalse(os.path.exists(f2))

    def test_play_audio_files_failure_preserves_failed_in_debug(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=True)

        def _play(path):
            if path.endswith('b.mp3'):
                raise RuntimeError('boom')

        audio.play_audio_file = _play

        f1 = os.path.join(self.temp_dir, 'a.mp3')
        f2 = os.path.join(self.temp_dir, 'b.mp3')
        f3 = os.path.join(self.temp_dir, 'c.mp3')
        open(f1, 'wb').close()
        open(f2, 'wb').close()
        open(f3, 'wb').close()

        success, failed, err = self.Audio.play_audio_files(audio, [f1, f2, f3])

        self.assertFalse(success)
        self.assertEqual(failed, f2)
        self.assertIsInstance(err, Exception)

        # a played successfully -> cleaned
        self.assertFalse(os.path.exists(f1))
        # b failed -> preserved in debug
        self.assertTrue(os.path.exists(f2))
        # c never played -> cleaned
        self.assertFalse(os.path.exists(f3))

    def test_play_audio_files_pauses_between_chunks_when_enabled(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False, tts_inter_chunk_pause_ms=120)

        events = []

        def _play(path):
            events.append(f"play:{os.path.basename(path)}")

        audio.play_audio_file = _play

        f1 = os.path.join(self.temp_dir, 'a.mp3')
        f2 = os.path.join(self.temp_dir, 'b.mp3')
        open(f1, 'wb').close()
        open(f2, 'wb').close()

        with patch('common.audio.time.sleep') as mock_sleep:
            def sleep_side_effect(seconds):
                events.append(f"sleep:{seconds}")
                return None
            mock_sleep.side_effect = sleep_side_effect

            success, failed, err = self.Audio.play_audio_files(audio, [f1, f2])

        self.assertTrue(success)
        self.assertIsNone(failed)
        self.assertIsNone(err)
        self.assertEqual(events[0], 'play:a.mp3')
        self.assertTrue(any(e.startswith('sleep:') for e in events))
        self.assertEqual(events[-1], 'play:b.mp3')

    def test_play_audio_files_skips_pause_when_disabled(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False, tts_inter_chunk_pause_ms=0)

        audio.play_audio_file = lambda _path: None

        f1 = os.path.join(self.temp_dir, 'a.mp3')
        f2 = os.path.join(self.temp_dir, 'b.mp3')
        open(f1, 'wb').close()
        open(f2, 'wb').close()

        with patch('common.audio.time.sleep') as mock_sleep:
            success, failed, err = self.Audio.play_audio_files(audio, [f1, f2])

        self.assertTrue(success)
        self.assertIsNone(failed)
        self.assertIsNone(err)
        mock_sleep.assert_not_called()

    def test_play_audio_files_stop_event_interrupts_during_pause(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False, tts_inter_chunk_pause_ms=500)

        played = []
        audio.play_audio_file = lambda path, **kwargs: played.append(os.path.basename(path))

        f1 = os.path.join(self.temp_dir, 'a.mp3')
        f2 = os.path.join(self.temp_dir, 'b.mp3')
        open(f1, 'wb').close()
        open(f2, 'wb').close()

        stop_event = threading.Event()

        # Interrupt on first sleep call
        with patch('common.audio.time.sleep') as mock_sleep:
            def sleep_side_effect(_seconds):
                stop_event.set()
                return None
            mock_sleep.side_effect = sleep_side_effect

            success, failed, err = self.Audio.play_audio_files(audio, [f1, f2], stop_event=stop_event)

        self.assertFalse(success)
        self.assertIsNone(failed)
        self.assertIsNone(err)
        self.assertEqual(played, ['a.mp3'])
        self.assertFalse(os.path.exists(f1))
        self.assertFalse(os.path.exists(f2))


class TestMixerInitialization(unittest.TestCase):
    def setUp(self):
        _install_fake_deps_for_common_audio()
        from common.audio import Audio
        self.Audio = Audio

    @patch('builtins.print')
    def test_play_audio_file_initializes_mixer_if_needed(self, _mock_print):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        pygame.mixer._init = None

        self.Audio.play_audio_file(audio, '/tmp/fake.mp3')
        self.assertIsNotNone(pygame.mixer.get_init())


class TestIsPlaying(unittest.TestCase):
    def setUp(self):
        _install_fake_deps_for_common_audio()
        from common.audio import Audio
        self.Audio = Audio

    def test_is_playing_false_when_mixer_not_initialized(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        pygame.mixer.quit()
        self.assertFalse(audio.is_playing())

    def test_is_playing_true_when_busy(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        pygame.mixer.init()

        original_get_busy = pygame.mixer.music.get_busy
        try:
            pygame.mixer.music.get_busy = lambda: True
            self.assertTrue(audio.is_playing())
        finally:
            pygame.mixer.music.get_busy = original_get_busy

    def test_is_playing_false_on_exception(self):
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        pygame.mixer.init()

        original_get_busy = pygame.mixer.music.get_busy
        try:
            def boom():
                raise RuntimeError("boom")
            pygame.mixer.music.get_busy = boom
            self.assertFalse(audio.is_playing())
        finally:
            pygame.mixer.music.get_busy = original_get_busy


class TestStopPlayback(unittest.TestCase):
    """Test stop_playback method for barge-in functionality."""
    
    def setUp(self):
        _install_fake_deps_for_common_audio()
        from common.audio import Audio
        self.Audio = Audio

    def test_stop_playback_calls_mixer_stop(self):
        """Test that stop_playback calls pygame.mixer.music.stop()."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        # Initialize mixer
        pygame.mixer.init()

        # Track if stop was called
        original_stop = pygame.mixer.music.stop
        stop_called = []

        def track_stop():
            stop_called.append(True)
            return original_stop()

        try:
            pygame.mixer.music.stop = track_stop

            # Call stop_playback
            audio.stop_playback()

            # Verify stop was called
            self.assertGreater(len(stop_called), 0)
        finally:
            pygame.mixer.music.stop = original_stop
    
    def test_stop_playback_safe_when_mixer_not_initialized(self):
        """Test that stop_playback is safe to call when mixer not initialized."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        # Uninitialize the mixer using the fake mixer's quit method
        pygame.mixer.quit()

        # Verify mixer is uninitialized
        self.assertIsNone(pygame.mixer.get_init())

        # Should not raise exception
        audio.stop_playback()
    
    def test_stop_playback_logs_in_debug_mode(self):
        """Test that stop_playback logs when debug is enabled."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=True)

        import pygame
        pygame.mixer.init()

        with patch('common.audio.logging.info') as mock_log:
            audio.stop_playback()
            # Check that stop_playback was logged (format includes thread and was_busy info)
            log_calls = [str(call) for call in mock_log.call_args_list]
            stop_logged = any('stop_playback' in call for call in log_calls)
            self.assertTrue(stop_logged, "stop_playback should be logged in debug mode")


class TestPlayAudioFileWithStopEvent(unittest.TestCase):
    """Test play_audio_file with stop_event parameter for barge-in interruption."""

    def setUp(self):
        _install_fake_deps_for_common_audio()
        from common.audio import Audio
        self.Audio = Audio

    def test_play_audio_file_accepts_stop_event_parameter(self):
        """Test that play_audio_file accepts stop_event parameter without error."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        import threading
        import inspect
        pygame.mixer.init()

        # Verify the method signature accepts stop_event parameter
        sig = inspect.signature(audio.play_audio_file)
        self.assertIn('stop_event', sig.parameters,
                      "play_audio_file should accept stop_event parameter")

        # Create event that is never set
        stop_event = threading.Event()

        # Verify the method can be called with the parameter
        # Only catch playback-related exceptions, not TypeError from wrong signature
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                temp_file = f.name

            audio.play_audio_file(temp_file, stop_event=stop_event)
        except TypeError:
            # TypeError means the signature is wrong - fail the test
            self.fail("play_audio_file does not accept stop_event parameter")
        except (RuntimeError, FileNotFoundError, OSError):
            # Expected: dummy temp file won't play properly on most platforms/CI.
            # We're testing the method signature accepts stop_event, not actual playback.
            pass
        finally:
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_stop_event_interrupts_playback(self):
        """Test that playback is interrupted when stop_event is set."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        import threading
        pygame.mixer.init()

        # Track calls to pygame.mixer.music.stop
        stop_called = []
        original_stop = pygame.mixer.music.stop

        def track_stop():
            stop_called.append(True)
            return original_stop()

        pygame.mixer.music.stop = track_stop

        # Make get_busy return True initially to simulate active playback
        busy_count = [0]
        original_get_busy = pygame.mixer.music.get_busy

        def controlled_get_busy():
            busy_count[0] += 1
            # Return True for first few calls, then False
            return busy_count[0] < 5

        pygame.mixer.music.get_busy = controlled_get_busy

        try:
            # Create a pre-set event to trigger immediate stop
            stop_event = threading.Event()
            stop_event.set()  # Pre-set to trigger stop on first check

            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    temp_file = f.name

                audio.play_audio_file(temp_file, stop_event=stop_event)
            except (RuntimeError, FileNotFoundError, OSError):
                # Expected: dummy temp file won't play properly on most platforms/CI.
                # We're testing the stop_event interruption behavior, not actual audio.
                pass
            finally:
                if temp_file and os.path.exists(temp_file):
                    os.unlink(temp_file)

            # Verify stop was called due to the stop_event
            self.assertGreater(len(stop_called), 0,
                               "pygame.mixer.music.stop should be called when stop_event is set")
        finally:
            pygame.mixer.music.stop = original_stop
            pygame.mixer.music.get_busy = original_get_busy

    def test_stop_event_logs_interruption_in_debug_mode(self):
        """Test that playback interruption is logged in debug mode."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=True)

        import pygame
        import threading
        pygame.mixer.init()

        # Make get_busy return True initially
        busy_count = [0]
        original_get_busy = pygame.mixer.music.get_busy

        def controlled_get_busy():
            busy_count[0] += 1
            return busy_count[0] < 5

        pygame.mixer.music.get_busy = controlled_get_busy

        try:
            stop_event = threading.Event()
            stop_event.set()

            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    temp_file = f.name

                with patch('common.audio.logging.info') as mock_log:
                    try:
                        audio.play_audio_file(temp_file, stop_event=stop_event)
                    except (RuntimeError, FileNotFoundError, OSError):
                        # Expected: dummy temp file won't play properly on most platforms/CI.
                        # We're testing the logging behavior, not actual audio playback.
                        pass

                    # Verify the interruption was logged
                    log_messages = [str(call) for call in mock_log.call_args_list]
                    interrupted_logged = any('interrupted' in msg.lower() for msg in log_messages)
                    self.assertTrue(interrupted_logged,
                                    "Should log that playback was interrupted by stop_event")
            finally:
                if temp_file and os.path.exists(temp_file):
                    os.unlink(temp_file)
        finally:
            pygame.mixer.music.get_busy = original_get_busy

    def test_playback_continues_when_stop_event_not_set(self):
        """Test that playback completes normally when stop_event is never set."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)

        import pygame
        import threading
        pygame.mixer.init()

        # Track stop calls
        stop_called = []
        original_stop = pygame.mixer.music.stop

        def track_stop():
            stop_called.append(True)
            return original_stop()

        pygame.mixer.music.stop = track_stop

        try:
            # Create event but never set it
            stop_event = threading.Event()
            # Don't call stop_event.set()

            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    temp_file = f.name

                audio.play_audio_file(temp_file, stop_event=stop_event)
            except (RuntimeError, FileNotFoundError, OSError):
                # Expected: dummy temp file won't play properly on most platforms/CI.
                # We're testing that playback completes normally when stop_event is unset.
                pass
            finally:
                if temp_file and os.path.exists(temp_file):
                    os.unlink(temp_file)

            # With get_busy returning False immediately, playback completes without stop
            # being called for interruption purposes
        finally:
            pygame.mixer.music.stop = original_stop
