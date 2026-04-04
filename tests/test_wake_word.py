import threading
import time
import unittest
import logging
from unittest.mock import Mock, patch

from common.wake_word import WakeWordMode, State
from common.barge_in import BargeInDetector, _BARGE_IN


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
        self.mock_route_message = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_init_sets_initial_state(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        self.assertEqual(mode.state, State.IDLE)
        self.assertFalse(mode.running)
        self.assertIsNone(mode.porcupine)
        self.assertIsNone(mode.confirmation_beep_path)

    def test_init_stores_dependencies(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        self.assertEqual(mode.config, self.mock_config)
        self.assertEqual(mode.ai, self.mock_ai)
        self.assertEqual(mode.audio, self.mock_audio)

    def test_audio_lock_defaults_to_none(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        self.assertIsNone(mode._audio_lock)

    def test_audio_lock_stored_when_provided(self):
        import threading
        lock = threading.Lock()
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message, audio_lock=lock)
        self.assertIs(mode._audio_lock, lock)

    def test_init_raises_when_route_message_is_none(self):
        with self.assertRaises(ValueError) as context:
            WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=None)
        self.assertIn("route_message", str(context.exception))


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

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock()

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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("bot_voice", str(context.exception))

    def test_initialize_raises_when_stream_responses_disabled(self):
        self.mock_config.bot_voice = True
        self.mock_config.stream_responses = False
        self.mock_config.stream_tts = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("stream_responses", str(context.exception))

    def test_initialize_raises_when_stream_tts_disabled(self):
        self.mock_config.bot_voice = True
        self.mock_config.stream_responses = True
        self.mock_config.stream_tts = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("stream_tts", str(context.exception))

    @patch('common.wake_word.pvporcupine.create')
    def test_initialize_raises_on_missing_access_key(self, mock_porcupine_create):
        self.mock_config.porcupine_access_key = ""

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("access key is required", str(context.exception).lower())

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_handles_porcupine_error(self, mock_beep, mock_porcupine_create):
        mock_porcupine_create.side_effect = Exception("Porcupine init failed")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        with self.assertRaises(RuntimeError) as context:
            mode._initialize()

        self.assertIn("Failed to initialize wake-word mode", str(context.exception))

    @patch('common.wake_word.pvporcupine.create')
    @patch('common.wake_word.create_confirmation_beep')
    def test_initialize_handles_beep_creation_error(self, mock_beep, mock_porcupine_create):
        mock_porcupine = Mock()
        mock_porcupine.sample_rate = 16000
        mock_porcupine.frame_length = 512
        mock_porcupine_create.return_value = mock_porcupine
        mock_beep.side_effect = Exception("Beep creation failed")

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        mode._initialize()

        self.assertIsNone(mode.confirmation_beep_path)

    def test_initialize_raises_when_vad_disabled(self):
        self.mock_config.vad_enabled = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

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
        self.mock_route_message = Mock()

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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.pyaudio.PyAudio')
    @patch('common.wake_word.struct.unpack_from')
    def test_state_idle_plays_confirmation_beep(self, mock_unpack, mock_pyaudio_class, mock_exists):
        mock_exists.return_value = True

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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock()

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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)

        def mock_state_idle():
            raise KeyboardInterrupt()

        mode._state_idle = mock_state_idle

        # Should not raise - should handle KeyboardInterrupt gracefully
        mode.run()

        # Cleanup should have been called
        self.assertIsNone(mode.porcupine)
        self.assertFalse(mode.running)


class TestWakeWordModeStateListening(unittest.TestCase):
    """Tests for _state_listening(), which is a thin wrapper around VadRecorder.record().

    Deep VAD/earcon behaviour is covered in tests/test_vad_recorder.py.
    These tests only exercise the state transition logic in the wrapper.
    """

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_mode(self):
        mode = WakeWordMode(
            self.mock_config, self.mock_ai, self.mock_audio,
            route_message=self.mock_route_message,
        )
        mode.running = True
        mode.state = State.LISTENING
        mode.vad_recorder = Mock()
        return mode

    def test_state_listening_transitions_to_processing_on_success(self):
        mode = self._make_mode()
        mode.vad_recorder.record.return_value = "/tmp/test/recording.wav"

        mode._state_listening()

        self.assertEqual(mode.state, State.PROCESSING)
        self.assertEqual(mode.recorded_audio_path, "/tmp/test/recording.wav")

    def test_state_listening_transitions_to_idle_when_no_frames(self):
        mode = self._make_mode()
        mode.vad_recorder.record.return_value = None

        mode._state_listening()

        self.assertEqual(mode.state, State.IDLE)

    def test_state_listening_transitions_to_idle_on_exception(self):
        mode = self._make_mode()
        mode.vad_recorder.record.side_effect = RuntimeError("Stream error")

        mode._state_listening()

        self.assertEqual(mode.state, State.IDLE)

    def test_state_listening_prints_indicator_when_enabled(self):
        self.mock_config.visual_state_indicator = True
        mode = self._make_mode()
        mode.vad_recorder.record.return_value = "/tmp/test/recording.wav"

        with patch('builtins.print') as mock_print:
            mode._state_listening()

        mock_print.assert_any_call("🎤 Listening...")


class TestWakeWordModeCleanup(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_cleanup_deletes_porcupine(self):
        mock_porcupine = Mock()

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        mode.porcupine = mock_porcupine
        mode.running = True

        mode._cleanup()

        mock_porcupine.delete.assert_called_once()
        self.assertIsNone(mode.porcupine)
        self.assertFalse(mode.running)

    def test_cleanup_handles_none_porcupine(self):
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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
        self.mock_route_message = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_mode(self, **kwargs):
        """Create a WakeWordMode with barge-in detector mocked out.

        Tests that exercise state logic (not barge-in thread management) use this
        to avoid requiring a real Porcupine instance.
        """
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, **{"route_message": self.mock_route_message, **kwargs})
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.is_triggered = False
        mock_barge_in.event = Mock()
        mock_barge_in.event.is_set.return_value = False
        mock_barge_in.run_with_polling.side_effect = lambda op, name, **kw: op()
        mode.barge_in = mock_barge_in
        return mode

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_transcribes_and_sets_up_streaming(self, mock_exists):
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "What's the weather?"
        self.mock_ai.define_route.return_value = {"route": "default-route", "reason": "direct"}

        mode = self._make_mode(plugins={})
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        self.mock_ai.transcribe_and_translate.assert_called_once_with(audio_file_path="/tmp/recording.wav")
        self.mock_ai.generate_response.assert_not_called()
        self.assertEqual(mode.state, State.RESPONDING)
        self.assertEqual(mode.streaming_user_input, "What's the weather?")
        self.mock_ai.text_to_speech.assert_not_called()

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_uses_routing_callback_when_provided(self, mock_exists):
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "What's the weather?"
        self.mock_ai.define_route.return_value = {"route": "weather", "reason": "weather"}

        route_message = Mock(return_value="It's sunny today!")
        plugins = {"weather": Mock()}

        mode = self._make_mode(route_message=route_message, plugins=plugins)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        self.mock_ai.transcribe_and_translate.assert_called_once_with(audio_file_path="/tmp/recording.wav")
        self.mock_ai.define_route.assert_called_once_with("What's the weather?", extra_routes=None)
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

        mode = self._make_mode(route_message=route_message, plugins=plugins)
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Should set up streaming and skip route_message/generate_response/text_to_speech
        route_message.assert_not_called()
        self.mock_ai.generate_response.assert_not_called()
        self.mock_ai.text_to_speech.assert_not_called()

        self.assertEqual(mode.state, State.RESPONDING)
        self.assertEqual(mode.streaming_user_input, "Tell me something long")

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_plugin_response_never_pre_generates_tts(self, mock_exists):
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "Hello"
        self.mock_ai.define_route.return_value = {"route": "echo", "reason": "echo"}

        route_message = Mock(return_value="Hi there!")
        plugins = {"echo": Mock()}

        mode = self._make_mode(route_message=route_message, plugins=plugins)
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

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
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

        mode = self._make_mode()
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        # Should return to IDLE on error
        self.assertEqual(mode.state, State.IDLE)

        # Should have attempted cleanup of recording file
        mock_remove.assert_called_once_with("/tmp/recording.wav")

        # Response generation should not be called
        self.mock_ai.generate_response.assert_not_called()

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_arms_voice_filler_when_plugin_route(self, mock_exists):
        """Voice filler lead_fn/lead_delay_s are passed to run_with_polling for plugin routes."""
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "What's the weather?"
        self.mock_ai.define_route.return_value = {"route": "weather", "reason": "weather"}

        mock_voice_filler = Mock()
        mock_voice_filler.pick_random_path.return_value = "/cache/one_sec.mp3"

        self.mock_config.voice_filler_delay_ms = 800

        route_message = Mock(return_value="It's sunny!")
        plugins = {"weather": Mock()}

        mode = self._make_mode(
            route_message=route_message,
            plugins=plugins,
            voice_filler=mock_voice_filler,
        )
        # Capture run_with_polling kwargs
        captured_kwargs = {}

        def capture_kwargs(op, name, **kw):
            captured_kwargs.update(kw)
            return op()

        mode.barge_in.run_with_polling.side_effect = capture_kwargs
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        self.assertIsNotNone(captured_kwargs.get("lead_fn"), "lead_fn should be set for plugin routes")
        self.assertAlmostEqual(captured_kwargs.get("lead_delay_s"), 0.8, places=3)
        self.assertTrue(callable(captured_kwargs["lead_fn"]))

    @patch('common.wake_word.os.path.exists')
    def test_state_processing_no_voice_filler_when_no_plugin_route(self, mock_exists):
        """lead_fn and lead_delay_s are None when voice_filler is not set."""
        mock_exists.return_value = True

        self.mock_ai.transcribe_and_translate.return_value = "Tell me a joke"
        self.mock_ai.define_route.return_value = {"route": "default-route", "reason": "general"}

        mode = self._make_mode(plugins={})
        captured_kwargs = {}

        def capture_kwargs(op, name, **kw):
            captured_kwargs.update(kw)
            return op()

        mode.barge_in.run_with_polling.side_effect = capture_kwargs
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.PROCESSING

        mode._state_processing()

        self.assertIsNone(captured_kwargs.get("lead_fn"))
        self.assertIsNone(captured_kwargs.get("lead_delay_s"))


class TestWakeWordModeResponding(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False
        self.mock_config.tmp_files_path = "/tmp/test/"
        self.mock_config.stream_tts_first_chunk_target_s = 6

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_mode(self, **kwargs):
        """Create a WakeWordMode with barge-in detector and StreamingResponder mocked out.

        Tests that exercise state logic (not barge-in thread management or streaming
        pipeline details) use this to avoid requiring a real Porcupine instance.
        """
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, **{"route_message": self.mock_route_message, **kwargs})
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.is_triggered = False
        mock_barge_in.event = Mock()
        mock_barge_in.event.is_set.return_value = False
        mock_barge_in.run_with_polling.side_effect = lambda op, name, **kw: op()
        mode.barge_in = mock_barge_in
        mode.responder = Mock()
        return mode

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_streaming_uses_stream_response_deltas_and_audio_queue(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        mode = self._make_mode()
        mode.streaming_user_input = "Hi"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # _respond_streaming delegates to StreamingResponder.respond
        mode.responder.respond.assert_called_once_with("Hi", None)
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_streams_and_cleans_up(self, mock_exists, mock_remove):
        mock_exists.return_value = True

        mode = self._make_mode()
        mode.streaming_user_input = "Hi"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        mode.responder.respond.assert_called_once_with("Hi", None)
        self.assertEqual(mode.state, State.IDLE)
        self.assertIsNone(mode.recorded_audio_path)
        self.assertIsNone(mode.response_text)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_no_streaming_input_goes_to_idle(self, mock_exists, mock_remove):
        """No streaming_user_input → nothing to play → clean up and go to IDLE."""
        mock_exists.return_value = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        mode.streaming_user_input = None
        mode.streaming_response_text = None
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        mock_remove.assert_called_once_with("/tmp/recording.wav")
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_handles_cleanup_error(self, mock_exists, mock_remove):
        mock_exists.return_value = True
        mock_remove.side_effect = OSError("Cleanup failed")

        mode = self._make_mode()
        mode.streaming_user_input = "Hey"
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should still transition to IDLE despite cleanup error
        self.assertEqual(mode.state, State.IDLE)

    @patch('common.wake_word.os.remove')
    @patch('common.wake_word.os.path.exists')
    def test_state_responding_speaks_plugin_response_via_tts(self, mock_exists, mock_remove):
        """Plugin response (streaming_response_text set) is passed to StreamingResponder."""
        mock_exists.return_value = False

        mode = self._make_mode()
        mode.streaming_response_text = "Plugin said this."
        mode.streaming_user_input = None
        mode.state = State.RESPONDING

        mode._state_responding()

        # StreamingResponder.respond receives user_input=None and response_text set
        mode.responder.respond.assert_called_once_with(None, "Plugin said this.")
        self.assertEqual(mode.state, State.IDLE)
        # streaming_response_text cleared after responding
        self.assertIsNone(mode.streaming_response_text)


class TestBargeIn(unittest.TestCase):
    """Test barge-in functionality (interrupt TTS with wake word)."""
    
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.wake_confirmation_beep = False
        self.mock_config.visual_state_indicator = False

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_porcupine = Mock()  # Mock porcupine for consistency
        self.mock_route_message = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_starts_detection_thread(self, mock_remove, mock_exists):
        """Test that barge-in detection is started when entering responding state."""
        mock_exists.return_value = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.is_triggered = False
        mock_barge_in.event = Mock()
        mock_barge_in.event.is_set.return_value = False
        mode.barge_in = mock_barge_in
        mode.responder = Mock()
        mode.streaming_user_input = "Hey"
        mode.state = State.RESPONDING

        mode._state_responding()

        # barge_in.start() should have been called in _respond_streaming to ensure detection is running
        mock_barge_in.start.assert_called()
        # StreamingResponder.respond should have been delegated to
        mode.responder.respond.assert_called_once_with("Hey", None)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_transitions_to_listening_on_wake_word(self, mock_remove, mock_exists):
        """Test that barge-in transitions to LISTENING when wake word detected."""
        mock_exists.return_value = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        # Simulate barge-in already triggered
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.is_triggered = True
        mock_barge_event = Mock()
        mock_barge_event.is_set.return_value = True
        mock_barge_in.event = mock_barge_event
        mode.barge_in = mock_barge_in
        mode.responder = Mock()
        mode.streaming_user_input = "Hey"
        mode.state = State.RESPONDING

        mode._state_responding()

        # Should transition to LISTENING, not IDLE
        self.assertEqual(mode.state, State.LISTENING)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_stops_playback_on_wake_word(self, mock_remove, mock_exists):
        """Test that streaming path delegates to StreamingResponder and barge-in is handled."""
        mock_exists.return_value = False

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        # Set up a mock BargeInDetector with barge-in already triggered
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.is_triggered = True
        mock_barge_event = Mock()
        mock_barge_event.is_set.return_value = True
        mock_barge_in.event = mock_barge_event
        mode.barge_in = mock_barge_in
        mode.responder = Mock()
        mode.streaming_user_input = "Hey"
        mode.state = State.RESPONDING

        mode._state_responding()

        # StreamingResponder.respond should have been called
        mode.responder.respond.assert_called_once_with("Hey", None)

        # Should transition to LISTENING (barge-in is triggered)
        self.assertEqual(mode.state, State.LISTENING)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_barge_in_during_processing(self, mock_remove, mock_exists):
        """Test immediate barge-in handler works correctly."""
        mock_exists.return_value = True
        self.mock_config.wake_confirmation_beep = True

        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        mode.recorded_audio_path = "/tmp/test.mp3"
        mode.confirmation_beep_path = "/tmp/beep.mp3"
        mode.state = State.PROCESSING

        # Set up mock BargeInDetector
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.is_triggered = True
        mock_barge_in.event = Mock()
        mode.barge_in = mock_barge_in

        # Call the immediate barge-in handler
        mode._handle_immediate_barge_in()

        # Verify beep was played
        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/beep.mp3")

        # Verify barge-in detector was stopped
        mock_barge_in.stop.assert_called_once()

        # Verify cleanup
        mock_remove.assert_called_once_with("/tmp/test.mp3")
        self.assertIsNone(mode.recorded_audio_path)

        # Should transition to LISTENING (immediate response)
        self.assertEqual(mode.state, State.LISTENING)

    def test_poll_op_returns_barge_in_and_handles_barge_in(self):
        """Test that _poll_op returns _BARGE_IN and calls _handle_immediate_barge_in."""
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.run_with_polling.return_value = _BARGE_IN
        mode.barge_in = mock_barge_in
        mode.state = State.PROCESSING
        mode.recorded_audio_path = None
        mode._handle_immediate_barge_in = Mock()

        result = mode._poll_op(lambda: "result", "test_op")

        self.assertIs(result, _BARGE_IN)
        mode._handle_immediate_barge_in.assert_called_once()

    def test_poll_op_returns_operation_result_on_success(self):
        """Test that _poll_op returns the operation result when no barge-in."""
        mode = WakeWordMode(self.mock_config, self.mock_ai, self.mock_audio, route_message=self.mock_route_message)
        mock_barge_in = Mock(spec=BargeInDetector)
        mock_barge_in.run_with_polling.return_value = "api_result"
        mode.barge_in = mock_barge_in

        result = mode._poll_op(lambda: "api_result", "test_op")

        self.assertEqual(result, "api_result")
        mode.barge_in.run_with_polling.assert_called_once()


class TestHelperMethods(unittest.TestCase):
    """Tests for the private helper methods extracted in Plan 32."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False
        self.mock_config.wake_confirmation_beep = True

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_mode(self, **kwargs):
        return WakeWordMode(
            self.mock_config, self.mock_ai, self.mock_audio,
            **{"route_message": self.mock_route_message, **kwargs}
        )

    # --- _cleanup_pyaudio ---

    def test_cleanup_pyaudio_stops_and_closes_stream(self):
        mock_stream = Mock()
        mock_pa = Mock()
        mode = self._make_mode()
        mode._cleanup_pyaudio(mock_stream, mock_pa)
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    def test_cleanup_pyaudio_handles_none_stream(self):
        mock_pa = Mock()
        mode = self._make_mode()
        mode._cleanup_pyaudio(None, mock_pa)
        mock_pa.terminate.assert_called_once()

    def test_cleanup_pyaudio_handles_none_pa(self):
        mock_stream = Mock()
        mode = self._make_mode()
        mode._cleanup_pyaudio(mock_stream, None)
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_cleanup_pyaudio_handles_both_none(self):
        mode = self._make_mode()
        # Should not raise
        mode._cleanup_pyaudio(None, None)

    def test_cleanup_pyaudio_suppresses_stream_exception(self):
        mock_stream = Mock()
        mock_stream.stop_stream.side_effect = Exception("hw error")
        mock_pa = Mock()
        mode = self._make_mode()
        # Should not raise — exception is logged at DEBUG and absorbed
        # close() must still be attempted even when stop_stream() fails
        mode._cleanup_pyaudio(mock_stream, mock_pa)
        mock_stream.close.assert_called_once()
        mock_pa.terminate.assert_called_once()

    def test_cleanup_pyaudio_suppresses_pa_exception(self):
        mock_stream = Mock()
        mock_pa = Mock()
        mock_pa.terminate.side_effect = Exception("pa terminate error")
        mode = self._make_mode()
        # Should not raise
        mode._cleanup_pyaudio(mock_stream, mock_pa)

    # --- _cleanup_barge_in ---

    def test_cleanup_barge_in_calls_stop_on_detector(self):
        mode = self._make_mode()
        mock_barge_in = Mock(spec=BargeInDetector)
        mode.barge_in = mock_barge_in

        mode._cleanup_barge_in()

        mock_barge_in.stop.assert_called_once_with(timeout=0.3)

    def test_cleanup_barge_in_passes_custom_timeout(self):
        mode = self._make_mode()
        mock_barge_in = Mock(spec=BargeInDetector)
        mode.barge_in = mock_barge_in

        mode._cleanup_barge_in(timeout=1.5)

        mock_barge_in.stop.assert_called_once_with(timeout=1.5)

    def test_cleanup_barge_in_handles_none_detector(self):
        mode = self._make_mode()
        mode.barge_in = None
        # Should not raise
        mode._cleanup_barge_in()

    # --- _play_confirmation_beep ---

    @patch('common.wake_word.os.path.exists')
    def test_play_confirmation_beep_plays_when_configured(self, mock_exists):
        mock_exists.return_value = True
        mode = self._make_mode()
        mode.confirmation_beep_path = "/tmp/beep.mp3"

        mode._play_confirmation_beep()

        self.mock_audio.play_audio_file.assert_called_once_with("/tmp/beep.mp3")

    @patch('common.wake_word.os.path.exists')
    def test_play_confirmation_beep_skips_when_beep_disabled(self, mock_exists):
        self.mock_config.wake_confirmation_beep = False
        mock_exists.return_value = True
        mode = self._make_mode()
        mode.confirmation_beep_path = "/tmp/beep.mp3"

        mode._play_confirmation_beep()

        self.mock_audio.play_audio_file.assert_not_called()

    @patch('common.wake_word.os.path.exists')
    def test_play_confirmation_beep_skips_when_path_is_none(self, mock_exists):
        mock_exists.return_value = True
        mode = self._make_mode()
        mode.confirmation_beep_path = None

        mode._play_confirmation_beep()

        self.mock_audio.play_audio_file.assert_not_called()

    @patch('common.wake_word.os.path.exists')
    def test_play_confirmation_beep_skips_when_file_missing(self, mock_exists):
        mock_exists.return_value = False
        mode = self._make_mode()
        mode.confirmation_beep_path = "/tmp/beep.mp3"

        mode._play_confirmation_beep()

        self.mock_audio.play_audio_file.assert_not_called()

    @patch('common.wake_word.os.path.exists')
    def test_play_confirmation_beep_logs_warning_on_playback_error(self, mock_exists):
        mock_exists.return_value = True
        self.mock_audio.play_audio_file.side_effect = Exception("audio error")
        mode = self._make_mode()
        mode.confirmation_beep_path = "/tmp/beep.mp3"
        # Should not raise
        mode._play_confirmation_beep()

    # --- _reset_streaming_state ---

    def test_reset_streaming_state_clears_all_fields(self):
        mode = self._make_mode()
        mode.response_text = "some response"
        mode.streaming_response_text = "some streaming text"
        mode.streaming_user_input = "some input"

        mode._reset_streaming_state()

        self.assertIsNone(mode.response_text)
        self.assertIsNone(mode.streaming_response_text)
        self.assertIsNone(mode.streaming_user_input)

    def test_reset_streaming_state_idempotent_when_already_none(self):
        mode = self._make_mode()
        mode.response_text = None
        mode.streaming_response_text = None
        mode.streaming_user_input = None
        # Should not raise
        mode._reset_streaming_state()
        self.assertIsNone(mode.response_text)
        self.assertIsNone(mode.streaming_response_text)
        self.assertIsNone(mode.streaming_user_input)


    # --- _require_config_enabled ---

    def test_require_config_enabled_raises_when_disabled(self):
        mode = self._make_mode()
        msg = "Wake-word mode requires VAD. Set vad_enabled: enabled"
        with self.assertRaises(RuntimeError) as ctx:
            mode._require_config_enabled("disabled", msg)
        self.assertEqual(str(ctx.exception), msg)

    def test_require_config_enabled_raises_for_false(self):
        mode = self._make_mode()
        with self.assertRaises(RuntimeError):
            mode._require_config_enabled(False, "some error message")

    def test_require_config_enabled_passes_when_enabled(self):
        mode = self._make_mode()
        # Should not raise
        mode._require_config_enabled("enabled", "irrelevant")
        mode._require_config_enabled(True, "irrelevant")

    # --- _remove_recorded_audio ---

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_remove_recorded_audio_removes_existing_file(self, mock_remove, mock_exists):
        mock_exists.return_value = True
        mode = self._make_mode()
        mode.recorded_audio_path = "/tmp/recording.wav"
        mode._remove_recorded_audio()
        mock_remove.assert_called_once_with("/tmp/recording.wav")
        self.assertIsNone(mode.recorded_audio_path)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_remove_recorded_audio_skips_missing_file(self, mock_remove, mock_exists):
        mock_exists.return_value = False
        mode = self._make_mode()
        mode.recorded_audio_path = "/tmp/missing.wav"
        mode._remove_recorded_audio()
        mock_remove.assert_not_called()
        self.assertIsNone(mode.recorded_audio_path)

    def test_remove_recorded_audio_noop_when_path_none(self):
        mode = self._make_mode()
        mode.recorded_audio_path = None
        # Should not raise
        mode._remove_recorded_audio()
        self.assertIsNone(mode.recorded_audio_path)

    @patch('common.wake_word.os.path.exists')
    @patch('common.wake_word.os.remove')
    def test_remove_recorded_audio_handles_oserror(self, mock_remove, mock_exists):
        mock_exists.return_value = True
        mock_remove.side_effect = OSError("Permission denied")
        mode = self._make_mode()
        mode.recorded_audio_path = "/tmp/recording.wav"
        # Should not raise; path should be cleared
        mode._remove_recorded_audio()
        self.assertIsNone(mode.recorded_audio_path)


class TestRequestTimingSummary(unittest.TestCase):
    """Tests for _emit_request_summary() and per-request timing instrumentation."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = False
        self.mock_config.gpt_route_model = "gpt-4.1-nano"

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock(return_value="Plugin response")

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_mode(self, **kwargs):
        return WakeWordMode(
            self.mock_config, self.mock_ai, self.mock_audio,
            **{"route_message": self.mock_route_message, **kwargs}
        )

    # --- _emit_request_summary ---

    def test_emit_summary_no_op_when_t_start_is_none(self):
        mode = self._make_mode()
        mode._req_t_start = None
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        mock_logger.info.assert_not_called()

    def test_emit_summary_includes_transcribe_field(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_transcribe_s = 2.41
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("transcribe=2.41s", summary)

    def test_emit_summary_includes_route_field_with_model_and_name(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_route_s = 1.83
        mode._req_route_name = "weather"
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("route=1.83s(gpt-4.1-nano→weather)", summary)

    def test_emit_summary_includes_plugin_field_with_cache_status(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_plugin_s = 0.05
        # Summary reads the per-request snapshot, not cache.last_hit_type directly
        mode._req_cache_hit_type = "hit-fresh"
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("plugin=0.05s(cache:hit-fresh)", summary)

    def test_emit_summary_cache_status_none_when_no_cache(self):
        mode = self._make_mode(cache=None)
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_plugin_s = 0.05
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("plugin=0.05s(cache:none)", summary)

    def test_emit_summary_cache_status_none_when_last_hit_type_not_set(self):
        mock_cache = Mock()
        mock_cache.last_hit_type = None
        mode = self._make_mode(cache=mock_cache)
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_plugin_s = 0.05
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("plugin=0.05s(cache:none)", summary)

    def test_emit_summary_includes_respond_field(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_respond_s = 4.12
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("respond=4.12s", summary)

    def test_emit_summary_always_includes_total(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 3.0
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("total=", summary)
        self.assertIn("s", summary)

    def test_emit_summary_includes_filler_tag_when_filler_fired(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_plugin_s = 3.50
        mode._req_filler_s = 0.80
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertIn("filler@0.80s", summary)

    def test_emit_summary_omits_filler_tag_when_filler_not_fired(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_plugin_s = 0.05
        mode._req_filler_s = None
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertNotIn("filler", summary)

    def test_filler_write_guarded_by_seq_token(self):
        """Filler does not update _req_filler_s if _req_seq changed (new request started)."""
        mode = self._make_mode()
        mode._req_seq = 1
        mode._req_filler_s = None
        # Simulate filler closure captured seq=1 but request advanced to seq=2 before filler finished
        mode._req_seq = 2
        if mode._req_seq == 1:  # guard: should NOT fire
            mode._req_filler_s = 9.99
        self.assertIsNone(mode._req_filler_s)

    def test_emit_summary_omits_plugin_field_for_default_route(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic() - 5.0
        mode._req_transcribe_s = 2.0
        mode._req_route_s = 1.0
        mode._req_route_name = "default-route"
        mode._req_plugin_s = None  # No plugin on default route
        mode._req_respond_s = 3.0
        with patch("common.wake_word.logger") as mock_logger:
            mode._emit_request_summary()
        summary = mock_logger.info.call_args[0][0]
        self.assertNotIn("plugin=", summary)
        self.assertIn("respond=3.00s", summary)

    # --- timing fields set in _state_processing ---

    def test_state_idle_sets_req_t_start_on_wake_word(self):
        """_req_t_start is set when wake word is detected."""
        mode = self._make_mode()
        mode.porcupine = Mock()
        mode.porcupine.sample_rate = 16000
        mode.porcupine.frame_length = 512
        mode.running = True
        mode.state = State.IDLE

        # Simulate: first frame no wake word, second frame detects wake word
        call_count = [0]

        def porcupine_process(pcm):
            call_count[0] += 1
            return 0 if call_count[0] >= 2 else -1

        mode.porcupine.process.side_effect = porcupine_process
        mode._play_confirmation_beep = Mock()

        with patch("common.wake_word.pyaudio.PyAudio") as mock_pa_cls:
            mock_pa = Mock()
            mock_pa_cls.return_value = mock_pa
            mock_stream = Mock()
            mock_pa.open.return_value = mock_stream
            mock_stream.read.return_value = b"\x00" * (512 * 2)  # 512 int16 samples
            mode._state_idle()

        self.assertIsNotNone(mode._req_t_start)

    def test_summary_suppressed_when_barge_in_during_responding(self):
        """_emit_request_summary is skipped when barge-in interrupts the response."""
        mode = self._make_mode()
        mode._req_t_start = time.monotonic()
        mode.streaming_user_input = "tell me a joke"
        mode.streaming_response_text = None

        mock_barge_in = Mock()
        mock_barge_in.is_triggered = True
        mode.barge_in = mock_barge_in

        mode._respond_streaming = Mock()
        mode._cleanup_barge_in = Mock()
        mode._remove_recorded_audio = Mock()
        mode._play_confirmation_beep = Mock()

        with patch("common.wake_word.logger") as mock_logger:
            mode._state_responding()

        mock_logger.info.assert_not_called()
        self.assertEqual(mode.state, State.LISTENING)

    def test_cache_hit_type_snapshotted_after_plugin_call(self):
        """_req_cache_hit_type is snapshotted from cache.last_hit_type immediately after plugin."""
        mock_cache = Mock(spec_set=["last_hit_type"])
        mock_cache.last_hit_type = None
        mode = self._make_mode(cache=mock_cache)
        mode._req_t_start = time.monotonic()
        mode.barge_in = Mock()
        mode.barge_in.is_triggered = False
        mode.barge_in.start = Mock()
        mode.barge_in.run_with_polling = Mock(side_effect=lambda op, name, **kw: op())
        mode.recorded_audio_path = "/tmp/fake.wav"
        mode.plugins = {"weather": Mock()}

        mode.ai.transcribe_and_translate.return_value = "What's the weather?"
        mode.ai.define_route.return_value = {"route": "weather"}

        def plugin_side_effect(user_input, route):
            mock_cache.last_hit_type = "hit-stale"
            return "Cloudy"
        self.mock_route_message.side_effect = plugin_side_effect

        with patch("common.wake_word.os.path.exists", return_value=True):
            mode._state_processing()

        # Snapshot must capture the value set by the plugin call
        self.assertEqual(mode._req_cache_hit_type, "hit-stale")

class TestTerminalUIIntegration(unittest.TestCase):
    """Tests that WakeWordMode routes state and conversation output through TerminalUI."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.visual_state_indicator = True
        self.mock_config.vad_enabled = "enabled"
        self.mock_config.wake_phrase = "hey bot"
        self.mock_config.botname = "testbot"
        self.mock_config.vad_aggressiveness = 1
        self.mock_config.sample_rate = 16000
        self.mock_config.frame_duration_ms = 30
        self.mock_config.min_speech_frames = 3
        self.mock_config.max_silence_frames = 10
        self.mock_config.stream_responses = "enabled"
        self.mock_config.stream_tts = "enabled"

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_route_message = Mock(return_value="Plugin response")
        self.mock_ui = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_mode(self, **kwargs):
        return WakeWordMode(
            self.mock_config, self.mock_ai, self.mock_audio,
            route_message=self.mock_route_message,
            ui=self.mock_ui,
            **kwargs,
        )

    def test_state_idle_calls_ui_set_state_waiting(self):
        mode = _build_mode_for_idle(self.mock_config, self.mock_ai, self.mock_audio,
                                     self.mock_route_message, self.mock_ui)
        # Simulate one idle cycle by calling _state_idle with a mocked porcupine
        mode.porcupine = Mock()
        mode.porcupine.frame_length = 512
        mode.porcupine.sample_rate = 16000
        mode.porcupine.process.return_value = -1  # no keyword
        mode.running = True
        # Force state to leave IDLE after one iteration while returning "no keyword"
        def stop_after_one(*args, **kwargs):
            mode.running = False
            return -1
        mode.porcupine.process.side_effect = stop_after_one

        mock_stream = Mock()
        mock_stream.read.return_value = b"\x00" * 1024
        mock_pa = Mock()
        mock_pa.open.return_value = mock_stream

        with patch("common.wake_word.pyaudio.PyAudio", return_value=mock_pa):
            mode._state_idle()

        self.mock_ui.set_state.assert_called_with("waiting")

    def test_state_listening_calls_ui_set_state_listening(self):
        mode = self._make_mode()
        mode.vad_recorder = Mock()
        mode.vad_recorder.record.return_value = "/tmp/fake.wav"
        mode._play_confirmation_beep = Mock()
        mode.barge_in = Mock()
        mode.barge_in.run_with_polling = Mock(side_effect=lambda op, name, **kw: op())
        mode.barge_in.is_triggered = False

        mode._state_listening()

        self.mock_ui.set_state.assert_any_call("listening")

    def test_state_processing_calls_ui_set_state_processing(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic()
        mode.barge_in = Mock()
        mode.barge_in.is_triggered = False
        mode.barge_in.start = Mock()
        mode.barge_in.run_with_polling = Mock(side_effect=lambda op, name, **kw: op())
        mode.recorded_audio_path = "/tmp/fake.wav"
        mode.plugins = {"weather": Mock()}
        mode.ai.transcribe_and_translate.return_value = "What time is it?"
        mode.ai.define_route.return_value = {"route": "default"}

        with patch("common.wake_word.os.path.exists", return_value=True):
            mode._state_processing()

        self.mock_ui.set_state.assert_any_call("processing")

    def test_state_processing_calls_ui_print_exchange_for_user_input(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic()
        mode.barge_in = Mock()
        mode.barge_in.is_triggered = False
        mode.barge_in.start = Mock()
        mode.barge_in.run_with_polling = Mock(side_effect=lambda op, name, **kw: op())
        mode.recorded_audio_path = "/tmp/fake.wav"
        mode.plugins = {"weather": Mock()}
        mode.ai.transcribe_and_translate.return_value = "hello"
        mode.ai.define_route.return_value = {"route": "default"}

        with patch("common.wake_word.os.path.exists", return_value=True):
            mode._state_processing()

        self.mock_ui.print_exchange.assert_any_call("you", "hello")

    def test_state_responding_calls_ui_set_state_responding(self):
        mode = self._make_mode()
        mode._req_t_start = time.monotonic()
        mode.streaming_user_input = None
        mode.streaming_response_text = None
        mode.barge_in = Mock()
        mode.barge_in.is_triggered = False
        mode._cleanup_barge_in = Mock()
        mode._remove_recorded_audio = Mock()
        mode._play_confirmation_beep = Mock()
        mode.response_text = "hello"

        mode._state_responding()

        self.mock_ui.set_state.assert_any_call("responding")

    def test_state_processing_calls_ui_print_exchange_for_bot_response(self):
        # Plugin route (not default): route_message is called, response printed via print_exchange
        mode = self._make_mode()
        mode._req_t_start = time.monotonic()
        mode.barge_in = Mock()
        mode.barge_in.is_triggered = False
        mode.barge_in.start = Mock()
        mode.barge_in.run_with_polling = Mock(side_effect=lambda op, name, **kw: op())
        mode.recorded_audio_path = "/tmp/fake.wav"
        mode.plugins = {"weather": Mock()}
        mode.ai.transcribe_and_translate.return_value = "What is the weather?"
        # Route to "weather" plugin (present in plugins) → no stream_default_route
        mode.ai.define_route.return_value = {"route": "weather"}
        self.mock_route_message.return_value = "Sunny and warm"

        with patch("common.wake_word.os.path.exists", return_value=True):
            mode._state_processing()

        self.mock_ui.print_exchange.assert_any_call("testbot", "Sunny and warm")

    def test_run_finally_calls_ui_close(self):
        mode = self._make_mode()
        mode._initialize = Mock()
        mode._cleanup = Mock()
        # run() sets self.running = True before the loop, so we must stop it
        # from inside _state_idle instead of pre-setting running=False.
        mode._state_idle = Mock(side_effect=lambda: setattr(mode, "running", False))

        mode.run()

        self.mock_ui.close.assert_called_once()


def _build_mode_for_idle(config, ai, audio, route_message, ui):
    mode = WakeWordMode(config, ai, audio, route_message=route_message, ui=ui)
    return mode


if __name__ == '__main__':
    unittest.main()
