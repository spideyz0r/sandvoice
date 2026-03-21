import logging
import struct
import threading
import time

import pvporcupine
import pyaudio

logger = logging.getLogger(__name__)

# Sentinel returned by run_with_polling when barge-in interrupted the operation.
_BARGE_IN = object()


class BargeInDetector:
    """Encapsulates barge-in detection using Porcupine wake-word engine.

    Runs a background thread that listens for the wake word while other
    operations are in progress (e.g. TTS playback, API calls). When the
    wake word is detected the internal event is set; callers poll
    ``is_triggered`` or use ``run_with_polling`` to react.

    Usage::

        detector = BargeInDetector(
            access_key=..., keyword_paths=..., sensitivity=...,
            audio_lock=..., audio=..., config=...
        )
        detector.start()
        result = detector.run_with_polling(my_op, "my op")
        if result is _BARGE_IN:
            handle_barge_in()
        detector.stop()
    """

    def __init__(self, access_key, keyword_paths, sensitivity, audio_lock, audio, config):
        """Initialise the detector.

        Args:
            access_key: Porcupine access key string.
            keyword_paths: List of .ppn file paths, or None to use built-in
                keywords derived from ``config.wake_phrase``.
            sensitivity: Float sensitivity for wake-word detection (0.0–1.0).
            audio_lock: threading.Lock (or None) acquired around playback
                calls inside the host WakeWordMode.  Not used by the detector
                itself; stored so callers can pass it along if needed.
            audio: Audio instance (stored for future use; not used internally).
            config: Config instance; used to read ``wake_phrase`` when
                creating Porcupine instances with built-in keywords.
        """
        self._access_key = access_key
        self._keyword_paths = keyword_paths
        self._sensitivity = sensitivity
        self._audio_lock = audio_lock
        self._audio = audio
        self._config = config

        self._event = threading.Event()       # set when wake word detected
        self._stop_flag = threading.Event()   # set to signal thread to stop
        self._thread = None                   # background detection thread

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self):
        """Start background detection thread.  No-op if already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._event.clear()
        self._thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
        )
        self._thread.start()
        logger.debug("Barge-in detection started")

    def stop(self, timeout=0.3):
        """Signal thread to stop, join it, then reset internal state.

        Args:
            timeout: Seconds to wait for the thread to exit.  Pass 0 for a
                non-blocking stop (signal only, no join).
        """
        self._stop_flag.set()
        thread = self._thread
        if thread is None:
            logger.debug("Barge-in detection stop requested, but no thread is running")
            return
        if timeout != 0 and thread.is_alive():
            try:
                thread.join(timeout=timeout)
            except RuntimeError:
                pass
        if not thread.is_alive():
            self._thread = None
            self._stop_flag.clear()
            self._event.clear()
            logger.debug("Barge-in detection stopped")
        else:
            logger.debug("Barge-in detection stop requested, but thread is still running")

    def clear(self):
        """Reset the triggered flag (re-arm for next detection cycle)."""
        self._event.clear()

    @property
    def is_triggered(self):
        """True if the barge-in wake word has been detected."""
        return self._event.is_set()

    @property
    def event(self):
        """The threading.Event that is set when barge-in is detected."""
        return self._event

    def run_with_polling(self, operation, name):
        """Run *operation* in a background thread, polling for barge-in every 50 ms.

        If barge-in is detected before or during the operation, returns
        ``_BARGE_IN`` immediately without waiting for the operation to finish.
        The operation continues running as a daemon thread and its result is
        discarded (see note on side effects in the original implementation).

        Note: Operations with side effects (e.g., AI conversation history
        updates, plugin actions) will still complete even after barge-in. This
        is acceptable because barge-in is primarily about responsiveness, not
        transaction rollback.

        Args:
            operation: Zero-argument callable to run.
            name: Human-readable name used in log messages.

        Returns:
            Operation result, or ``_BARGE_IN`` sentinel if interrupted.
        """
        # If barge-in is already active, skip starting the operation.
        if self.is_triggered:
            logger.debug("Barge-in already active before starting %s - skipping", name)
            return _BARGE_IN

        result_holder = [None]
        error_holder = [None]

        def run_in_background():
            try:
                result_holder[0] = operation()
            except Exception as e:
                error_holder[0] = e
                # Log at DEBUG only — if no barge-in, the error is re-raised below;
                # a WARNING here would duplicate it.
                logger.debug("Background %s failed: %s", name, e)

        thread = threading.Thread(target=run_in_background, daemon=True)
        thread.start()

        # Poll every 50 ms for completion or barge-in.
        poll_count = 0
        while thread.is_alive():
            if self.is_triggered:
                logger.debug("Barge-in during %s - responding immediately!", name)
                return _BARGE_IN
            time.sleep(0.05)
            poll_count += 1
            if logger.isEnabledFor(logging.DEBUG) and poll_count % 40 == 0:
                try:
                    import pygame
                    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                        logger.debug(
                            ">>> UNEXPECTED: Audio is playing during %s polling!", name
                        )
                except Exception:
                    pass

        # Operation completed — re-raise any error.
        if error_holder[0] is not None:
            raise error_holder[0]

        return result_holder[0]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create_porcupine_instance(self):
        """Create a fresh Porcupine instance for this thread."""
        if self._keyword_paths:
            paths = self._keyword_paths
            if not isinstance(paths, (list, tuple)):
                paths = [paths]
            sensitivities = [self._sensitivity] * len(paths)
            return pvporcupine.create(
                access_key=self._access_key,
                keyword_paths=paths,
                sensitivities=sensitivities,
            )
        else:
            wake_keyword = self._config.wake_phrase.lower()
            return pvporcupine.create(
                access_key=self._access_key,
                keywords=[wake_keyword],
                sensitivities=[self._sensitivity],
            )

    def _cleanup_pyaudio(self, stream, pa):
        """Stop and close a PyAudio stream, then terminate the PyAudio instance."""
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception as e:
                logger.debug("Failed to stop PyAudio stream: %s", e)
            try:
                stream.close()
            except Exception as e:
                logger.debug("Failed to close PyAudio stream: %s", e)
        if pa is not None:
            try:
                pa.terminate()
            except Exception as e:
                logger.debug("Failed to terminate PyAudio instance: %s", e)

    def _detection_loop(self):
        """Background thread body: listen for barge-in wake word.

        Creates its own Porcupine instance to avoid thread-safety issues with
        the main Porcupine instance used in IDLE state.
        """
        porcupine_instance = None
        pa = None
        audio_stream = None

        try:
            logger.debug("Barge-in thread: Creating Porcupine instance...")
            porcupine_instance = self._create_porcupine_instance()
            logger.debug("Barge-in thread: Porcupine created successfully")

            logger.debug("Barge-in thread: Opening PyAudio stream...")
            pa = pyaudio.PyAudio()
            audio_stream = pa.open(
                rate=porcupine_instance.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=porcupine_instance.frame_length,
            )

            logger.debug("Barge-in thread: Audio stream opened, listening for wake word...")

            while not self._event.is_set() and not self._stop_flag.is_set():
                try:
                    pcm = audio_stream.read(
                        porcupine_instance.frame_length,
                        exception_on_overflow=False,
                    )
                    pcm = struct.unpack_from("h" * porcupine_instance.frame_length, pcm)

                    keyword_index = porcupine_instance.process(pcm)

                    if keyword_index >= 0:
                        logger.info("Barge-in: Wake word detected! Interrupting...")
                        self._event.set()
                        break

                except Exception as e:
                    logger.warning("Barge-in thread error reading audio: %s", e)
                    break

        except Exception as e:
            logger.error("Barge-in detection thread error: %s", e)
        finally:
            self._cleanup_pyaudio(audio_stream, pa)
            if porcupine_instance is not None:
                try:
                    porcupine_instance.delete()
                except Exception as e:
                    logger.warning("Failed to delete barge-in Porcupine instance: %s", e)
