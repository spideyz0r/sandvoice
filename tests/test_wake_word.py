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

    def test_audio_lock_defaults_to_none(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        self.assertIsNone(mode._audio_lock)

    def test_audio_lock_stored_when_provided(self):
        import threading
        lock = threading.Lock()
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, audio_lock=lock)
        self.assertIs(mode._audio_lock, lock)


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
        self.mock_config.bot_voice = True
        self.mock_config.stream_responses = True
        self.mock_config.stream_tts = True
        self.mock_config.vad_enabled = True
        self.mock_config.barge_in = True

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

    def test_initialize_raises_when_bot_voice_disabled(self):
        self.mock_config.bot_voice = False
        self.mock_config.stream_responses = True
        self.mock_config.stream_tts = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("bot_voice", str(context.exception))

    def test_initialize_raises_when_stream_responses_disabled(self):
        self.mock_config.bot_voice = True
        self.mock_config.stream_responses = False
        self.mock_config.stream_tts = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("stream_responses", str(context.exception))

    def test_initialize_raises_when_stream_tts_disabled(self):
        self.mock_config.bot_voice = True
        self.mock_config.stream_responses = True
        self.mock_config.stream_tts = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("stream_tts", str(context.exception))

    def test_initialize_raises_when_barge_in_disabled(self):
        self.mock_config.bot_voice = True
        self.mock_config.stream_responses = True
        self.mock_config.stream_tts = True
        self.mock_config.barge_in = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("barge_in", str(context.exception))

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

    def test_initialize_raises_when_vad_disabled(self):
        self.mock_config.vad_enabled = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("VAD", str(context.exception))
        self.assertIn("vad_enabled", str(context.exception))


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
        self.mock_config.vad_enabled = True
        self.mock_config.bot_voice = True
        self.mock_config.stream_responses = True
        self.mock_config.stream_tts = True
        self.mock_config.barge_in = True

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
        self.mock_config.rate = 16000
        self.mock_config.channels = 1
        self.mock_config.vad_aggressiveness = 3
        self.mock_config.vad_silence_duration = 1.5
        self.mock_config.vad_frame_duration = 30
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
    def test_state_processing_transcribes_and_sets_up_streaming(self, mock_exists):
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "What's the weather?"

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Verify transcription was called with correct file path
        self.mock_ai.transcribe_and_translate.assert_called_once_with(audio_file_path="/tmp/recording.wav")

        # No route_message → streaming path; generate_response is never called directly
        self.mock_ai.generate_response.assert_not_called()
        self.assertEqual(mode.state, State.RESPONDING)
        self.assertEqual(mode.streaming_user_input, "What's the weather?")

        # TTS is no longer pre-generated in _state_processing
        self.mock_ai.text_to_speech.assert_not_called()

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_uses_routing_callback_when_provided(self, mock_exists):
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "What's the weather?"
        self.mock_ai.define_route.return_value = {"route": "weather", "reason": "weather"}

        route_message = Mock(return_value="It's sunny today!")
        plugins = {"weather": Mock()}

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=route_message, plugins=plugins)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        self.mock_ai.transcribe_and_translate.assert_called_once_with(audio_file_path="/tmp/recording.wav")
        self.mock_ai.define_route.assert_called_once_with("What's the weather?")
        route_message.assert_called_once()
        self.mock_ai.generate_response.assert_not_called()
        # TTS no longer pre-generated in _state_processing
        self.mock_ai.text_to_speech.assert_not_called()
        self.assertEqual(mode.response_text, "It's sunny today!")
        # streaming_response_text set so RESPONDING can speak it via TTS worker
        self.assertEqual(mode.streaming_response_text, "It's sunny today!")
        self.assertEqual(mode.state, State.RESPONDING)

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_sets_up_streaming_for_default_route_when_plugins_provided(self, mock_exists):
        mock_exists.return_value = True

        self.mock_config.stream_responses = "enabled"
        self.mock_config.stream_tts = "enabled"
        self.mock_config.stream_tts_boundary = "sentence"

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
    def test_state_processing_plugin_response_never_pre_generates_tts(self, mock_exists):
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "Hello"
        self.mock_ai.define_route.return_value = {"route": "echo", "reason": "echo"}

        route_message = Mock(return_value="Hi there!")
        plugins = {"echo": Mock()}

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=route_message, plugins=plugins)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # TTS is never pre-generated in _state_processing (streaming handles it in RESPONDING)
        self.mock_ai.text_to_speech.assert_not_called()

        self.assertEqual(mode.state, State.RESPONDING)
        self.assertEqual(mode.response_text, "Hi there!")

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
        self.mock_config.barge_in = True
        self.mock_config.tmp_files_path = "/tmp/test/"
        self.mock_config.stream_tts_first_chunk_target_s = 6

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_streaming_uses_stream_response_deltas_and_audio_queue(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

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
    def test_state_responding_streaming_continues_collecting_deltas_on_playback_failure(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

        consumed = []

        def deltas():
            for p in ["A", "B", "C"]:
                consumed.append(p)
                yield p

        self.mock_ai.stream_response_deltas.side_effect = lambda _ui: deltas()

        # Player fails immediately -> interrupt_event set.
        self.mock_audio.play_audio_queue.return_value = (False, "/tmp/fail.mp3", Exception("boom"))

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.streaming_user_input = "Hi"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        self.assertEqual(consumed, ["A", "B", "C"])

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_streams_and_cleans_up(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

        self.mock_ai.stream_response_deltas.return_value = iter(["Hello!"])
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts1.mp3"]
        self.mock_audio.play_audio_queue.return_value = (True, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.streaming_user_input = "Hi"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        self.mock_ai.stream_response_deltas.assert_called_once_with("Hi")
        self.mock_audio.play_audio_queue.assert_called()
        self.assertEqual(mode.state, State.IDLE)
        self.assertIsNone(mode.recorded_audio_path)
        self.assertIsNone(mode.response_text)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_handles_playback_error(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

        self.mock_ai.stream_response_deltas.return_value = iter(["Hello!"])
        self.mock_audio.play_audio_queue.return_value = (False, "/tmp/tts1.mp3", Exception("boom"))

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.streaming_user_input = "Hi"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should still clean up recording and transition to IDLE
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_no_streaming_input_goes_to_idle(self, mock_exists, mock_remove):
        """No streaming_user_input → nothing to play → clean up and go to IDLE."""
        mock_exists.return_value = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.streaming_user_input = None
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        self.mock_audio.play_audio_queue.assert_not_called()
        mock_remove.assert_called_once_with("/tmp/recording.wav")
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_handles_cleanup_error(self, mock_exists, mock_remove):
        mock_exists.return_value = True
        mock_remove.side_effect = Exception("Cleanup failed")

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"
        self.mock_ai.stream_response_deltas.return_value = iter([])
        self.mock_audio.play_audio_queue.return_value = (True, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.streaming_user_input = "Hey"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should still transition to IDLE despite cleanup error
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_speaks_plugin_response_via_tts(self, mock_exists, mock_remove):
        """Plugin response (streaming_response_text set) is fed directly to streaming TTS."""
        mock_exists.return_value = False

        tts_file = "/tmp/tts-plugin.mp3"
        self.mock_ai.text_to_speech.return_value = [tts_file]
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.streaming_response_text = "Plugin said this."
        mode.streaming_user_input = None
        mode.state = State.RESPONDING

        mode._state_responding()

        # TTS worker should have been called with the plugin response text
        self.mock_ai.text_to_speech.assert_called_once_with("Plugin said this.")
        self.mock_audio.play_audio_queue.assert_called()
        self.assertEqual(mode.state, State.IDLE)
        # streaming_response_text cleared after responding
        self.assertIsNone(mode.streaming_response_text)


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
        """Test that barge-in detection thread is started when enabled (streaming path)."""
        mock_exists.return_value = False

        # __init__ does NOT call _initialize(), so no Events consumed during construction.
        # _start_barge_in_detection() consumes 2, _respond_streaming() consumes 2 → 4 total.
        def _make_event(is_set_val=False):
            e = Mock()
            e.is_set.return_value = is_set_val
            return e

        mock_event_class.side_effect = [_make_event() for _ in range(4)]

        mock_thread = Mock()
        mock_thread.is_alive.return_value = False
        mock_thread_class.return_value = mock_thread

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"
        self.mock_ai.stream_response_deltas.return_value = iter([])
        self.mock_audio.play_audio_queue.return_value = (True, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = Mock()
        mode.streaming_user_input = "Hey"
        mode.state = State.RESPONDING

        mode._state_responding()

        # The streaming path creates threads (tts_worker + player_worker)
        self.assertTrue(mock_thread_class.called)
        mock_thread.start.assert_called()
        # _start_barge_in_detection must also create a thread targeting _listen_for_barge_in
        thread_targets = [call.kwargs.get('target') for call in mock_thread_class.call_args_list]
        self.assertTrue(
            any(getattr(t, '__name__', '') == '_listen_for_barge_in' for t in thread_targets),
            "Expected _listen_for_barge_in to be registered as a thread target"
        )

    @patch('common.wake_word.threading.Thread')
    @patch('common.wake_word.threading.Event')
    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_transitions_to_listening_on_wake_word(self, mock_remove, mock_exists, mock_event_class, mock_thread_class):
        """Test that barge-in transitions to LISTENING when wake word detected."""
        mock_exists.return_value = False

        # __init__ does NOT call _initialize() — only run() does, so no Events consumed
        # during construction.  _start_barge_in_detection() consumes indices 0 and 1
        # (barge_in_event and barge_in_stop_flag), then _respond_streaming() consumes
        # indices 2 and 3.  Index 0 must have is_set=True to trigger LISTENING.
        def _make_event(is_set_val=False):
            e = Mock()
            e.is_set.return_value = is_set_val
            return e

        mock_event_class.side_effect = [
            _make_event(True),    # _start_barge_in_detection barge_in_event (is_set=True → LISTENING)
            _make_event(),        # _start_barge_in_detection barge_in_stop_flag
            _make_event(),        # _respond_streaming interrupt_event
            _make_event(),        # _respond_streaming production_failed_event
        ]

        mock_thread = Mock()
        mock_thread.is_alive.return_value = False
        mock_thread_class.return_value = mock_thread

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"
        self.mock_ai.stream_response_deltas.return_value = iter([])
        self.mock_audio.play_audio_queue.return_value = (True, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = Mock()
        mode.streaming_user_input = "Hey"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should transition to LISTENING, not IDLE
        self.assertEqual(mode.state, State.LISTENING)
    
    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_stops_playback_on_wake_word(self, mock_remove, mock_exists):
        """Test that streaming path passes stop_event (composite) to play_audio_queue."""
        mock_exists.return_value = False

        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"
        self.mock_ai.stream_response_deltas.return_value = iter([])

        # Simulate player interrupted by barge-in (returns False / no error)
        self.mock_audio.play_audio_queue.return_value = (False, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.porcupine = Mock()
        # Mark barge-in thread as already running so _start_barge_in_detection is
        # skipped and self.barge_in_event is not overwritten with a new real Event.
        mock_barge_in_thread = Mock()
        mock_barge_in_thread.is_alive.return_value = True
        mode.barge_in_thread = mock_barge_in_thread
        mode.barge_in_event = Mock()
        mode.barge_in_event.is_set.return_value = True
        mode.streaming_user_input = "Hey"
        mode.state = State.RESPONDING

        mode._state_responding()

        # play_audio_queue should have been called with a stop_event
        self.mock_audio.play_audio_queue.assert_called()
        call_kwargs = self.mock_audio.play_audio_queue.call_args.kwargs
        self.assertIn('stop_event', call_kwargs)
        self.assertIsNotNone(call_kwargs['stop_event'])

        # Should transition to LISTENING (barge-in event is set)
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
