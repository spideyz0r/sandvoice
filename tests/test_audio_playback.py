import os
import sys
import types
import unittest
import tempfile
from unittest.mock import Mock, patch


def _install_fake_deps_for_common_audio():
    # Minimal stub modules so `common.audio` can be imported without native deps.
    fake_pyaudio = types.SimpleNamespace(paInt16=8, PyAudio=object)
    fake_lameenc = types.SimpleNamespace(Encoder=object)

    fake_keyboard = types.SimpleNamespace(Listener=object)
    fake_pynput = types.SimpleNamespace(keyboard=fake_keyboard)

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

    class _FakeTime:
        class Clock:
            def tick(self, _fps):
                return None

    fake_pygame = types.SimpleNamespace(mixer=_FakeMixer(), time=_FakeTime())

    sys.modules.setdefault('pyaudio', fake_pyaudio)
    sys.modules.setdefault('lameenc', fake_lameenc)
    sys.modules.setdefault('pynput', fake_pynput)
    sys.modules.setdefault('pynput.keyboard', fake_keyboard)
    sys.modules.setdefault('pygame', fake_pygame)


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
        
        pygame.mixer.music.stop = track_stop
        
        # Call stop_playback
        audio.stop_playback()
        
        # Verify stop was called
        self.assertTrue(len(stop_called) > 0)
    
    def test_stop_playback_safe_when_mixer_not_initialized(self):
        """Test that stop_playback is safe to call when mixer not initialized."""
        audio = self.Audio.__new__(self.Audio)
        audio.config = Mock(debug=False)
        
        import pygame
        pygame.mixer._init = None
        
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
            mock_log.assert_called_with("Audio playback stopped")

