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

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_handles_transcription_error(self, mock_exists):
        mock_exists.return_value = True

        # Mock transcription error
        self.mock_ai.transcribe_and_translate.side_effect = Exception("Transcription failed")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Should return to IDLE on error
        self.assertEqual(mode.state, State.IDLE)

        # Response generation should not be called
        self.mock_ai.generate_response.assert_not_called()


class TestWakeWordModeResponding(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_plays_tts_and_cleans_up(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        # Mock successful audio playback
        self.mock_audio.play_audio_files.return_value = (True, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = ["/tmp/tts1.mp3", "/tmp/tts2.mp3"]
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.response_text = "Hello!"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Verify audio playback was called
        self.mock_audio.play_audio_files.assert_called_once_with(["/tmp/tts1.mp3", "/tmp/tts2.mp3"])

        # Verify cleanup
        mock_remove.assert_called_once_with("/tmp/recording.wav")

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
        self.mock_audio.play_audio_files.return_value = (False, "/tmp/tts1.mp3", "Playback error")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = ["/tmp/tts1.mp3"]
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should still clean up and transition to IDLE
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

        self.mock_audio.play_audio_files.return_value = (True, None, None)

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio)
        mode.tts_files = ["/tmp/tts1.mp3"]
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should still transition to IDLE despite cleanup error
        self.assertEqual(mode.state, State.IDLE)


if __name__ == '__main__':
    unittest.main()
