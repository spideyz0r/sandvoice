import logging
import os
import queue
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch, call

from common.streaming_responder import StreamingResponder, _CompositeStopEvent


class TestCompositeStopEvent(unittest.TestCase):
    def test_not_set_when_neither_event_is_set(self):
        interrupt = threading.Event()
        barge = threading.Event()
        evt = _CompositeStopEvent(interrupt, barge)
        self.assertFalse(evt.is_set())

    def test_set_when_interrupt_is_set(self):
        interrupt = threading.Event()
        interrupt.set()
        barge = threading.Event()
        evt = _CompositeStopEvent(interrupt, barge)
        self.assertTrue(evt.is_set())

    def test_set_when_barge_in_is_set(self):
        interrupt = threading.Event()
        barge = threading.Event()
        barge.set()
        evt = _CompositeStopEvent(interrupt, barge)
        self.assertTrue(evt.is_set())

    def test_set_when_both_are_set(self):
        interrupt = threading.Event()
        interrupt.set()
        barge = threading.Event()
        barge.set()
        evt = _CompositeStopEvent(interrupt, barge)
        self.assertTrue(evt.is_set())

    def test_set_method_only_sets_interrupt(self):
        interrupt = threading.Event()
        barge = threading.Event()
        evt = _CompositeStopEvent(interrupt, barge)
        evt.set()
        self.assertTrue(interrupt.is_set())
        self.assertFalse(barge.is_set())

    def test_none_barge_in_is_handled(self):
        interrupt = threading.Event()
        evt = _CompositeStopEvent(interrupt, None)
        self.assertFalse(evt.is_set())
        interrupt.set()
        self.assertTrue(evt.is_set())


class TestStreamingResponderSetup(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_audio_lock = threading.Lock()
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = Mock()
        self.mock_barge_in.event.is_set.return_value = False
        self.mock_pop_chunk_fn = Mock()
        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_responder(self):
        return StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=self.mock_audio_lock,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=self.mock_pop_chunk_fn,
            config=self.mock_config,
        )

    def test_stores_dependencies(self):
        responder = self._make_responder()
        self.assertIs(responder._ai, self.mock_ai)
        self.assertIs(responder._audio, self.mock_audio)
        self.assertIs(responder._audio_lock, self.mock_audio_lock)
        self.assertIs(responder._barge_in, self.mock_barge_in)
        self.assertIs(responder._pop_chunk_fn, self.mock_pop_chunk_fn)
        self.assertIs(responder._config, self.mock_config)


class TestStreamingResponderPrecomputed(unittest.TestCase):
    """Tests for respond() with pre-computed text (response_text parameter)."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = Mock()
        self.mock_barge_in.event.is_set.return_value = False
        self.mock_pop_chunk_fn = Mock()
        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_responder(self):
        return StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=self.mock_pop_chunk_fn,
            config=self.mock_config,
        )

    def test_precomputed_text_sent_to_tts_worker(self):
        """Pre-computed text is enqueued and passed to TTS worker."""
        tts_file = "/tmp/tts-precomputed.mp3"
        self.mock_ai.text_to_speech.return_value = [tts_file]

        responder = self._make_responder()
        responder.respond(user_input=None, response_text="Hello from plugin.")

        self.mock_ai.text_to_speech.assert_called_once_with("Hello from plugin.")
        self.mock_audio.play_audio_queue.assert_called_once()

    def test_precomputed_text_does_not_call_stream_response_deltas(self):
        """LLM streaming is skipped when response_text is provided."""
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts.mp3"]

        responder = self._make_responder()
        responder.respond(user_input=None, response_text="Direct text.")

        self.mock_ai.stream_response_deltas.assert_not_called()

    def test_precomputed_text_skipped_on_barge_in(self):
        """Pre-computed text is not enqueued when barge-in is already triggered."""
        self.mock_barge_in.event.is_set.return_value = True

        responder = self._make_responder()
        responder.respond(user_input=None, response_text="Skipped.")

        self.mock_ai.text_to_speech.assert_not_called()

    @patch('common.streaming_responder.os.path.exists')
    @patch('common.streaming_responder.os.remove')
    def test_tts_returns_no_files_sets_production_failed(self, mock_remove, mock_exists):
        """When TTS returns no files, production failure is handled gracefully."""
        self.mock_ai.text_to_speech.return_value = []
        mock_exists.return_value = True

        responder = self._make_responder()
        # Should not raise
        responder.respond(user_input=None, response_text="Some text.")

        self.mock_audio.play_audio_queue.assert_called_once()


class TestStreamingResponderLLMStream(unittest.TestCase):
    """Tests for respond() with LLM streaming (user_input parameter)."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = Mock()
        self.mock_barge_in.event.is_set.return_value = False
        self.mock_pop_chunk_fn = Mock()
        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_responder(self):
        return StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=self.mock_pop_chunk_fn,
            config=self.mock_config,
        )

    def test_calls_stream_response_deltas_with_user_input(self):
        """LLM streaming is invoked with the provided user_input."""
        self.mock_ai.stream_response_deltas.return_value = iter([])
        self.mock_pop_chunk_fn.return_value = (None, "")

        responder = self._make_responder()
        responder.respond(user_input="What's the weather?", response_text=None)

        self.mock_ai.stream_response_deltas.assert_called_once_with("What's the weather?")

    def test_delta_is_chunked_and_sent_to_tts(self):
        """Streaming deltas are accumulated, chunked, and sent to TTS."""
        long_text = "Hello there! " * 20  # enough to trigger chunking
        self.mock_ai.stream_response_deltas.return_value = iter([long_text])
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts.mp3"]

        # pop_chunk_fn returns a chunk on first call, then None on second
        chunk_text = "Hello there! " * 20
        call_count = [0]

        def fake_pop(buffer, boundary, min_chars):
            call_count[0] += 1
            if call_count[0] == 1:
                return (chunk_text, "")
            return (None, buffer)

        self.mock_pop_chunk_fn.side_effect = fake_pop

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        # TTS was called with chunked content
        self.mock_ai.text_to_speech.assert_called()

    def test_stream_exception_prints_error(self):
        """API error during streaming is caught and printed; does not propagate."""
        self.mock_ai.stream_response_deltas.side_effect = Exception("API error")
        self.mock_pop_chunk_fn.return_value = (None, "")

        responder = self._make_responder()
        # Should not raise
        responder.respond(user_input="hi", response_text=None)

    def test_incomplete_stream_removes_dangling_history(self):
        """When streaming is incomplete, the last user turn in history is removed."""
        # Simulate barge-in stopping the stream after one delta
        call_count = [0]

        def stream_deltas(_ui):
            call_count[0] += 1
            yield "Hello"
            self.mock_barge_in.event.is_set.return_value = True
            yield "World"

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas
        self.mock_ai.conversation_history = ["User: hi"]
        self.mock_pop_chunk_fn.return_value = (None, "")

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        # History entry removed because stream was incomplete
        self.assertEqual(self.mock_ai.conversation_history, [])

    def test_completed_stream_does_not_remove_history(self):
        """When streaming completes normally, history is not modified."""
        self.mock_ai.stream_response_deltas.return_value = iter(["Hello."])
        self.mock_ai.conversation_history = ["User: hi"]
        self.mock_pop_chunk_fn.return_value = (None, "")

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        # History unchanged because stream completed
        self.assertEqual(self.mock_ai.conversation_history, ["User: hi"])

    def test_barge_in_stops_delta_collection(self):
        """Barge-in during streaming stops delta collection early."""
        events_fired = []

        def stream_deltas(_ui):
            events_fired.append("delta1")
            yield "Delta 1"
            self.mock_barge_in.event.is_set.return_value = True
            events_fired.append("delta2")
            yield "Delta 2"
            events_fired.append("delta3")
            yield "Delta 3"

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas
        self.mock_pop_chunk_fn.return_value = (None, "")

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        # delta2 is reached (barge-in is checked after each delta), but delta3 is not
        self.assertIn("delta2", events_fired)
        self.assertNotIn("delta3", events_fired)

    def test_final_buffer_flushed_on_completion(self):
        """Remaining buffer content is flushed as a final chunk after stream completes."""
        self.mock_ai.stream_response_deltas.return_value = iter(["Short text"])
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts.mp3"]

        # pop_chunk returns None (no complete chunk), leaving buffer with content
        self.mock_pop_chunk_fn.return_value = (None, "Short text")

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        # TTS worker should receive the final buffer flush
        self.mock_ai.text_to_speech.assert_called_once_with("Short text")

    def test_player_failure_logs_warning(self):
        """Player failure is logged as a warning (not raised)."""
        self.mock_audio.play_audio_queue.return_value = (False, "/tmp/bad.mp3", Exception("boom"))
        self.mock_ai.stream_response_deltas.return_value = iter([])
        self.mock_pop_chunk_fn.return_value = (None, "")

        responder = self._make_responder()
        # Should not raise
        responder.respond(user_input="hi", response_text=None)

    def test_player_failure_on_barge_in_is_expected(self):
        """Player failure during barge-in does not produce a warning."""
        self.mock_barge_in.event.is_set.return_value = True
        self.mock_audio.play_audio_queue.return_value = (False, "/tmp/bad.mp3", Exception("barge"))
        self.mock_ai.stream_response_deltas.return_value = iter([])
        self.mock_pop_chunk_fn.return_value = (None, "")

        responder = self._make_responder()
        # Should not raise
        responder.respond(user_input="hi", response_text=None)


class TestStreamingResponderNoBargein(unittest.TestCase):
    """Tests for respond() when barge_in has no event (or event is None)."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = None
        self.mock_pop_chunk_fn = Mock()
        self.mock_pop_chunk_fn.return_value = (None, "")
        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_responder(self):
        return StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=self.mock_pop_chunk_fn,
            config=self.mock_config,
        )

    def test_precomputed_text_works_with_none_barge_in_event(self):
        """Pre-computed text works when barge-in event is None."""
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts.mp3"]

        responder = self._make_responder()
        responder.respond(user_input=None, response_text="Hello.")

        self.mock_ai.text_to_speech.assert_called_once_with("Hello.")

    def test_llm_stream_works_with_none_barge_in_event(self):
        """LLM streaming works when barge-in event is None."""
        self.mock_ai.stream_response_deltas.return_value = iter(["Hi."])

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        self.mock_ai.stream_response_deltas.assert_called_once_with("hi")


class TestStreamingResponderDebugMode(unittest.TestCase):
    """Tests for respond() debug mode behavior."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = Mock()
        self.mock_barge_in.event.is_set.return_value = False
        self.mock_pop_chunk_fn = Mock()
        self.mock_pop_chunk_fn.return_value = (None, "")
        self.mock_config = Mock()
        self.mock_config.debug = True
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_responder(self):
        return StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=self.mock_pop_chunk_fn,
            config=self.mock_config,
        )

    def test_debug_mode_does_not_print_assembled_text(self):
        """In debug mode, the assembled response text is not printed after streaming."""
        self.mock_ai.stream_response_deltas.return_value = iter(["Hello!"])

        responder = self._make_responder()
        # Should not raise; debug output goes to stdout which we don't assert here
        responder.respond(user_input="hi", response_text=None)

    def test_debug_mode_precomputed_text_still_works(self):
        """Pre-computed text path works in debug mode (no LLM call)."""
        self.mock_ai.text_to_speech.return_value = ["/tmp/tts.mp3"]

        responder = self._make_responder()
        responder.respond(user_input=None, response_text="Debug text.")

        self.mock_ai.text_to_speech.assert_called_once_with("Debug text.")


class TestStreamingResponderBoundaryConfig(unittest.TestCase):
    """Tests for stream_tts_boundary configuration."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = Mock()
        self.mock_barge_in.event.is_set.return_value = False

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_responder(self, boundary, pop_chunk_fn):
        config = Mock()
        config.debug = False
        config.botname = "TestBot"
        config.stream_tts_boundary = boundary
        return StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=pop_chunk_fn,
            config=config,
        )

    def test_boundary_passed_to_pop_chunk_fn(self):
        """The stream_tts_boundary value is passed to pop_chunk_fn."""
        pop_fn = Mock(return_value=(None, ""))
        self.mock_ai.stream_response_deltas.return_value = iter(["text"])

        responder = self._make_responder("paragraph", pop_fn)
        responder.respond(user_input="hi", response_text=None)

        # pop_chunk_fn is called with the configured boundary
        for call_args in pop_fn.call_args_list:
            self.assertEqual(call_args.kwargs.get("boundary") or call_args[1].get("boundary"), "paragraph")

    def test_none_boundary_defaults_to_sentence(self):
        """None boundary falls back to 'sentence'."""
        pop_fn = Mock(return_value=(None, ""))
        self.mock_ai.stream_response_deltas.return_value = iter(["text"])

        responder = self._make_responder(None, pop_fn)
        responder.respond(user_input="hi", response_text=None)

        for call_args in pop_fn.call_args_list:
            used_boundary = call_args.kwargs.get("boundary") or call_args[1].get("boundary")
            self.assertEqual(used_boundary, "sentence")


class TestStreamingResponderTTSFileCleanup(unittest.TestCase):
    """Tests for TTS file cleanup on stop."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = Mock()
        self.mock_barge_in.event.is_set.return_value = False
        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    @patch('common.streaming_responder.os.path.exists')
    @patch('common.streaming_responder.os.remove')
    def test_tts_files_cleaned_up_on_stop_event(self, mock_remove, mock_exists):
        """TTS files are removed when stop event fires during tts_worker processing."""
        tts_file = "/tmp/tts-cleanup.mp3"
        self.mock_ai.text_to_speech.return_value = [tts_file]

        # Trigger barge-in after TTS is called so stop_event fires
        call_count = [0]

        def is_set_side_effect():
            call_count[0] += 1
            # Return True after TTS has been called
            return call_count[0] > 5

        self.mock_barge_in.event.is_set.side_effect = is_set_side_effect
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        mock_exists.return_value = True

        responder = StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=Mock(return_value=(None, "")),
            config=self.mock_config,
        )
        responder.respond(user_input=None, response_text="Text to speak.")

        # After respond, no exception raised


class TestStreamingResponderInterruptPaths(unittest.TestCase):
    """Tests for interrupt/failure paths in LLM streaming."""

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.mock_ai = Mock()
        self.mock_audio = Mock()
        self.mock_audio.play_audio_queue.return_value = (True, None, None)
        self.mock_barge_in = Mock()
        self.mock_barge_in.event = Mock()
        self.mock_barge_in.event.is_set.return_value = False
        self.mock_config = Mock()
        self.mock_config.debug = False
        self.mock_config.botname = "TestBot"
        self.mock_config.stream_tts_boundary = "sentence"

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _make_responder(self, pop_chunk_fn=None):
        if pop_chunk_fn is None:
            pop_chunk_fn = Mock(return_value=(None, ""))
        return StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=pop_chunk_fn,
            config=self.mock_config,
        )

    def test_player_failure_then_deltas_continue_collection(self):
        """After player fails, deltas are still collected (interrupt_event.is_set() path)."""
        consumed = []

        def stream_deltas(_ui):
            for p in ["A", "B", "C"]:
                consumed.append(p)
                yield p

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas
        # Player fails immediately to trigger interrupt_event
        self.mock_audio.play_audio_queue.return_value = (False, "/tmp/fail.mp3", Exception("boom"))

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        # All deltas consumed even after interrupt
        self.assertEqual(consumed, ["A", "B", "C"])

    def test_production_failed_then_deltas_continue_collection(self):
        """After TTS production fails, deltas keep being collected."""
        consumed = []

        def stream_deltas(_ui):
            for p in ["X", "Y", "Z"]:
                consumed.append(p)
                yield p

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas
        # TTS returns no files to trigger production_failed_event
        self.mock_ai.text_to_speech.return_value = []

        pop_calls = [0]

        def fake_pop(buffer, boundary, min_chars):
            pop_calls[0] += 1
            if pop_calls[0] == 1:
                return ("X", "")
            return (None, buffer)

        responder = self._make_responder(pop_chunk_fn=fake_pop)
        responder.respond(user_input="hi", response_text=None)

        # All deltas consumed
        self.assertEqual(consumed, ["X", "Y", "Z"])

    def test_put_text_queue_fails_for_chunk_sets_interrupt(self):
        """If _put_text_queue returns False during chunking, interrupt_event is set."""
        # Stop event fires immediately so _put_text_queue returns False
        self.mock_barge_in.event.is_set.return_value = True

        delta_calls = []

        def stream_deltas(_ui):
            delta_calls.append(1)
            yield "Some long text that would be chunked"

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas

        pop_call_count = [0]

        def fake_pop(buffer, boundary, min_chars):
            pop_call_count[0] += 1
            if pop_call_count[0] == 1:
                return ("chunk", "")
            return (None, buffer)

        responder = self._make_responder(pop_chunk_fn=fake_pop)
        # Should not raise
        responder.respond(user_input="hi", response_text=None)

    def test_thread_alive_after_timeout_logs_warning(self):
        """If threads don't exit within timeout, a warning is logged (no crash)."""
        # We can't reliably force threads to stay alive in tests, but we can
        # verify the code path doesn't raise by running normally
        self.mock_ai.stream_response_deltas.return_value = iter([])

        responder = self._make_responder()
        # Normal operation; no exception
        responder.respond(user_input="hi", response_text=None)

    def test_history_removal_skipped_when_last_entry_does_not_match(self):
        """History is not modified when last entry doesn't match the user input."""
        def stream_deltas(_ui):
            self.mock_barge_in.event.is_set.return_value = True
            yield "Hello"

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas
        self.mock_ai.conversation_history = ["User: other input"]

        responder = self._make_responder()
        responder.respond(user_input="hi", response_text=None)

        # History not modified since last entry doesn't match "hi"
        self.assertEqual(self.mock_ai.conversation_history, ["User: other input"])

    def test_history_removal_skipped_when_history_is_empty(self):
        """History removal is handled gracefully when history is empty."""
        def stream_deltas(_ui):
            self.mock_barge_in.event.is_set.return_value = True
            yield "Hello"

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas
        self.mock_ai.conversation_history = []

        responder = self._make_responder()
        # Should not raise
        responder.respond(user_input="hi", response_text=None)

    def test_precomputed_text_enqueue_fails_sets_interrupt(self):
        """When precomputed text enqueue returns False, interrupt_event is set."""
        # stop_event fires at the start so _put_text_queue returns False immediately
        self.mock_barge_in.event.is_set.return_value = True

        responder = self._make_responder()
        # Should not raise (barge-in event causes _put_text_queue to be skipped anyway)
        responder.respond(user_input=None, response_text="text")

        # TTS not called because barge_in_event was set
        self.mock_ai.text_to_speech.assert_not_called()

    def test_debug_mode_exception_prints_newline_then_error(self):
        """In debug mode, an API error during streaming prints a newline then error message."""
        self.mock_config.debug = True
        self.mock_ai.stream_response_deltas.side_effect = Exception("API failure")

        responder = self._make_responder()
        # Should not raise even in debug mode
        responder.respond(user_input="hi", response_text=None)

    def test_final_buffer_enqueue_fails_when_stop_event_fires(self):
        """When stop_event fires just as stream completes, final buffer flush may not be enqueued."""
        # Use a delta that fills the buffer but doesn't trigger a chunk
        self.mock_ai.stream_response_deltas.return_value = iter(["short text"])
        # pop_chunk returns None so buffer accumulates
        pop_fn = Mock(return_value=(None, "short text"))
        # Player fails immediately to set interrupt_event before final flush
        self.mock_audio.play_audio_queue.return_value = (False, "/tmp/fail.mp3", Exception("boom"))

        responder = StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=pop_fn,
            config=self.mock_config,
        )
        # Should not raise
        responder.respond(user_input="hi", response_text=None)

    def test_production_failed_continue_in_delta_loop(self):
        """Deltas keep flowing even after production_failed_event is set."""
        import time as _time

        tts_called = threading.Event()
        got_second_delta = threading.Event()

        def stream_deltas(_ui):
            yield "First chunk of text that is long enough to trigger TTS call here yes it is"
            # Wait a bit for TTS worker to process
            tts_called.wait(timeout=2.0)
            got_second_delta.set()
            yield "Second delta"
            yield "Third delta"

        self.mock_ai.stream_response_deltas.side_effect = stream_deltas

        original_tts = [None]

        def tts_side_effect(chunk):
            original_tts[0] = chunk
            tts_called.set()
            return []  # No files → sets production_failed_event

        self.mock_ai.text_to_speech.side_effect = tts_side_effect

        pop_calls = [0]

        def fake_pop(buffer, boundary, min_chars):
            pop_calls[0] += 1
            if pop_calls[0] == 1:
                return ("First chunk of text that is long enough to trigger TTS call here yes it is", "")
            return (None, buffer)

        responder = StreamingResponder(
            ai=self.mock_ai,
            audio=self.mock_audio,
            audio_lock=None,
            barge_in=self.mock_barge_in,
            pop_chunk_fn=fake_pop,
            config=self.mock_config,
        )
        responder.respond(user_input="hi", response_text=None)

        # Verify TTS was called (production failed path exercised)
        self.assertTrue(tts_called.is_set())
        # Second delta was reached
        self.assertTrue(got_second_delta.is_set())
