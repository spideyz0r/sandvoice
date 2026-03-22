import logging
import unittest
from unittest.mock import Mock, patch

from common.utils import _is_enabled_flag
from common.vad_recorder import VadRecorder, _negotiate_sample_rate


class TestIsEnabledFlag(unittest.TestCase):
    def test_true_bool(self):
        self.assertTrue(_is_enabled_flag(True))

    def test_false_bool(self):
        self.assertFalse(_is_enabled_flag(False))

    def test_enabled_string(self):
        self.assertTrue(_is_enabled_flag("enabled"))
        self.assertTrue(_is_enabled_flag("true"))
        self.assertTrue(_is_enabled_flag("yes"))
        self.assertTrue(_is_enabled_flag("1"))
        self.assertTrue(_is_enabled_flag("on"))

    def test_disabled_string(self):
        self.assertFalse(_is_enabled_flag("disabled"))
        self.assertFalse(_is_enabled_flag("false"))
        self.assertFalse(_is_enabled_flag("no"))
        self.assertFalse(_is_enabled_flag("0"))
        self.assertFalse(_is_enabled_flag("off"))

    def test_nonzero_int(self):
        self.assertTrue(_is_enabled_flag(1))
        self.assertTrue(_is_enabled_flag(42))

    def test_zero_int(self):
        self.assertFalse(_is_enabled_flag(0))

    def test_unknown_type(self):
        self.assertFalse(_is_enabled_flag(None))
        self.assertFalse(_is_enabled_flag([]))


class TestNegotiateSampleRate(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(_negotiate_sample_rate(16000), 16000)
        self.assertEqual(_negotiate_sample_rate(8000), 8000)
        self.assertEqual(_negotiate_sample_rate(48000), 48000)

    def test_nearest_match(self):
        # 44100 is closest to 48000
        self.assertEqual(_negotiate_sample_rate(44100), 48000)
        # 11025 is closest to 8000
        self.assertEqual(_negotiate_sample_rate(11025), 8000)


class TestVadRecorderRecord(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.rate = 16000
        self.mock_config.vad_aggressiveness = 3
        self.mock_config.vad_frame_duration = 30
        self.mock_config.vad_timeout = 30
        self.mock_config.vad_silence_duration = 1.5
        self.mock_config.tmp_files_path = "/tmp/test/"
        self.mock_config.voice_ack_earcon = False

        self.mock_audio = Mock()
        self.mock_audio_lock = None

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_recorder(self, ack_earcon_path=None):
        return VadRecorder(
            self.mock_config, self.mock_audio, self.mock_audio_lock,
            ack_earcon_path=ack_earcon_path,
        )

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_success_transitions_after_silence(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        mock_time.side_effect = [0.0] + [i * 0.03 for i in range(10)] + [1.5, 3.0, 3.0, 3.0]

        mock_vad = Mock()
        mock_vad.is_speech.side_effect = [True, True, True, False, False, False]
        mock_vad_class.return_value = mock_vad

        read_count = [0]
        def mock_read(size, exception_on_overflow=False):
            read_count[0] += 1
            if read_count[0] <= 6:
                return b'\x00' * 960
            raise Exception("End of test")

        mock_stream = Mock()
        mock_stream.read = mock_read

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        recorder = self._make_recorder()
        path = recorder.record()

        self.assertIsNotNone(path)
        self.assertTrue(path.endswith('.wav'))
        mock_wf.writeframes.assert_called_once()
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_returns_none_when_no_frames(self, mock_pa_class, mock_vad_class, mock_time):
        # Timeout immediately, stream read fails before any frames appended
        mock_time.side_effect = [0.0, 31.0]

        mock_vad = Mock()
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("No audio")

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa_class.return_value = mock_pa

        recorder = self._make_recorder()
        result = recorder.record()

        self.assertIsNone(result)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_timeout_exits_loop(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        # recording_start=0, elapsed below timeout, read 1 frame, elapsed exceeds timeout, then log+filename
        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        recorder = self._make_recorder()
        path = recorder.record()

        self.assertIsNotNone(path)
        self.assertEqual(mock_vad.is_speech.call_count, 1)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_stream_read_error_breaks_loop(self, mock_pa_class, mock_vad_class, mock_time):
        mock_time.side_effect = [0.0, 0.1]

        mock_vad = Mock()
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("Stream error")

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa_class.return_value = mock_pa

        recorder = self._make_recorder()
        result = recorder.record()

        # No frames → None
        self.assertIsNone(result)
        mock_stream.stop_stream.assert_called_once()

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_vad_error_assumes_speech_and_continues(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        mock_time.side_effect = [0.0] + [i * 0.03 for i in range(10)] + [31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.side_effect = Exception("VAD error")
        mock_vad_class.return_value = mock_vad

        read_count = [0]
        def mock_read(size, exception_on_overflow=False):
            read_count[0] += 1
            if read_count[0] <= 3:
                return b'\x00' * 960
            raise Exception("End")
        mock_stream = Mock()
        mock_stream.read = mock_read

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        recorder = self._make_recorder()
        path = recorder.record()

        # VAD errors assumed as speech; frames captured → returns path
        self.assertIsNotNone(path)
        self.assertEqual(mock_vad.is_speech.call_count, 3)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_sample_rate_negotiation(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        self.mock_config.rate = 44100  # Not a VAD-supported rate → negotiates to 48000
        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        recorder = self._make_recorder()
        recorder.record()

        # PyAudio stream opened with negotiated rate (48000), not 44100
        call_kwargs = mock_pa.open.call_args[1]
        self.assertEqual(call_kwargs['rate'], 48000)

    @patch('common.vad_recorder.os.remove')
    @patch('common.vad_recorder.os.path.exists')
    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_wav_write_failure_raises_and_removes_file(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs,
            mock_time, mock_exists, mock_remove):
        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]
        # Simulate partial file left on disk after wave.open failure
        mock_exists.return_value = True

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_wave_open.side_effect = OSError("Disk full")

        recorder = self._make_recorder()

        with self.assertRaises(OSError):
            recorder.record()

        # Verify partial file is cleaned up
        mock_remove.assert_called_once()


class TestVadRecorderCleanupStream(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.recorder = VadRecorder(Mock(), Mock(), None)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_cleanup_stream_stops_and_closes(self):
        mock_stream = Mock()
        mock_pa = Mock()

        self.recorder._cleanup_stream(mock_stream, mock_pa)

        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    def test_cleanup_stream_handles_none_stream(self):
        mock_pa = Mock()
        # Should not raise
        self.recorder._cleanup_stream(None, mock_pa)
        mock_pa.terminate.assert_called_once()

    def test_cleanup_stream_handles_none_pa(self):
        mock_stream = Mock()
        # Should not raise
        self.recorder._cleanup_stream(mock_stream, None)
        mock_stream.stop_stream.assert_called_once()

    def test_cleanup_stream_swallows_exceptions(self):
        mock_stream = Mock()
        mock_stream.stop_stream.side_effect = Exception("Error")
        mock_stream.close.side_effect = Exception("Error")
        mock_pa = Mock()
        mock_pa.terminate.side_effect = Exception("Error")

        # Should not raise
        self.recorder._cleanup_stream(mock_stream, mock_pa)


class TestVadRecorderPlayAckEarcon(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_recorder(self, ack_earcon_path=None):
        return VadRecorder(
            self.mock_config, self.mock_audio, None,
            ack_earcon_path=ack_earcon_path,
        )

    @patch('common.vad_recorder.os.path.exists')
    def test_plays_earcon_when_configured(self, mock_exists):
        self.mock_config.voice_ack_earcon = True
        self.mock_audio.is_playing.return_value = False
        mock_exists.return_value = True

        recorder = self._make_recorder(ack_earcon_path="/tmp/ack.mp3")
        recorder._play_ack_earcon()

        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/ack.mp3")

    def test_skips_earcon_when_disabled(self):
        self.mock_config.voice_ack_earcon = False

        recorder = self._make_recorder(ack_earcon_path="/tmp/ack.mp3")
        recorder._play_ack_earcon()

        self.mock_audio.play_audio_file.assert_not_called()

    def test_skips_earcon_when_path_is_none(self):
        self.mock_config.voice_ack_earcon = True

        recorder = self._make_recorder(ack_earcon_path=None)
        recorder._play_ack_earcon()

        self.mock_audio.play_audio_file.assert_not_called()

    @patch('common.vad_recorder.os.path.exists')
    def test_skips_earcon_when_file_missing(self, mock_exists):
        self.mock_config.voice_ack_earcon = True
        mock_exists.return_value = False

        recorder = self._make_recorder(ack_earcon_path="/tmp/ack.mp3")
        recorder._play_ack_earcon()

        self.mock_audio.play_audio_file.assert_not_called()

    @patch('common.vad_recorder.os.path.exists')
    def test_skips_earcon_when_audio_is_playing(self, mock_exists):
        self.mock_config.voice_ack_earcon = True
        self.mock_audio.is_playing.return_value = True
        mock_exists.return_value = True

        recorder = self._make_recorder(ack_earcon_path="/tmp/ack.mp3")
        recorder._play_ack_earcon()

        self.mock_audio.play_audio_file.assert_not_called()

    @patch('common.vad_recorder.os.path.exists')
    def test_earcon_uses_audio_lock_when_provided(self, mock_exists):
        self.mock_config.voice_ack_earcon = True
        self.mock_audio.is_playing.return_value = False
        mock_exists.return_value = True

        import threading
        lock = threading.Lock()
        recorder = VadRecorder(
            self.mock_config, self.mock_audio, lock,
            ack_earcon_path="/tmp/ack.mp3",
        )
        recorder._play_ack_earcon()

        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/ack.mp3")

    @patch('common.vad_recorder.os.path.exists')
    def test_earcon_handles_playback_exception(self, mock_exists):
        self.mock_config.voice_ack_earcon = True
        self.mock_audio.is_playing.return_value = False
        self.mock_audio.play_audio_file.side_effect = Exception("Audio error")
        mock_exists.return_value = True

        recorder = self._make_recorder(ack_earcon_path="/tmp/ack.mp3")
        # Should not raise
        recorder._play_ack_earcon()

    @patch('common.vad_recorder.os.path.exists')
    def test_earcon_with_no_is_playing_method(self, mock_exists):
        self.mock_config.voice_ack_earcon = True
        # Use a mock without is_playing so getattr(audio, 'is_playing', None) returns None
        self.mock_audio = Mock(spec=['play_audio_file'])
        mock_exists.return_value = True

        recorder = self._make_recorder(ack_earcon_path="/tmp/ack.mp3")
        recorder._play_ack_earcon()

        # Should play when is_playing is not available (default to not playing)
        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/ack.mp3")


class TestVadRecorderRecordWithEarcon(unittest.TestCase):
    """Integration: earcon is played at end of a successful record() call."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.rate = 16000
        self.mock_config.vad_aggressiveness = 3
        self.mock_config.vad_frame_duration = 30
        self.mock_config.vad_timeout = 30
        self.mock_config.vad_silence_duration = 1.5
        self.mock_config.tmp_files_path = "/tmp/test/"
        self.mock_config.voice_ack_earcon = True

        self.mock_audio = Mock()
        self.mock_audio.is_playing.return_value = False

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.vad_recorder.os.path.exists')
    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_plays_earcon_after_saving_wav(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs,
            mock_time, mock_exists):
        def exists_side_effect(path):
            return path == "/tmp/ack.mp3"
        mock_exists.side_effect = exists_side_effect

        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        recorder = VadRecorder(
            self.mock_config, self.mock_audio, None,
            ack_earcon_path="/tmp/ack.mp3",
        )
        path = recorder.record()

        self.assertIsNotNone(path)
        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/ack.mp3")

    @patch('common.vad_recorder.os.path.exists')
    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_skips_earcon_when_audio_already_playing(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs,
            mock_time, mock_exists):
        mock_exists.return_value = True
        self.mock_audio.is_playing.return_value = True

        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        recorder = VadRecorder(
            self.mock_config, self.mock_audio, None,
            ack_earcon_path="/tmp/ack.mp3",
        )
        recorder.record()

        self.mock_audio.play_audio_file.assert_not_called()
