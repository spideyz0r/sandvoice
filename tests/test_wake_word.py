import threading
import time
import unittest
import logging
from unittest.mock import Mock, patch

from common.wake_word import WakeWordMode, State


class TestWakeWordModeInitialization(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.wake_word_enabled = True
        self.mock_config.wake_phrase = "hey sandvoice"
        self.mock_config.wake_word_sensitivity = 0.5
        self.mock_config.porcupine_access_key = "test-key-123"
        self.mock_config.wake_confirmation_beep = True
        self.mock_config.wake_confirmation_beep_freq = 800
        self.mock_config.wake_confirmation_beep_duration = 0.1
        self.mock_config.tmp_files_path = "/tmp/test/"
        self.mock_config.visual_state_indicator = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_init_sets_initial_state(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        self.assertEqual(mode.state, State.IDLE)
        self.assertFalse(mode.running)
        self.assertIsNone(mode.porcupine)
        self.assertIsNone(mode.confirmation_beep_path)

    def test_init_stores_dependencies(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        self.assertEqual(mode.config, self.mock_config)
        self.assertEqual(mode.ai, self.mock_ai)
        self.assertEqual(mode.audio, self.mock_audio)


class TestWakeWordModeInitialize(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.wake_phrase = "porcupine"
        self.mock_config.wake_word_sensitivity = 0.5
        self.mock_config.porcupine_access_key = "test-key-123"
        self.mock_config.porcupine_keyword_paths = None
        self.mock_config.wake_confirmation_beep = True
        self.mock_config.wake_confirmation_beep_freq = 800
        self.mock_config.wake_confirmation_beep_duration = 0.1
        self.mock_config.tmp_files_path = "/tmp/test/"

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_creates_porcupine(self, mock_beep, mock_porcupine_create):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.return_value = "/tmp/test/beep.mp3"

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode._initialize()

        mock_porcupine_create.assert_called_once_with(
            access_key="test-key-123",
            keywords=["porcupine"],
            sensitivities=[0.5]
        )
        self.assertEqual(mode.porcupine, mock_porcupine)

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_creates_confirmation_beep(self, mock_beep, mock_porcupine_create):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.return_value = "/tmp/test/beep.mp3"

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode._initialize()

        mock_beep.assert_called_once_with(
            freq=800,
            duration=0.1,
            tmp_path="/tmp/test/"
        )
        self.assertEqual(mode.confirmation_beep_path, "/tmp/test/beep.mp3")

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_ack_earcon')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_creates_ack_earcon_when_enabled(self, mock_beep, mock_ack, mock_porcupine_create):
        self.mock_config.bot_voice = True
        self.mock_config.voice_ack_earcon = True
        self.mock_config.voice_ack_earcon_freq = 600
        self.mock_config.voice_ack_earcon_duration = 0.06

        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.return_value = "/tmp/test/beep.mp3"
        mock_ack.return_value = "/tmp/test/ack.mp3"

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode._initialize()

        mock_ack.assert_called_once_with(
            freq=600,
            duration=0.06,
            tmp_path="/tmp/test/",
        )
        self.assertEqual(mode.ack_earcon_path, "/tmp/test/ack.mp3")

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_ack_earcon')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_does_not_create_ack_earcon_when_bot_voice_disabled(self, mock_beep, mock_ack, mock_porcupine_create):
        self.mock_config.bot_voice = False
        self.mock_config.voice_ack_earcon = True
        self.mock_config.voice_ack_earcon_freq = 600
        self.mock_config.voice_ack_earcon_duration = 0.06

        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.return_value = "/tmp/test/beep.mp3"

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode._initialize()

        mock_ack.assert_not_called()
        self.assertIsNone(mode.ack_earcon_path)

    @patch('common.wake_word.pvporcupine.create')
    def test_initialize_raises_on_missing_access_key(self, mock_porcupine_create):
        self.mock_config.porcupine_access_key = ""

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("access key is required", str(context.exception).lower())

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_handles_porcupine_error(self, mock_beep, mock_porcupine_create):
        mock_porcupine_create.side_effect = Exception("Porcupine init failed")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("Failed to initialize Porcupine", str(context.exception))

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_handles_beep_creation_error(self, mock_beep, mock_porcupine_create):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.side_effect = Exception("Beep creation failed")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode._initialize()

        self.assertIsNone(mode.confirmation_beep_path)


class TestWakeWordModeStateIdle(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.wake_phrase = "hey sandvoice"
        self.mock_config.wake_word_sensitivity = 0.5
        self.mock_config.visual_state_indicator = False
        self.mock_config.wake_confirmation_beep = True

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.struct.unpack_from')
    def test_state_idle_detects_wake_word(self, mock_unpack, mock_pyaudio_class):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.side_effect = [-1, -1, 0]

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 1024
        mock_unpack.return_value = [0] * 512

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = mock_porcupine
        mode.confirmation_beep_path = "/tmp/beep.mp3"
        mode.running = True
        mode.state = State.IDLE

        mode._state_idle()

        self.assertEqual(mode.state, State.LISTENING)
        self.assertEqual(mock_porcupine.process.call_count, 3)
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.struct.unpack_from')
    def test_state_idle_plays_confirmation_beep(self, mock_unpack, mock_pyaudio_class):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine.process.return_value = 0

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 1024
        mock_unpack.return_value = [0] * 512

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = mock_porcupine
        mode.confirmation_beep_path = "/tmp/beep.mp3"
        mode.running = True
        mode.state = State.IDLE

        mode._state_idle()

        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/beep.mp3")

    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.struct.unpack_from')
    def test_state_idle_handles_stream_error(self, mock_unpack, mock_pyaudio_class):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("Stream error")

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = mock_porcupine
        mode.running = True
        mode.state = State.IDLE

        mode._state_idle()

        self.assertFalse(mode.running)
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()


class TestWakeWordModeRun(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_run_transitions_through_states(self, mock_beep, mock_porcupine_create):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.return_value = "/tmp/beep.mp3"

        self.mock_config.porcupine_access_key = "test-key"
        self.mock_config.wake_phrase = "porcupine"
        self.mock_config.wake_word_sensitivity = 0.5
        self.mock_config.wake_confirmation_beep = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        # Mock state methods to simulate state transitions
        call_count = {'idle': 0}

        def mock_state_idle():
            call_count['idle'] += 1
            if call_count['idle'] == 1:
                mode.state = State.LISTENING
            else:
                mode.running = False

        def mock_state_listening():
            mode.state = State.PROCESSING

        def mock_state_processing():
            mode.state = State.RESPONDING

        def mock_state_responding():
            mode.state = State.IDLE

        mode._state_idle = mock_state_idle
        mode._state_listening = mock_state_listening
        mode._state_processing = mock_state_processing
        mode._state_responding = mock_state_responding

        mode.run()

        # Verify state machine cycled through all states
        self.assertEqual(call_count['idle'], 2)
        self.assertFalse(mode.running)

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_run_handles_keyboard_interrupt(self, mock_beep, mock_porcupine_create):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.return_value = "/tmp/beep.mp3"

        self.mock_config.porcupine_access_key = "test-key"
        self.mock_config.wake_phrase = "porcupine"
        self.mock_config.wake_word_sensitivity = 0.5
        self.mock_config.wake_confirmation_beep = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        def mock_state_idle():
            raise KeyboardInterrupt()

        mode._state_idle = mock_state_idle

        # Should not raise - should handle KeyboardInterrupt gracefully
        mode.run()

        # Cleanup should have been called
        self.assertIsNone(mode.porcupine)
        self.assertFalse(mode.running)


class TestWakeWordModeStateListening(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False
        self.mock_config.vad_enabled = True
        self.mock_config.vad_aggressiveness = 3
        self.mock_config.rate = 16000
        self.mock_config.channels = 1
        self.mock_config.vad_frame_duration = 30
        self.mock_config.vad_silence_duration = 1.5
        self.mock_config.vad_timeout = 30
        self.mock_config.tmp_files_path = "/tmp/test/"

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.time.time')
    @patch('common.wake_word.os.makedirs')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.pyaudio.PyAudio')
    def test_state_listening_plays_ack_earcon_before_processing(self, mock_pyaudio_class, mock_vad_class,
                                                               mock_wave_open, mock_makedirs, mock_time, mock_exists):
        self.mock_config.bot_voice = True
        self.mock_config.voice_ack_earcon = True

        # Make ack mp3 appear to exist
        def exists_side_effect(path):
            return path == "/tmp/test/ack.mp3"
        mock_exists.side_effect = exists_side_effect

        # Time triggers timeout after 1 frame; still has frames so transitions to PROCESSING
        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pyaudio_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        # Ensure we don't skip due to "already playing"
        self.mock_audio.is_playing.return_value = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.ack_earcon_path = "/tmp/test/ack.mp3"
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/test/ack.mp3")
        self.assertEqual(mode.state, State.PROCESSING)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.time.time')
    @patch('common.wake_word.os.makedirs')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.pyaudio.PyAudio')
    def test_state_listening_skips_ack_earcon_when_audio_playing(self, mock_pyaudio_class, mock_vad_class,
                                                                 mock_wave_open, mock_makedirs, mock_time, mock_exists):
        self.mock_config.bot_voice = True
        self.mock_config.voice_ack_earcon = True

        def exists_side_effect(path):
            return path == "/tmp/test/ack.mp3"
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
        mock_pyaudio_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        self.mock_audio.is_playing.return_value = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.ack_earcon_path = "/tmp/test/ack.mp3"
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        self.mock_audio.play_audio_file.assert_not_called()
        self.assertEqual(mode.state, State.PROCESSING)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.time.time')
    @patch('common.wake_word.os.makedirs')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.pyaudio.PyAudio')
    def test_state_listening_skips_ack_earcon_when_disabled(self, mock_pyaudio_class, mock_vad_class,
                                                           mock_wave_open, mock_makedirs, mock_time, mock_exists):
        self.mock_config.bot_voice = True
        self.mock_config.voice_ack_earcon = False

        mock_exists.return_value = True
        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pyaudio_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.ack_earcon_path = "/tmp/test/ack.mp3"
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        self.mock_audio.play_audio_file.assert_not_called()
        self.assertEqual(mode.state, State.PROCESSING)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.time.time')
    @patch('common.wake_word.os.makedirs')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.pyaudio.PyAudio')
    def test_state_listening_skips_ack_earcon_when_missing_file(self, mock_pyaudio_class, mock_vad_class,
                                                                mock_wave_open, mock_makedirs, mock_time, mock_exists):
        self.mock_config.bot_voice = True
        self.mock_config.voice_ack_earcon = True

        mock_exists.return_value = False
        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pyaudio_class.return_value = mock_pa

        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        self.mock_audio.is_playing.return_value = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.ack_earcon_path = "/tmp/test/ack.mp3"
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        self.mock_audio.play_audio_file.assert_not_called()
        self.assertEqual(mode.state, State.PROCESSING)

    @patch('common.wake_word.time.time')
    @patch('common.wake_word.os.makedirs')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.pyaudio.PyAudio')
    def test_state_listening_records_and_detects_silence(self, mock_pyaudio_class, mock_vad_class,
                                                         mock_wave_open, mock_makedirs, mock_time):
        # Mock time progression: start, loop iterations with silence detection
        time_values = [0.0, 0.0]  # recording_start
        for i in range(6):  # 6 frames
            time_values.append(0.0 + i * 0.03)  # elapsed checks
        # silence_start, silence_duration checks (ensure >= vad_silence_duration), final elapsed
        time_values.extend([1.5, 3.0, 3.0, 3.0])  # 3.0 - 1.5 = 1.5s >= vad_silence_duration
        mock_time.side_effect = time_values

        # Mock VAD
        mock_vad = Mock()
        # First 3 frames: speech, next 3 frames: silence
        mock_vad.is_speech.side_effect = [True, True, True, False, False, False]
        mock_vad_class.return_value = mock_vad

        # Mock PyAudio stream
        mock_stream = Mock()
        # Return 6 frames then raise to break loop
        read_count = [0]
        def mock_read(size, exception_on_overflow=False):
            read_count[0] += 1
            if read_count[0] <= 6:
                return b'\x00' * 960  # 30ms at 16kHz mono
            raise Exception("End of test")
        mock_stream.read = mock_read

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2  # 16-bit = 2 bytes
        mock_pyaudio_class.return_value = mock_pa

        # Mock wave file
        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        # Verify VAD was initialized
        mock_vad_class.assert_called_once_with(3)

        # Verify audio stream was opened
        mock_pa.open.assert_called_once()

        # Verify WAV file was written
        self.assertTrue(mock_wave_open.called)
        self.assertTrue(mode.recorded_audio_path.endswith('.wav'))

        # Verify transition to PROCESSING
        self.assertEqual(mode.state, State.PROCESSING)

        # Verify stream cleanup
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    @patch('common.wake_word.time.time')
    @patch('common.wake_word.os.makedirs')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.pyaudio.PyAudio')
    def test_state_listening_handles_timeout(self, mock_pyaudio_class, mock_vad_class,
                                             mock_wave_open, mock_makedirs, mock_time):
        # Mock time to trigger timeout after 1 frame
        mock_time.side_effect = [0.0, 0.0, 31.0, 31.0, 31.0]  # Exceed 30s timeout, final elapsed

        mock_vad = Mock()
        mock_vad.is_speech.return_value = True
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.return_value = b'\x00' * 960

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pyaudio_class.return_value = mock_pa

        # Mock wave file
        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        # Should transition to PROCESSING after timeout
        self.assertEqual(mode.state, State.PROCESSING)

    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.webrtcvad.Vad')
    def test_state_listening_skips_when_vad_disabled(self, mock_vad_class, mock_pyaudio_class):
        self.mock_config.vad_enabled = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        # Should skip recording and go to PROCESSING
        self.assertEqual(mode.state, State.PROCESSING)

        # Should not initialize VAD or PyAudio
        mock_vad_class.assert_not_called()
        mock_pyaudio_class.assert_not_called()

    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.webrtcvad.Vad')
    def test_state_listening_handles_stream_error(self, mock_vad_class, mock_pyaudio_class):
        mock_vad = Mock()
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        mock_stream.read.side_effect = Exception("Stream error")

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        # Should return to IDLE on error
        self.assertEqual(mode.state, State.IDLE)

        # Should clean up stream
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.os.makedirs')
    @patch('common.wake_word.time.time')
    def test_state_listening_no_frames_returns_to_idle(self, mock_time, mock_makedirs,
                                                       mock_wave_open, mock_vad_class, mock_pyaudio_class):
        # Mock immediate timeout with no frames
        mock_time.side_effect = [0.0, 0.0, 31.0]

        mock_vad = Mock()
        mock_vad_class.return_value = mock_vad

        mock_stream = Mock()
        # Read fails immediately
        mock_stream.read.side_effect = Exception("No audio")

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pyaudio_class.return_value = mock_pa

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        # Should return to IDLE when no frames recorded
        self.assertEqual(mode.state, State.IDLE)

        # Should NOT write WAV file
        mock_wave_open.assert_not_called()

    @patch('common.wake_word.time.time')
    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.webrtcvad.Vad')
    @patch('common.wake_word.wave.open')
    @patch('common.wake_word.os.makedirs')
    def test_state_listening_handles_vad_processing_error(self, mock_makedirs,
                                                          mock_wave_open, mock_vad_class, mock_pyaudio_class,
                                                          mock_time):
        # Use realistic timeout with mocked time for deterministic behavior
        self.mock_config.vad_timeout = 30

        # Mock time to stay well below timeout (exit via stream error instead)
        # recording_start, 4 elapsed checks (loop iterations), final elapsed, filename timestamp
        mock_time.side_effect = [0.0, 0.0, 0.1, 0.2, 0.3, 0.3, 0.3]

        # Mock VAD that raises exception
        mock_vad = Mock()
        # Exception should be caught and recording continues
        mock_vad.is_speech.side_effect = Exception("VAD error")
        mock_vad_class.return_value = mock_vad

        # Mock PyAudio stream - succeed a few times then fail to exit loop
        mock_stream = Mock()
        read_count = [0]
        def mock_read(size, exception_on_overflow=False):
            read_count[0] += 1
            if read_count[0] <= 3:  # Return 3 frames successfully
                return b'\x00' * 960
            raise Exception("End recording")  # Then exit loop
        mock_stream.read = mock_read

        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream
        mock_pa.get_sample_size.return_value = 2
        mock_pyaudio_class.return_value = mock_pa

        # Mock wave file
        mock_wf = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.running = True
        mode.state = State.LISTENING

        mode._state_listening()

        # Should transition to PROCESSING (has frames saved)
        self.assertEqual(mode.state, State.PROCESSING)

        # Verify VAD was called and error was handled gracefully (3 times)
        self.assertEqual(mock_vad.is_speech.call_count, 3)

        # Should have saved audio file
        self.assertTrue(mock_wave_open.called)

        # Should clean up
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()


class TestWakeWordModeCleanup(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_cleanup_deletes_porcupine(self):
        mock_porcupine = Mock()

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = mock_porcupine
        mode.running = True

        mode._cleanup()

        mock_porcupine.delete.assert_called_once()
        self.assertIsNone(mode.porcupine)
        self.assertFalse(mode.running)

    def test_cleanup_handles_none_porcupine(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = None
        mode.running = True

        mode._cleanup()

        self.assertFalse(mode.running)


class TestWakeWordModeProcessing(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False
        self.mock_config.botname = "TestBot"
        self.mock_config.bot_voice = True

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_transcribes_and_generates_response(self, mock_exists):
        mock_exists.return_value = True

        # Mock AI methods
        self.mock_ai.transcribe_and_translate.return_value = "What's the weather?"
        mock_response = Mock()
        mock_response.content = "It's sunny today!"
        self.mock_ai.generate_response.return_value = mock_response
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts1.mp3", "/tmp/tts2.mp3"]

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Verify transcription was called with correct file path
        self.mock_ai.transcribe_and_translate.assert_called_once_with(audio_file_path="/tmp/recording.wav")

        # Verify response generation was called
        self.mock_ai.generate_response.assert_called_once_with("What's the weather?")

        # Verify TTS generation was called
        self.mock_ai.text_to_speech.assert_called_once_with("It's sunny today!")

        # Verify state transition
        self.assertEqual(mode.state, State.RESPONDING)

        # Verify data stored for responding state
        self.assertEqual(mode.response_text, "It's sunny today!")
        self.assertEqual(mode.tts_files, ["/tmp/tts1.mp3", "/tmp/tts2.mp3"])

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_uses_routing_callback_when_provided(self, mock_exists):
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "What's the weather?"
        self.mock_ai.define_route.return_value = {"route": "weather", "reason": "weather"}
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts1.mp3"]

        route_message = Mock(return_value="It's sunny today!")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=route_message)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        self.mock_ai.transcribe_and_translate.assert_called_once_with(audio_file_path="/tmp/recording.wav")
        self.mock_ai.define_route.assert_called_once_with("What's the weather?")
        route_message.assert_called_once()
        self.mock_ai.generate_response.assert_not_called()
        self.mock_ai.text_to_speech.assert_called_once_with("It's sunny today!")
        self.assertEqual(mode.response_text, "It's sunny today!")
        self.assertEqual(mode.state, State.RESPONDING)

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_sets_up_streaming_for_default_route_when_plugins_provided(self, mock_exists):
        mock_exists.return_value = True

        self.mock_config.stream_responses = True
        self.mock_config.stream_tts = True
        self.mock_config.stream_tts_boundary = "sentence"
        self.mock_config.stream_tts_first_chunk_target_s = 2
        self.mock_config.stream_tts_buffer_chunks = 1

        self.mock_ai.transcribe_and_translate.return_value = "Tell me something long"
        self.mock_ai.define_route.return_value = {"route": "default-route", "reason": "default"}

        route_message = Mock(return_value="non-streaming default")
        plugins = {"weather": Mock()}

        mode = WakeWordMode(
            self.mock_config,
            self.mock_ai,
            self.mock_audio,
            route_message=route_message,
            plugins=plugins,
        )
        mode._start_barge_in_detection = Mock(return_value=None)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Should set up streaming and skip route_message/generate_response/text_to_speech
        route_message.assert_not_called()
        self.mock_ai.generate_response.assert_not_called()
        self.mock_ai.text_to_speech.assert_not_called()

        self.assertEqual(mode.state, State.RESPONDING)
        self.assertEqual(mode.streaming_user_input, "Tell me something long")
        self.assertIsNotNone(mode.streaming_route)

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_without_bot_voice(self, mock_exists):
        mock_exists.return_value = True
        self.mock_config.bot_voice = False

        self.mock_ai.transcribe_and_translate.return_value = "Hello"
        mock_response = Mock()
        mock_response.content = "Hi there!"
        self.mock_ai.generate_response.return_value = mock_response

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # TTS should not be called when bot_voice is False
        self.mock_ai.text_to_speech.assert_not_called()

        # Should still transition to RESPONDING
        self.assertEqual(mode.state, State.RESPONDING)
        self.assertEqual(mode.response_text, "Hi there!")
        self.assertIsNone(mode.tts_files)

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_handles_missing_file(self, mock_exists):
        mock_exists.return_value = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.recorded_audio_path = "/tmp/missing.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Should return to IDLE when file is missing
        self.assertEqual(mode.state, State.IDLE)

        # AI methods should not be called
        self.mock_ai.transcribe_and_translate.assert_not_called()
        self.mock_ai.generate_response.assert_not_called()

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_processing_handles_transcription_error(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        # Mock transcription error
        self.mock_ai.transcribe_and_translate.side_effect = Exception("Transcription failed")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Should return to IDLE on error
        self.assertEqual(mode.state, State.IDLE)

        # Should have attempted cleanup of recording file
        mock_remove.assert_called_once_with("/tmp/recording.wav")

        # Response generation should not be called
        self.mock_ai.generate_response.assert_not_called()


class TestWakeWordModeResponding(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False
        self.mock_config.barge_in = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_streaming_uses_stream_response_deltas_and_audio_queue(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_print_deltas = False
        self.mock_config.stream_tts_boundary = "sentence"
        self.mock_config.stream_tts_first_chunk_target_s = 1
        self.mock_config.stream_tts_buffer_chunks = 1
        self.mock_config.stream_tts_tts_join_timeout_s = 1
        self.mock_config.stream_tts_player_join_timeout_s = 1

        # Streaming yields a short response and completes
        self.mock_ai.stream_response_deltas.return_value = iter(["Hello world. "])
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts1.mp3"]

        # Mock queue-based playback (do not consume queue in this test)
        self.mock_audio.play_audio_queue.return_value = (True, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.streaming_user_input = "Hi"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        self.mock_ai.stream_response_deltas.assert_called_once_with("Hi")
        self.mock_audio.play_audio_queue.assert_called()
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_plays_tts_and_cleans_up(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = ["/tmp/tts1.mp3", "/tmp/tts2.mp3"]
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.response_text = "Hello!"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Verify audio playback was called for each file (with new implementation)
        # play_audio_file is called instead of play_audio_files
        self.assertEqual(self.mock_audio.play_audio_file.call_count, 2)

        # Verify cleanup - both TTS files and recording file
        # With new implementation, we clean up TTS files as we go
        self.assertEqual(mock_remove.call_count, 3)  # 2 TTS + 1 recording

        # Verify state transition to IDLE
        self.assertEqual(mode.state, State.IDLE)

        # Verify data reset
        self.assertIsNone(mode.recorded_audio_path)
        self.assertIsNone(mode.response_text)
        self.assertIsNone(mode.tts_files)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_handles_playback_error(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        # Mock failed audio playback
        self.mock_audio.play_audio_file.side_effect = Exception("Playback error")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = ["/tmp/tts1.mp3"]
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should still clean up and transition to IDLE
        # With new implementation: TTS file + recording file
        self.assertEqual(mock_remove.call_count, 2)
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_handles_playback_error_in_debug_mode(self, mock_exists, mock_remove):
        """Test that failed files are preserved in debug mode."""
        self.mock_config.debug = True
        mock_exists.return_value = True

        # Mock failed audio playback
        self.mock_audio.play_audio_file.side_effect = Exception("Playback error")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = ["/tmp/tts1.mp3"]
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # In debug mode: failed file is preserved, only recording is cleaned up
        mock_remove.assert_called_once_with("/tmp/recording.wav")
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_without_tts_files(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = None  # No TTS files
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Audio playback should not be called
        self.mock_audio.play_audio_files.assert_not_called()

        # Should still clean up and transition to IDLE
        mock_remove.assert_called_once_with("/tmp/recording.wav")
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_handles_cleanup_error(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        # Mock cleanup error
        mock_remove.side_effect = Exception("Cleanup failed")

        # Mock play_audio_file to succeed (updated from play_audio_files)
        self.mock_audio.play_audio_file.return_value = None

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = ["/tmp/tts1.mp3"]
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should still transition to IDLE despite cleanup error
        self.assertEqual(mode.state, State.IDLE)


class TestBargeIn(unittest.TestCase):
    """Test barge-in functionality (interrupt TTS with wake word)."""
    
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.barge_in = True
        self.mock_config.wake_confirmation_beep = False
        self.mock_config.visual_state_indicator = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_porcupine = Mock()  # Mock porcupine for consistency
        
    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.threading.Thread')
    @patch('common.wake_word.threading.Event')
    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_starts_detection_thread(self, mock_remove, mock_exists, mock_event_class, mock_thread_class):
        """Test that barge-in detection thread is started when enabled."""
        mock_exists.return_value = False

        # Use distinct mocks for barge_in_event and barge_in_stop_flag
        mock_barge_in_event = Mock()
        mock_barge_in_event.is_set.return_value = False
        mock_barge_in_stop_flag = Mock()
        mock_barge_in_stop_flag.is_set.return_value = False
        mock_event_class.side_effect = [mock_barge_in_event, mock_barge_in_stop_flag]

        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread

        # Create porcupine mock for barge-in thread
        mock_porcupine = Mock()

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = mock_porcupine
        mode.tts_files = ["/tmp/test.mp3"]  # Need TTS files for barge-in to start
        mode.state = State.RESPONDING

        mode._state_responding()

        # Verify thread was created with daemon=True and started
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args.kwargs
        self.assertEqual(call_kwargs.get('daemon'), True)
        mock_thread.start.assert_called_once()
        
    @patch('common.wake_word.threading.Thread')
    @patch('common.wake_word.threading.Event')
    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_transitions_to_listening_on_wake_word(self, mock_remove, mock_exists, mock_event_class, mock_thread_class):
        """Test that barge-in transitions to LISTENING when wake word detected."""
        mock_exists.return_value = False

        # Use distinct mocks for barge_in_event and barge_in_stop_flag
        mock_barge_in_event = Mock()
        mock_barge_in_event.is_set.return_value = True  # Wake word detected
        mock_barge_in_stop_flag = Mock()
        mock_barge_in_stop_flag.is_set.return_value = False
        mock_event_class.side_effect = [mock_barge_in_event, mock_barge_in_stop_flag]

        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread

        mock_porcupine = Mock()

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = mock_porcupine
        mode.tts_files = ["/tmp/test.mp3"]  # Need TTS files for barge-in to work
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should transition to LISTENING, not IDLE
        self.assertEqual(mode.state, State.LISTENING)
    
    @patch('common.wake_word.threading.Thread')
    @patch('common.wake_word.threading.Event')
    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_disabled_transitions_to_idle(self, mock_remove, mock_exists, mock_event_class, mock_thread_class):
        """Test that without barge-in, state transitions to IDLE."""
        mock_exists.return_value = False
        
        # Disable barge-in
        self.mock_config.barge_in = False
        
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = []
        mode.state = State.RESPONDING
        
        mode._state_responding()
        
        # Should transition to IDLE (no thread started)
        self.assertEqual(mode.state, State.IDLE)
        mock_thread_class.assert_not_called()

    @patch('common.wake_word.threading.Thread')
    @patch('common.wake_word.threading.Event')
    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_stops_playback_on_wake_word(self, mock_remove, mock_exists, mock_event_class, mock_thread_class):
        """Test that barge-in passes stop_event to play_audio_file for mid-playback interruption."""
        mock_exists.return_value = False

        # Simulate wake word detected after first file plays
        # Create separate mocks for barge_in_event and stop_flag
        mock_barge_in_event = Mock()
        mock_stop_flag = Mock()

        # Track which Event() call this is
        event_call_count = [0]
        def event_factory():
            event_call_count[0] += 1
            if event_call_count[0] == 1:
                return mock_barge_in_event  # First Event() is barge_in_event
            else:
                return mock_stop_flag  # Second Event() is stop_flag

        mock_event_class.side_effect = event_factory

        # Make barge_in_event.is_set() return True after first playback
        playback_count = [0]
        def is_set_after_first_playback():
            # Check if we've played at least one file
            return playback_count[0] > 0

        mock_barge_in_event.is_set.side_effect = is_set_after_first_playback
        mock_stop_flag.is_set.return_value = False

        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread

        mock_porcupine = Mock()

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = mock_porcupine
        mode.tts_files = ["/tmp/tts1.mp3", "/tmp/tts2.mp3"]
        mode.state = State.RESPONDING

        # Mock play_audio_file to track playback and simulate barge-in
        def play_audio_side_effect(file_path, stop_event=None):
            playback_count[0] += 1
            return None

        self.mock_audio.play_audio_file.side_effect = play_audio_side_effect

        mode._state_responding()

        # Verify play_audio_file was called with stop_event parameter
        # (New implementation: interruption happens inside play_audio_file via stop_event)
        self.mock_audio.play_audio_file.assert_called()
        call_args = self.mock_audio.play_audio_file.call_args
        # Check that a stop_event was passed (not None)
        self.assertIn('stop_event', call_args.kwargs)
        self.assertIsNotNone(call_args.kwargs['stop_event'])
        # Verify it's the barge_in_event object
        self.assertIs(call_args.kwargs['stop_event'], mock_barge_in_event)

        # Should transition to LISTENING (barge-in triggered)
        self.assertEqual(mode.state, State.LISTENING)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_during_processing(self, mock_remove, mock_exists):
        """Test immediate barge-in handler works correctly."""
        mock_exists.return_value = True
        self.mock_config.wake_confirmation_beep = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.recorded_audio_path = "/tmp/test.mp3"
        mode.confirmation_beep_path = "/tmp/beep.mp3"
        mode.state = State.PROCESSING

        # Set up mock barge-in thread and flags
        mock_barge_in_thread = Mock()
        mock_stop_flag = Mock()
        mode.barge_in_stop_flag = mock_stop_flag
        mode.barge_in_event = Mock()

        # Call the immediate barge-in handler
        mode._handle_immediate_barge_in(mock_barge_in_thread)

        # Verify beep was played
        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/beep.mp3")

        # Verify barge-in thread was signaled to stop; thread lifecycle is handled by the implementation
        mock_stop_flag.set.assert_called_once()

        # Verify cleanup
        mock_remove.assert_called_once_with("/tmp/test.mp3")
        self.assertIsNone(mode.recorded_audio_path)
        self.assertIsNone(mode.barge_in_event)
        self.assertIsNone(mode.barge_in_stop_flag)

        # Should transition to LISTENING (immediate response)
        self.assertEqual(mode.state, State.LISTENING)

    def test_run_with_barge_in_polling_returns_early_on_interrupt(self):
        """Test that _run_with_barge_in_polling returns early when barge-in detected."""
        mode = WakeWordMode.__new__(WakeWordMode)
        mode.config = self.mock_config
        mode.config.barge_in = True
        mode.barge_in_event = threading.Event()

        # Track operation execution
        operation_started = threading.Event()
        operation_completed = threading.Event()

        def slow_operation():
            operation_started.set()
            # Wait for a bit to simulate slow API call (kept short to minimize test time)
            time.sleep(0.3)
            operation_completed.set()
            return "result"

        # Start polling in a thread so we can trigger barge-in
        result_holder = [None]

        def run_polling():
            result_holder[0] = mode._run_with_barge_in_polling(slow_operation, "test")

        polling_thread = threading.Thread(target=run_polling)
        polling_thread.start()

        # Wait for operation to start
        operation_started.wait(timeout=1.0)

        # Trigger barge-in
        mode.barge_in_event.set()

        # Polling should return quickly (use generous timeout for CI stability)
        polling_thread.join(timeout=0.5)
        self.assertFalse(polling_thread.is_alive(), "Polling should return quickly on barge-in")

        # Should return (False, None) indicating interrupted
        completed, result = result_holder[0]
        self.assertFalse(completed)
        self.assertIsNone(result)

        # Operation may still be running (daemon thread) - that's expected
        # Wait for it to complete to clean up
        operation_completed.wait(timeout=1.0)


if __name__ == '__main__':
    unittest.main()
