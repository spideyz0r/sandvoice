import logging
import unittest
from unittest.mock import Mock, patch

import struct

from common.utils import _is_enabled_flag
from common.vad_recorder import VadRecorder, _negotiate_sample_rate, _rms


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
        self.mock_config.vad_energy_filter = False
        self.mock_config.vad_energy_threshold_multiplier = 2.5
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
        # filter=False: no calibration window; 3 speech + 3 silence frames only.
        # Frame 1-3 (speech): elapsed only = 1 call each
        # Frame 4 (silence, silence_start=None): elapsed + set silence_start = 2 calls
        # Frame 5 (silence, duration≥1.5 → break): elapsed + duration check = 2 calls
        # Post-loop: elapsed + wav_path = 2 calls
        all_frames = [b'\x00' * 960] * 6
        mock_time.side_effect = [0.0, 0.03, 0.06, 0.09, 0.12, 0.12, 0.15, 2.1, 2.1, 2.1]

        mock_vad = Mock()
        mock_vad.is_speech.side_effect = [True, True, True, False, False, False]
        mock_vad_class.return_value = mock_vad

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(all_frames):
                f = all_frames[read_idx[0]]
                read_idx[0] += 1
                return f
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
        # filter=False: no calibration window; WebRTC=True on frame 1 → speech_detected=True.
        # Frame 2 elapsed check fires timeout → WAV written.
        mock_time.side_effect = [0.0, 0.03, 31.0, 31.0, 31.0]

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

        # Filter disabled → no calibration window; WebRTC=True on frame 1 sets speech_detected=True.
        # Timeout fires on frame 2 elapsed check → WAV written (frames exist, speech_detected=True).
        self.assertIsNotNone(path)

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

    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_read_timeout_breaks_loop_and_returns_none(
            self, mock_pa_class, mock_vad_class):
        """audio_stream.read() that never returns (ALSA overrun spin-loop) is escaped
        by the per-read timeout; record() returns None and cleanup is called."""
        import threading

        hang_event = threading.Event()

        def hanging_read(size, exception_on_overflow=False):
            hang_event.wait()
            return b'\x00' * size

        mock_stream = Mock()
        mock_stream.read = hanging_read

        # stop_stream() is what unblocks read() in real ALSA (SNDRV_PCM_IOCTL_DROP).
        # Mirror that here so shutdown(wait=True) does not deadlock the test.
        mock_stream.stop_stream.side_effect = hang_event.set

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa_class.return_value = mock_pa

        mock_vad = Mock()
        mock_vad_class.return_value = mock_vad

        recorder = self._make_recorder()
        result = recorder.record()

        # Timeout fires before any frame is processed → no speech_detected → None
        self.assertIsNone(result)
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_record_vad_error_assumes_speech_and_continues(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        # filter=False → no calibration window; 3 frames total, all raise VAD error → assume speech
        frames = [b'\x00' * 960] * 3
        # recording_start + 3 frames (speech_detected=True from frame 1: 1 elapsed each)
        # + timeout fires on frame 4 elapsed; post-loop elapsed + wav_path
        mock_time.side_effect = [0.0, 0.03, 0.06, 0.09, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.side_effect = Exception("VAD error")
        mock_vad_class.return_value = mock_vad

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames):
                f = frames[read_idx[0]]
                read_idx[0] += 1
                return f
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

        # VAD errors assumed as speech (filter=False, no calibration, vad_error skips gate)
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
        # Timeout on first frame check; test only validates pa.open rate arg
        mock_time.side_effect = [0.0, 31.0]

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
        # filter=False: frame 1 WebRTC=True → speech_detected=True; frame 2 timeout → wav write fails
        mock_time.side_effect = [0.0, 0.03, 31.0, 31.0, 31.0]
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
        self.mock_config.vad_energy_filter = False
        self.mock_config.vad_energy_threshold_multiplier = 2.5
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

        # vad_energy_filter=False → no calibration window; WebRTC runs from frame 1.
        # 15 frames (WebRTC=True, speech_detected after frame 1): 1 elapsed call each.
        # Frame 16: elapsed=0.45, WebRTC=True; frame 17: elapsed=31.0 → timeout break.
        # Post-loop: elapsed, wav_path.
        pre_speech_frames = [i * 0.03 for i in range(15)]
        mock_time.side_effect = [0.0] + pre_speech_frames + [0.45, 31.0, 31.0, 31.0]

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

        # vad_energy_filter=False → no calibration; same timing pattern as the plays-earcon test.
        pre_speech_frames = [i * 0.03 for i in range(15)]
        mock_time.side_effect = [0.0] + pre_speech_frames + [0.45, 31.0, 31.0, 31.0]

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


class TestRms(unittest.TestCase):
    def _make_pcm(self, value, count):
        """Return PCM bytes with `count` samples all equal to `value`."""
        return struct.pack(f"{count}h", *([value] * count))

    def test_zero_signal_returns_zero(self):
        pcm = self._make_pcm(0, 160)
        self.assertEqual(_rms(pcm), 0.0)

    def test_constant_signal_returns_amplitude(self):
        # All samples = 1000 → RMS = 1000
        pcm = self._make_pcm(1000, 160)
        self.assertAlmostEqual(_rms(pcm), 1000.0, places=1)

    def test_empty_input_returns_zero(self):
        self.assertEqual(_rms(b''), 0.0)

    def test_single_byte_returns_zero(self):
        # 1 byte = 0 complete 16-bit samples
        self.assertEqual(_rms(b'\x00'), 0.0)

    def test_mixed_signal(self):
        # Samples alternating +1000 and -1000 → RMS still 1000
        pcm = struct.pack("4h", 1000, -1000, 1000, -1000)
        self.assertAlmostEqual(_rms(pcm), 1000.0, places=1)


def _make_pcm_with_rms(target_rms, n_samples=480):
    """Return PCM bytes where all samples equal target_rms (gives exact RMS)."""
    val = int(target_rms)
    return struct.pack(f"{n_samples}h", *([val] * n_samples))


class TestEnergyFilter(unittest.TestCase):
    """Tests for the adaptive energy pre-filter inside VadRecorder.record()."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.mock_config = Mock()
        self.mock_config.rate = 16000
        self.mock_config.vad_aggressiveness = 3
        self.mock_config.vad_frame_duration = 30
        self.mock_config.vad_timeout = 30
        self.mock_config.vad_silence_duration = 1.5
        self.mock_config.vad_energy_filter = True
        self.mock_config.vad_energy_threshold_multiplier = 2.5
        self.mock_config.tmp_files_path = "/tmp/test/"
        self.mock_config.voice_ack_earcon = False

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_recorder(self):
        return VadRecorder(self.mock_config, Mock(), None)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_energy_gate_enables_silence_detection_over_tv_noise(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        """Gate allows silence detection to work even when TV audio makes WebRTC say True.

        Without the gate: WebRTC returns True for every frame (TV + speech + post-speech TV),
        silence_start never gets set, recording never ends until vad_timeout.
        With the gate: post-speech TV frames are suppressed → silence counter ticks → recording
        ends within vad_silence_duration.

        Calibration runs unconditionally on frames 1-15 (TV level RMS 200),
        so noise_floor is established even though WebRTC fires True throughout.
        """
        tv_pcm = _make_pcm_with_rms(200)      # TV noise, below gate (200 < 200*2.5=500)
        speech_pcm = _make_pcm_with_rms(5000)  # User speech, above gate

        # 15 calibration (TV) + 3 speech + 3 TV noise after speech
        frames_returned = [tv_pcm] * 15 + [speech_pcm] * 3 + [tv_pcm] * 3

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        # WebRTC says True for every frame — gate is the only thing that can detect silence
        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        # recording_start=0.0
        # 15 calibration frames: pre-speech bail skipped (calibrating=True) → 1 elapsed call each.
        #   TV noise in upper half: 200 < 200*2.5=500 → no retroactive speech detected.
        # 3 speech frames (post-calibration, gate passes: 5000>500): 1 call each
        # TV frame 1 (gate suppresses BEFORE WebRTC → is_speech=False, silence_start set): 2 calls
        # TV frame 2 (gate suppresses → silence_duration=2.1-0.54=1.56≥1.5 → break): 2 calls
        # Post-loop: elapsed + wav_path = 2 calls
        times = ([0.0]
                 + [i * 0.03 for i in range(15)]  # 15 calibration frames: 1 call each
                 + [0.45, 0.48, 0.51]               # 3 speech frames
                 + [0.54, 0.54]                      # TV frame 1: elapsed + silence_start
                 + [0.57, 2.1]                       # TV frame 2: elapsed + duration
                 + [2.1, 2.1])                       # post-loop
        mock_time.side_effect = times

        recorder = self._make_recorder()
        result = recorder.record()

        # Gate suppressed post-speech TV frames → silence detected → WAV returned
        self.assertIsNotNone(result)
        # WebRTC only called for post-calibration frames that pass the energy gate.
        # TV frames (RMS=200 < 500) are blocked by the gate before reaching WebRTC.
        # Only the 3 speech frames (RMS=5000 > 500) call WebRTC.
        self.assertEqual(mock_vad.is_speech.call_count, 3)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_energy_gate_passes_high_energy_speech_frames(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        """Frames above the energy gate pass through normally and are recorded.

        Calibration (15 frames, WebRTC=False, RMS=100) → noise_floor=100, threshold=250.
        Speech frames (RMS=3000, WebRTC=True) → 3000 > 250, passes gate → speech_detected.
        Silence frames (RMS=50, WebRTC=False) → silence counter → recording ends.
        """
        noise_pcm = _make_pcm_with_rms(100)
        speech_pcm = _make_pcm_with_rms(3000)
        silence_pcm = _make_pcm_with_rms(50)

        # 15 calibration + 3 speech + 3 silence
        frames_returned = [noise_pcm] * 15 + [speech_pcm] * 3 + [silence_pcm] * 3

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        # WebRTC is not called during calibration or for low-energy (gate-blocked) frames.
        # Silence frames (RMS=50 < 250) are blocked by the gate before reaching WebRTC.
        # Only 3 speech frames (RMS=3000 > 250) call WebRTC.
        mock_vad = Mock()
        mock_vad.is_speech.side_effect = [True] * 3
        mock_vad_class.return_value = mock_vad

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        # recording_start=0.0
        # 15 calibration frames: 1 elapsed call each (pre-speech bail skipped while calibrating)
        # 3 speech frames (gate passes: 3000>100*2.5=250, WebRTC=True): 1 call each
        # Silence frame 1 (gate blocks: 50<250, silence_start=None → set): elapsed + silence_start = 2 calls
        # Silence frame 2 (gate blocks, duration=2.1-0.54=1.56≥1.5 → break): elapsed + duration = 2 calls
        # Post-loop: elapsed + wav_path = 2 calls
        calibration_times = [i * 0.03 for i in range(15)]
        speech_times = [0.45, 0.48, 0.51]
        silence_times = [0.54, 0.54, 0.57, 2.1, 2.1, 2.1]
        times = [0.0] + calibration_times + speech_times + silence_times
        mock_time.side_effect = times

        recorder = self._make_recorder()
        result = recorder.record()

        # High energy speech was not suppressed → WAV written → path returned
        self.assertIsNotNone(result)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_energy_filter_disabled_passes_all_webrtc_speech(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        """When vad_energy_filter=False, low-energy frames that WebRTC marks as speech are not suppressed."""
        self.mock_config.vad_energy_filter = False

        low_energy_pcm = _make_pcm_with_rms(50)
        silence_pcm = _make_pcm_with_rms(0)

        # filter=False: no calibration window; 3 speech + 3 silence frames only.
        # WebRTC is called from frame 1.
        frames_returned = [low_energy_pcm] * 3 + [silence_pcm] * 3

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        # WebRTC is called from frame 1: 3 True (speech) + 2 False (silence before break)
        mock_vad = Mock()
        mock_vad.is_speech.side_effect = [True, True, True, False, False, False]
        mock_vad_class.return_value = mock_vad

        # recording_start + 3 speech (1 call each, speech_detected=True from frame 1)
        # + silence frame 1 (elapsed + set silence_start=2 calls)
        # + silence frame 2 (elapsed + duration≥1.5 → break=2 calls)
        # + post-loop (elapsed + wav_path=2 calls)
        times = [0.0, 0.03, 0.06, 0.09, 0.12, 0.12, 0.15, 2.1, 2.1, 2.1]
        mock_time.side_effect = times

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        recorder = self._make_recorder()
        result = recorder.record()

        # filter=False: low-energy speech frames passed WebRTC; WAV written
        self.assertIsNotNone(result)
        # 5 frames called WebRTC: 3 speech + 2 silence (loop breaks on 2nd silence frame)
        self.assertEqual(mock_vad.is_speech.call_count, 5)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_early_speech_during_calibration_is_captured(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        """User speech that starts during the calibration window is not dropped.

        Mixed calibration frames: 7 ambient (RMS=50) + 8 speech (RMS=3000).
        Lower-half mean ≈ 50, threshold = 50*2.5 = 125.
        Upper-half frames (3000) ≥ 125 → speech_detected=True retroactively after frame 15.
        Stream raises on frame 16; post-loop writes WAV and returns path.
        WebRTC is never called during calibration.
        """
        ambient_pcm = _make_pcm_with_rms(50)
        speech_pcm = _make_pcm_with_rms(3000)
        frames_returned = [ambient_pcm] * 7 + [speech_pcm] * 8

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        mock_vad = Mock()
        mock_vad_class.return_value = mock_vad

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        # Frames 0-13: 1 elapsed call each (pre-speech bail skipped while calibrating).
        # Frame 14 (last calibration, retroactive fires → speech_detected=True, is_speech=False
        #   → silence_start branch runs): elapsed + silence_start = 2 calls.
        # Frame 15: elapsed → stream raises → break; post-loop: elapsed + wav_path.
        calib = [i * 0.03 for i in range(14)] + [0.42, 0.42]
        times = [0.0] + calib + [0.45, 0.45, 0.45]
        mock_time.side_effect = times

        recorder = self._make_recorder()
        result = recorder.record()

        # speech_detected set retroactively from upper-half calibration frames → WAV returned
        self.assertIsNotNone(result)
        # WebRTC is not called during calibration
        mock_vad.is_speech.assert_not_called()

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_energy_calibration_uses_exactly_15_pre_speech_frames(
            self, mock_pa_class, mock_vad_class, mock_time):
        """Noise floor is computed from exactly _ENERGY_CALIBRATION_FRAMES pre-speech frames."""
        from common.vad_recorder import _ENERGY_CALIBRATION_FRAMES

        noise_pcm = _make_pcm_with_rms(200)
        # Feed exactly _ENERGY_CALIBRATION_FRAMES frames then raise to end loop
        frames_returned = [noise_pcm] * _ENERGY_CALIBRATION_FRAMES

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End of calibration frames")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa_class.return_value = mock_pa

        # WebRTC says False throughout so speech_detected stays False → calibration runs
        mock_vad = Mock()
        mock_vad.is_speech.return_value = False
        mock_vad_class.return_value = mock_vad

        # 1 elapsed call per calibration frame (pre-speech bail skipped while calibrating).
        # +1 extra at end: loop starts iteration N+1, calls time.time() for elapsed,
        # then stream.read() raises and breaks — so we need that one extra value.
        times = [0.0] + [i * 0.03 for i in range(_ENERGY_CALIBRATION_FRAMES)] + [1.0]
        mock_time.side_effect = times

        recorder = self._make_recorder()
        recorder.record()

        # All _ENERGY_CALIBRATION_FRAMES frames were read
        self.assertEqual(read_idx[0], _ENERGY_CALIBRATION_FRAMES)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_energy_calibration_frame_count_scales_with_frame_duration(
            self, mock_pa_class, mock_vad_class, mock_time):
        """Calibration window uses round(450ms / frame_duration_ms) frames, not a fixed 15.

        With vad_frame_duration=20ms: round(450/20)=22 calibration frames (Python banker's
        rounding: 22.5 rounds to 22).
        With vad_frame_duration=10ms: round(450/10)=45 calibration frames.
        This test exercises the 20ms case to verify n_calibration_frames is computed
        dynamically and not hardcoded to _ENERGY_CALIBRATION_FRAMES (which assumes 30ms).
        """
        self.mock_config.vad_frame_duration = 20
        expected_calib_frames = round(450 / 20)  # 22 (banker's rounding: 22.5 → 22)

        noise_pcm = _make_pcm_with_rms(200)
        frames_returned = [noise_pcm] * expected_calib_frames

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa_class.return_value = mock_pa

        mock_vad = Mock()
        mock_vad.is_speech.return_value = False
        mock_vad_class.return_value = mock_vad

        # 1 elapsed call per calibration frame + 1 extra for the iteration that raises.
        times = [0.0] + [i * 0.02 for i in range(expected_calib_frames)] + [1.0]
        mock_time.side_effect = times

        recorder = self._make_recorder()
        recorder.record()

        # Exactly 22 frames consumed — confirms frame count scales with frame_duration_ms
        self.assertEqual(read_idx[0], expected_calib_frames)
        # WebRTC not called during calibration
        mock_vad.is_speech.assert_not_called()

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_noise_floor_uses_lower_half_to_resist_early_speech(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        """Noise floor uses lower-half mean so early speech frames do not inflate it.

        Scenario: user starts talking after frame 7 of calibration.
        Frames 0-6: ambient RMS=100 (7 frames)
        Frames 7-14: user speech RMS=2000 (8 frames)
        Sorted lower half (first 7): all 100 → noise_floor=100, threshold=250.
        Post-calibration speech at RMS=2000 must pass the gate (2000 > 250).
        If mean were used instead: noise_floor=(7*100+8*2000)/15≈1107, threshold≈2767,
        so post-calibration speech at 2000 would be suppressed.
        """
        from common.vad_recorder import _ENERGY_CALIBRATION_FRAMES
        ambient_pcm = _make_pcm_with_rms(100)
        speech_pcm = _make_pcm_with_rms(2000)

        # 7 ambient + 8 speech during calibration, then 1 post-calibration speech frame
        frames_returned = (
            [ambient_pcm] * 7 + [speech_pcm] * 8   # calibration
            + [speech_pcm]                           # post-calibration: must pass gate
        )

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa_class.return_value = mock_pa

        # Post-calibration: WebRTC says True for the speech frame
        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        # recording_start: 1 call.
        # Frames 0-13: 1 elapsed call each (pre-speech bail skipped while calibrating).
        # Frame 14 (last calibration): elapsed=0.42 + silence_start=0.42 = 2 calls.
        #   Retroactive fires (upper-half RMS=2000 ≥ 100*2.5=250) → speech_detected=True,
        #   is_speech=False → silence_start = time.time().
        # Frame 15 (post-calibration speech, RMS=2000 > 250 → passes gate → WebRTC called):
        #   elapsed=0.45 → WebRTC returns True → speech_detected=True, silence_start reset.
        # Frame 16: stream raises → break. Post-loop: elapsed + wav_path = 2 calls.
        # Total: 1 + 14 + 2 + 1 + 1 + 2 = 21.
        calib_times = [i * 0.03 for i in range(14)] + [0.42, 0.42]  # frame 14: elapsed + silence_start
        times = [0.0] + calib_times + [0.45, 31.0, 31.0, 31.0]
        mock_time.side_effect = times

        recorder = self._make_recorder()
        result = recorder.record()

        # Lower-half noise floor=100 → threshold=250; post-calibration speech RMS=2000 passes gate →
        # WebRTC confirms speech → WAV written. If mean were used instead, threshold≈2767 and
        # RMS=2000 would be suppressed.
        self.assertIsNotNone(result)
        # WebRTC called exactly once: calibration skips it; only the post-calibration frame reaches it.
        self.assertEqual(mock_vad.is_speech.call_count, 1)

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_silent_calibration_does_not_trigger_retroactive_speech(
            self, mock_pa_class, mock_vad_class, mock_time):
        """A completely silent calibration (all RMS=0) must not set speech_detected via 0>=0."""
        from common.vad_recorder import _ENERGY_CALIBRATION_FRAMES
        silent_pcm = _make_pcm_with_rms(0)
        frames_returned = [silent_pcm] * _ENERGY_CALIBRATION_FRAMES

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa_class.return_value = mock_pa

        mock_vad = Mock()
        mock_vad_class.return_value = mock_vad

        # 1 elapsed call per calibration frame (pre-speech bail skipped during calibration)
        # + 1 extra for the iteration that hits stream.read raise
        times = [0.0] + [i * 0.03 for i in range(_ENERGY_CALIBRATION_FRAMES)] + [0.45]
        mock_time.side_effect = times

        recorder = self._make_recorder()
        result = recorder.record()

        # All-silent calibration: threshold=0, retroactive check skipped → no speech_detected → None
        self.assertIsNone(result)
        mock_vad.is_speech.assert_not_called()

    @patch('common.vad_recorder.time.time')
    @patch('common.vad_recorder.os.makedirs')
    @patch('common.vad_recorder.wave.open')
    @patch('common.vad_recorder.webrtcvad.Vad')
    @patch('common.vad_recorder.pyaudio.PyAudio')
    def test_known_limitation_all_speech_calibration_discards_utterance(
            self, mock_pa_class, mock_vad_class, mock_wave_open, mock_makedirs, mock_time):
        """Regression test for known limitation: all-speech calibration poisons the noise floor.

        TODO: This test documents a failure mode that should be fixed. When the user speaks
        immediately after the wake word fires and their voice fills all calibration frames,
        the lower-half mean equals speech RMS, threshold is set above continued speech, and
        the recording is discarded (returns None) even though real speech occurred.

        The current implementation cannot distinguish all-speech calibration from
        all-ambient-at-the-same-level using RMS alone; the retroactive check only fires for
        bimodal distributions. A future fix should ensure record() returns a WAV when all
        calibration frames contain the user's voice.

        If the whole calibration window is speech (RMS=2000), lower-half mean=2000 and
        threshold=5000. Upper-half frames (2000) are below the 5000 threshold → no retroactive
        detection → speech_detected=False → None (with no post-calibration frames).
        """
        from common.vad_recorder import _ENERGY_CALIBRATION_FRAMES
        speech_pcm = _make_pcm_with_rms(2000)
        frames_returned = [speech_pcm] * _ENERGY_CALIBRATION_FRAMES

        read_idx = [0]
        def mock_read(size, exception_on_overflow=False):
            if read_idx[0] < len(frames_returned):
                f = frames_returned[read_idx[0]]
                read_idx[0] += 1
                return f
            raise Exception("End")

        mock_stream = Mock()
        mock_stream.read = mock_read
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pa_class.return_value = mock_pa

        # Post-calibration: timeout fires before any WebRTC call (stream raises)
        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        # 1 elapsed/calibration frame + stream raises on frame 16 + timeout (31.0) + post-loop
        times = [0.0] + [i * 0.03 for i in range(_ENERGY_CALIBRATION_FRAMES)] + [31.0, 31.0, 31.0]
        mock_time.side_effect = times

        recorder = self._make_recorder()
        result = recorder.record()

        # Known limitation: noise floor = speech level → threshold above speech RMS →
        # no retroactive detection → speech_detected=False → None.
        # TODO: this should return a WAV once the all-speech calibration case is handled.
        self.assertIsNone(result)
        mock_vad.is_speech.assert_not_called()
