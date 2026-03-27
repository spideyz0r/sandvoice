import logging
import os
import queue
import threading
import time

from common.error_handling import handle_api_error

logger = logging.getLogger(__name__)


class _CompositeStopEvent:
    """Stop event that fires when either an interrupt or a barge-in event is set."""

    def __init__(self, interrupt_evt, barge_evt):
        self._interrupt = interrupt_evt
        self._barge = barge_evt

    def is_set(self):
        if self._interrupt.is_set():
            return True
        return bool(self._barge and self._barge.is_set())

    def set(self):
        # Only set the interrupt event (do not set barge-in).
        self._interrupt.set()


class StreamingResponder:
    """Manages the threaded streaming TTS pipeline for wake-word mode responses.

    Handles three concurrent concerns:
    1. LLM streaming: collecting deltas, chunking text onto a text queue.
    2. TTS worker thread: consuming text chunks, calling ai.text_to_speech(),
       writing audio files, putting file paths onto an audio queue.
    3. Audio player worker thread: consuming audio file paths, acquiring the
       audio lock, playing files, deleting temp files.

    Barge-in interruption is polled from barge_in.event. StreamingResponder
    does not clear or stop the barge-in event — the caller (_state_responding)
    checks it after respond() returns to decide whether to transition to LISTENING.
    """

    def __init__(self, ai, audio, audio_lock, barge_in, pop_chunk_fn, config, ui=None):
        """
        Args:
            ai:           AI instance (stream_response_deltas, text_to_speech).
            audio:        Audio instance (play_audio_queue with audio_lock/stop_event pattern).
            audio_lock:   threading.Lock acquired around audio playback.
            barge_in:     BargeInDetector instance (polled for interruption).
            pop_chunk_fn: The standalone pop_streaming_chunk function imported from
                          common.ai. Injected rather than called via ai because it is
                          a module-level function, not an instance method.
            config:       Config instance (reads stream_tts_boundary, debug, botname).
            ui:           Optional TerminalUI instance. When present, the assembled
                          response is printed via ui.print_exchange() instead of print().
        """
        self._ai = ai
        self._audio = audio
        self._audio_lock = audio_lock
        self._barge_in = barge_in
        self._pop_chunk_fn = pop_chunk_fn
        self._config = config
        self._ui = ui

    def respond(self, user_input=None, response_text=None):
        """Stream a response to the user.

        If response_text is provided, stream it directly to TTS (pre-computed text).
        Otherwise, stream from the LLM via ai.stream_response_deltas() using user_input.
        user_input may be None when a pre-computed plugin response is provided via
        response_text.

        Barge-in interruption is communicated via barge_in.event (the underlying
        threading.Event whose .is_set() is polled). StreamingResponder must not clear
        or stop the barge-in event — _state_responding() checks it after respond()
        returns to decide whether to transition to LISTENING.

        Raises:
            ValueError: If neither user_input nor response_text is provided, or if
                        both are provided simultaneously.
        """
        if user_input is None and response_text is None:
            raise ValueError("respond() requires user_input or response_text")
        if user_input is not None and response_text is not None:
            raise ValueError("respond() requires exactly one of user_input or response_text")

        barge_in_event = self._barge_in.event if self._barge_in is not None else None
        interrupt_event = threading.Event()
        production_failed_event = threading.Event()

        stop_event = _CompositeStopEvent(interrupt_event, barge_in_event)

        stream_tts_buffer_chunks = 2
        text_queue = queue.Queue(maxsize=stream_tts_buffer_chunks)
        audio_queue_max_files = max(4, stream_tts_buffer_chunks * 4)
        audio_queue = queue.Queue(maxsize=audio_queue_max_files)

        tts_error = [""]
        queue_put_max_wait_s = 10.0

        def _put_text_queue(item, allow_when_stopped=False):
            deadline = time.monotonic() + queue_put_max_wait_s
            while True:
                if stop_event.is_set() and not allow_when_stopped:
                    return False
                try:
                    text_queue.put(item, timeout=0.1)
                    return True
                except queue.Full:
                    if time.monotonic() >= deadline:
                        logger.warning("Timed out enqueueing streaming text chunk")
                        return False

        def tts_worker():
            try:
                while not stop_event.is_set():
                    if production_failed_event.is_set():
                        break
                    try:
                        chunk = text_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if chunk is None:
                        break

                    tts_files = self._ai.text_to_speech(chunk)

                    if not tts_files:
                        production_failed_event.set()
                        if not tts_error[0]:
                            tts_error[0] = "TTS returned no audio files"
                        break

                    last_idx = -1
                    for idx, f in enumerate(tts_files):
                        last_idx = idx
                        if stop_event.is_set():
                            try:
                                if os.path.exists(f):
                                    os.remove(f)
                            except OSError:
                                pass
                            continue

                        if production_failed_event.is_set():
                            break

                        deadline = time.monotonic() + queue_put_max_wait_s
                        while not stop_event.is_set():
                            try:
                                audio_queue.put(f, timeout=0.1)
                                break
                            except queue.Full:
                                if time.monotonic() >= deadline:
                                    production_failed_event.set()
                                    if not tts_error[0]:
                                        tts_error[0] = "Timed out enqueueing streaming audio chunk"
                                    try:
                                        if os.path.exists(f):
                                            os.remove(f)
                                    except OSError:
                                        pass
                                    break

                        if production_failed_event.is_set():
                            break

                    if production_failed_event.is_set() and last_idx != -1 and last_idx < (len(tts_files) - 1):
                        for remaining_file in tts_files[last_idx + 1:]:
                            try:
                                if os.path.exists(remaining_file):
                                    os.remove(remaining_file)
                            except OSError:
                                pass

                    if production_failed_event.is_set():
                        break

            finally:
                try:
                    audio_queue.put(None, timeout=0.1)
                except queue.Full:
                    interrupt_event.set()

        player_success = [True]
        player_failed_file = [""]
        player_error = [""]

        def player_worker():
            # Pass the lock so it is acquired per-file, not across the
            # entire queue-drain loop (which blocks on queue.get() between files).
            success, failed_file, error = self._audio.play_audio_queue(
                audio_queue, stop_event=stop_event, playback_lock=self._audio_lock
            )
            player_success[0] = bool(success)
            if failed_file:
                player_failed_file[0] = str(failed_file)
            if error:
                player_error[0] = str(error)
            if not success:
                interrupt_event.set()

        tts_thread = threading.Thread(target=tts_worker, name="wake-stream-tts-worker", daemon=True)
        player_thread = threading.Thread(target=player_worker, name="wake-stream-audio-player", daemon=True)
        tts_thread.start()
        player_thread.start()

        boundary = str(getattr(self._config, "stream_tts_boundary", "sentence") or "sentence").strip().lower()
        # Rough heuristic for English: ~35 characters/sec spoken.
        chars_per_second = 35
        target_s = 6
        first_min_chars = max(120, int(target_s * chars_per_second))
        next_min_chars = 200

        buffer = ""
        full_parts = []
        is_first = True
        stream_completed = False

        if response_text is not None:
            # Pre-computed plugin response — enqueue directly without LLM streaming.
            if not (barge_in_event and barge_in_event.is_set()) and not stop_event.is_set():
                if _put_text_queue(response_text):
                    stream_completed = True
                else:
                    interrupt_event.set()
        else:
            if self._config.debug:
                print(f"{self._config.botname}: ", end="", flush=True)

            try:
                for delta in self._ai.stream_response_deltas(user_input):
                    full_parts.append(delta)
                    if self._config.debug:
                        print(delta, end="", flush=True)

                    # Stop immediately on barge-in (user is starting a new request).
                    if barge_in_event and barge_in_event.is_set():
                        break

                    # If playback is interrupted (player failure), keep collecting deltas so
                    # the text fallback can still print a full response, but stop producing audio.
                    if interrupt_event.is_set():
                        continue

                    if production_failed_event.is_set():
                        continue

                    buffer += delta
                    while not stop_event.is_set():
                        min_chars = first_min_chars if is_first else next_min_chars
                        chunk, buffer = self._pop_chunk_fn(buffer, boundary=boundary, min_chars=min_chars)
                        if chunk is None:
                            break
                        is_first = False
                        if not _put_text_queue(chunk):
                            interrupt_event.set()
                            break

                else:
                    stream_completed = True
                    if self._config.debug:
                        print()  # terminate the debug delta line

            except Exception as e:
                interrupt_event.set()
                if self._config.debug:
                    print()
                print(handle_api_error(e, service_name="OpenAI GPT (streaming)"))

            # If LLM streaming did not complete, remove the last user turn to avoid dangling history.
            if not stream_completed:
                try:
                    last_user = "User: " + user_input
                    if getattr(self._ai, "conversation_history", None) and self._ai.conversation_history[-1] == last_user:
                        self._ai.conversation_history.pop()
                except Exception:
                    pass

            if stream_completed and (not production_failed_event.is_set()) and (not stop_event.is_set()):
                final_chunk = buffer.strip()
                if final_chunk:
                    if not _put_text_queue(final_chunk):
                        interrupt_event.set()

        # Always attempt to enqueue sentinel to allow TTS worker to exit.
        sentinel_enqueued = _put_text_queue(None, allow_when_stopped=True)
        if not sentinel_enqueued:
            logger.warning("Failed to enqueue wake-word streaming sentinel")
            interrupt_event.set()

        tts_join_timeout = 30
        player_join_timeout = 60
        tts_thread.join(timeout=tts_join_timeout)
        player_thread.join(timeout=player_join_timeout)

        if tts_thread.is_alive():
            logger.warning(
                "Wake-word streaming TTS thread did not exit within %s seconds",
                tts_join_timeout,
            )
        if player_thread.is_alive():
            logger.warning(
                "Wake-word streaming player thread did not exit within %s seconds",
                player_join_timeout,
            )

        response_text_assembled = "".join(full_parts).strip()
        # Print final text (unless we are in debug mode or barge-in occurred)
        if response_text_assembled and not self._config.debug:
            if not (barge_in_event and barge_in_event.is_set()):
                if self._ui is not None:
                    self._ui.print_exchange(self._config.botname, response_text_assembled)
                else:
                    print(f"{self._config.botname}: {response_text_assembled}\n")

        if production_failed_event.is_set() and tts_error[0]:
            logger.warning("Wake-word streaming TTS production failed: %s", tts_error[0])

        if not player_success[0]:
            if barge_in_event and barge_in_event.is_set():
                # Expected interruption; avoid logging as a playback failure.
                pass
            else:
                logger.warning(
                    "Wake-word streaming audio playback failed for file '%s': %s",
                    player_failed_file[0], player_error[0]
                )
