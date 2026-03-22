import contextlib
import logging
import os
import struct
import threading
from enum import Enum

import pvporcupine
import pyaudio

from common.beep_generator import create_confirmation_beep, create_ack_earcon
from common.ai import pop_streaming_chunk
from common.barge_in import BargeInDetector, _BARGE_IN
from common.streaming_responder import StreamingResponder
from common.vad_recorder import VadRecorder
from common.utils import _is_enabled_flag

logger = logging.getLogger(__name__)


class State(Enum):
    """Wake word mode states."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"


class WakeWordMode:
    """Wake word mode with state machine for hands-free interaction.

    States:
    - IDLE: Listening for wake word using Porcupine
    - LISTENING: Recording user command with VAD
    - PROCESSING: Transcribing and routing to plugin
    - RESPONDING: Playing TTS response

    Returns to IDLE after each cycle.
    """

    def __init__(self, config, ai_instance, audio_instance, route_message, plugins=None, audio_lock=None):
        """Initialize wake word mode.

        Args:
            config: Configuration object with wake word settings
            ai_instance: AI instance for transcription and responses
            audio_instance: Audio instance for playback
            route_message: Required callback to route messages through SandVoice plugins.
                Signature: route_message(user_input: str, route: dict) -> str
            plugins: Optional dict of plugin route handlers (used to decide when "default route"
                streaming is safe). If not provided, wake word mode will not attempt streaming
                for routed requests.
            audio_lock: Optional threading.Lock (or compatible) acquired around every
                audio playback call to serialize mixer usage with other threads (e.g.,
                the scheduler's TTS output). If None, no external locking is applied.
        """
        if route_message is None:
            raise ValueError("route_message is required for wake-word mode")
        self.config = config
        self.ai = ai_instance
        self.audio = audio_instance
        self.route_message = route_message
        self.plugins = plugins
        self._audio_lock = audio_lock
        self.state = State.IDLE
        self.running = False

        self.porcupine = None
        self.confirmation_beep_path = None
        self.ack_earcon_path = None
        self.recorded_audio_path = None
        self.response_text = None
        self.streaming_user_input = None
        self.streaming_response_text = None  # Pre-computed plugin response for TTS
        self.barge_in = None  # BargeInDetector instance (created in _initialize)
        self.vad_recorder = None  # VadRecorder instance (created in _initialize)
        self.responder = None  # StreamingResponder instance (created in _initialize)

        logger.debug("Initializing wake word mode")

    def run(self):
        """Main event loop. Runs until user exits with Ctrl+C.

        Manages state machine transitions:
        IDLE → LISTENING → PROCESSING → RESPONDING → IDLE
        """
        logger.info("Starting wake word mode")

        self.running = True

        try:
            self._initialize()

            while self.running:
                if self.state == State.IDLE:
                    self._state_idle()
                elif self.state == State.LISTENING:
                    self._state_listening()
                elif self.state == State.PROCESSING:
                    self._state_processing()
                elif self.state == State.RESPONDING:
                    self._state_responding()
        except KeyboardInterrupt:
            if self.config.visual_state_indicator:
                print("\n👋 Exiting wake word mode...")
        finally:
            self._cleanup()

    def _initialize(self):
        """Initialize Porcupine, VAD, and confirmation beep.

        Raises:
            RuntimeError: If Porcupine access key is missing or invalid; if any of
                vad_enabled, bot_voice, stream_responses, or stream_tts is
                disabled; or if the Porcupine instance cannot be created.
        """
        logger.debug("Initializing wake word detection and VAD")

        if not self.config.porcupine_access_key:
            error_msg = (
                "Porcupine access key is required for wake word mode. "
                "Get your free key at https://console.picovoice.ai/ and add it to your config: "
                "porcupine_access_key: YOUR_KEY_HERE"
            )
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

        self._require_config_enabled(
            getattr(self.config, "vad_enabled", False),
            "Wake-word mode requires VAD-based recording. "
            "Enable it in your config: vad_enabled: enabled",
        )
        self._require_config_enabled(
            getattr(self.config, "bot_voice", False),
            "Wake-word mode requires voice output to be enabled. "
            "Enable it in your config: bot_voice: enabled",
        )
        self._require_config_enabled(
            getattr(self.config, "stream_responses", False),
            "Wake-word mode requires streaming responses. "
            "Enable it in your config: stream_responses: enabled",
        )
        self._require_config_enabled(
            getattr(self.config, "stream_tts", False),
            "Wake-word mode requires streaming TTS. "
            "Enable it in your config: stream_tts: enabled",
        )

        try:
            keyword_paths = getattr(self.config, "porcupine_keyword_paths", None)

            if not keyword_paths:
                wake_keyword = self.config.wake_phrase.lower()

                if hasattr(pvporcupine, "KEYWORDS") and wake_keyword not in pvporcupine.KEYWORDS:
                    supported = ", ".join(sorted(pvporcupine.KEYWORDS)) if hasattr(pvporcupine, "KEYWORDS") else "unknown"
                    error_msg = (
                        f"Invalid Porcupine wake phrase '{self.config.wake_phrase}'. "
                        f"When using built-in keywords, wake_phrase must be one of: {supported}. "
                        "For a custom wake phrase, create a .ppn model at https://console.picovoice.ai/ "
                        "and configure its path via 'porcupine_keyword_paths' in your config."
                    )
                    logger.error(error_msg)
                    print(f"Error: {error_msg}")
                    raise RuntimeError(error_msg)

            # Create main Porcupine instance
            self.porcupine = self._create_porcupine_instance()

            if keyword_paths:
                logger.debug("Porcupine initialized with custom keyword paths: %s", keyword_paths)
            else:
                logger.debug("Porcupine initialized with built-in wake phrase: '%s'", self.config.wake_phrase)

            logger.debug("Porcupine sample rate: %s", self.porcupine.sample_rate)
            logger.debug("Porcupine frame length: %s", self.porcupine.frame_length)

            # Create barge-in detector now that config is validated.
            self.barge_in = BargeInDetector(
                access_key=self.config.porcupine_access_key,
                keyword_paths=getattr(self.config, "porcupine_keyword_paths", None),
                sensitivity=self.config.wake_word_sensitivity,
                audio_lock=self._audio_lock,
                audio=self.audio,
                config=self.config,
            )

        except RuntimeError:
            raise
        except Exception as e:
            error_msg = f"Failed to initialize wake-word mode: {str(e)}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

        if self.config.wake_confirmation_beep:
            try:
                self.confirmation_beep_path = create_confirmation_beep(
                    freq=self.config.wake_confirmation_beep_freq,
                    duration=self.config.wake_confirmation_beep_duration,
                    tmp_path=self.config.tmp_files_path
                )
                logger.debug("Confirmation beep created at: %s", self.confirmation_beep_path)
            except Exception as e:
                logger.warning("Failed to create confirmation beep: %s", e)
                self.confirmation_beep_path = None

        if _is_enabled_flag(getattr(self.config, "voice_ack_earcon", False)):
            try:
                self.ack_earcon_path = create_ack_earcon(
                    freq=self.config.voice_ack_earcon_freq,
                    duration=self.config.voice_ack_earcon_duration,
                    tmp_path=self.config.tmp_files_path,
                )
                logger.debug("Ack earcon created at: %s", self.ack_earcon_path)
            except Exception as e:
                logger.warning("Failed to create ack earcon: %s", e)
                self.ack_earcon_path = None

        self.vad_recorder = VadRecorder(
            self.config, self.audio, self._audio_lock,
            ack_earcon_path=self.ack_earcon_path,
        )

        self.responder = StreamingResponder(
            self.ai, self.audio, self._audio_lock, self.barge_in,
            pop_streaming_chunk, self.config,
        )

    def _create_porcupine_instance(self):
        """Create a new Porcupine instance with current config.

        Returns:
            Porcupine instance

        Raises:
            RuntimeError: If initialization fails
        """
        keyword_paths = getattr(self.config, "porcupine_keyword_paths", None)

        if keyword_paths:
            if not isinstance(keyword_paths, (list, tuple)):
                keyword_paths = [keyword_paths]

            base_sensitivity = self.config.wake_word_sensitivity
            sensitivities = [base_sensitivity] * len(keyword_paths)

            return pvporcupine.create(
                access_key=self.config.porcupine_access_key,
                keyword_paths=keyword_paths,
                sensitivities=sensitivities
            )
        else:
            wake_keyword = self.config.wake_phrase.lower()

            return pvporcupine.create(
                access_key=self.config.porcupine_access_key,
                keywords=[wake_keyword],
                sensitivities=[self.config.wake_word_sensitivity]
            )

    def _require_config_enabled(self, flag_value, error_msg):
        """Raise RuntimeError if flag_value is not considered enabled by _is_enabled_flag()."""
        if not _is_enabled_flag(flag_value):
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

    def _remove_recorded_audio(self):
        """Remove the temporary recorded audio file if it exists and clear the path."""
        if not self.recorded_audio_path:
            return
        if os.path.exists(self.recorded_audio_path):
            try:
                os.remove(self.recorded_audio_path)
            except OSError as e:
                logger.debug("Failed to remove recorded audio '%s': %s", self.recorded_audio_path, e)
        self.recorded_audio_path = None

    def _state_idle(self):
        """IDLE state: Listen for wake word using Porcupine.

        Listens for wake word in a blocking loop until detected.
        Plays confirmation beep and transitions to LISTENING.
        """
        if self.config.visual_state_indicator:
            print(f"⏸️  Waiting for wake word ('{self.config.wake_phrase}')...")

        pa = None
        audio_stream = None

        try:
            pa = pyaudio.PyAudio()
            audio_stream = pa.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )

            while self.running and self.state == State.IDLE:
                pcm = audio_stream.read(self.porcupine.frame_length, exception_on_overflow=False)
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)

                keyword_index = self.porcupine.process(pcm)

                if keyword_index >= 0:
                    logger.info("Wake word detected: '%s'", self.config.wake_phrase)

                    self._play_confirmation_beep()

                    self.state = State.LISTENING
                    break

        except Exception as e:
            error_msg = f"Wake word detection error: {str(e)}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")
            self.running = False
        finally:
            self._cleanup_pyaudio(audio_stream, pa)

    def _state_listening(self):
        """LISTENING state: Record audio with VAD until silence detected.

        Records audio frames and runs VAD to detect end of speech.
        Saves recording and transitions to PROCESSING.
        """
        if self.config.visual_state_indicator:
            print("🎤 Listening...")

        if self.config.debug:
            self.audio.log_mixer_state("LISTENING state entered")

        try:
            self.recorded_audio_path = self.vad_recorder.record()
            if self.recorded_audio_path:
                self.state = State.PROCESSING
            else:
                logger.warning("No audio recorded, returning to IDLE")
                self.state = State.IDLE
        except Exception as e:
            error_msg = f"Recording error: {str(e)}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")
            self.recorded_audio_path = None
            self.state = State.IDLE

    def _handle_immediate_barge_in(self):
        """Handle barge-in with immediate beep and transition to LISTENING."""
        logger.info("=== BARGE-IN TRIGGERED === Current state: %s", self.state.name)
        if self.config.debug:
            self.audio.log_mixer_state("barge-in BEFORE stop")

        # Immediately stop any audio and do full reset to prevent any cached audio from playing
        self.audio.stop_playback(full_reset=True)

        if self.config.debug:
            self.audio.log_mixer_state("barge-in AFTER stop")

        # Signal barge-in thread to stop and give it a brief chance to clean up
        # Short timeout to allow PyAudio stream to close before LISTENING reopens it
        self._cleanup_barge_in(timeout=0.3)

        # Clean up any partial data
        self._remove_recorded_audio()
        self._reset_streaming_state()

        # Play confirmation beep
        self._play_confirmation_beep()

        # Go directly to LISTENING
        self.state = State.LISTENING

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

    def _cleanup_barge_in(self, timeout=0.3):
        """Signal barge-in detector to stop and wait briefly for cleanup."""
        if self.barge_in is not None:
            self.barge_in.stop(timeout=timeout)

    def _play_confirmation_beep(self):
        """Play confirmation beep if configured and the file exists."""
        if not (getattr(self.config, "wake_confirmation_beep", False) and self.confirmation_beep_path):
            return
        if not os.path.exists(self.confirmation_beep_path):
            return
        try:
            with (self._audio_lock or contextlib.nullcontext()):
                self.audio.play_audio_file(self.confirmation_beep_path)
        except Exception as e:
            logger.warning("Failed to play confirmation beep: %s", e)

    def _reset_streaming_state(self):
        """Clear response and streaming state fields in preparation for the next cycle."""
        self.response_text = None
        self.streaming_response_text = None
        self.streaming_user_input = None

    def _poll_op(self, operation, name):
        """Run *operation* with barge-in polling.

        Delegates to ``self.barge_in.run_with_polling``.  If barge-in
        interrupts, calls _handle_immediate_barge_in and returns the
        _BARGE_IN sentinel so callers can early-return without further logic.
        Otherwise returns the operation result directly.
        """
        if self.barge_in is None:
            raise RuntimeError("Barge-in detector is not initialized; ensure _initialize() has been called")
        result = self.barge_in.run_with_polling(operation, name)
        if result is _BARGE_IN:
            self._handle_immediate_barge_in()
            return _BARGE_IN
        return result

    def _state_processing(self):
        """PROCESSING state: Transcribe audio and generate response.

        Uses existing AI methods for transcription, routing, and response.
        Supports barge-in: can be interrupted at any step by wake word detection.
        Transitions to RESPONDING or LISTENING (if interrupted).
        """
        if self.config.visual_state_indicator:
            print("🤔 Processing...")

        # Debug: Check if any audio is unexpectedly playing when we enter PROCESSING
        if self.config.debug:
            self.audio.log_mixer_state("PROCESSING state entered")

        # Reset response data
        self._reset_streaming_state()

        # Check if we have a recorded audio file before starting barge-in detection
        if not self.recorded_audio_path or not os.path.exists(self.recorded_audio_path):
            logger.warning("No recorded audio file found, returning to IDLE")
            self.recorded_audio_path = None
            self.state = State.IDLE
            return

        # Start barge-in detection (runs through PROCESSING and RESPONDING)
        if self.barge_in is None:
            raise RuntimeError("Barge-in detector is not initialized; ensure _initialize() has been called")
        self.barge_in.start()

        try:
            # Capture path locally to avoid race with barge-in clearing self.recorded_audio_path
            audio_path = self.recorded_audio_path

            # Transcribe the audio
            logger.debug("Transcribing audio from: %s", audio_path)
            user_input = self._poll_op(
                lambda: self.ai.transcribe_and_translate(audio_file_path=audio_path),
                "transcription",
            )
            if user_input is _BARGE_IN:
                return

            logger.debug("Transcription: %s", user_input)
            print(f"You: {user_input}")

            # Check for barge-in before starting response generation
            if self.barge_in.is_triggered:
                logger.debug("Barge-in detected after transcription, before response generation")
                self._handle_immediate_barge_in()
                return

            # Generate response via plugin routing
            route = self._poll_op(
                lambda: self.ai.define_route(user_input),
                "route definition",
            )
            if route is _BARGE_IN:
                return

            logger.debug("Route: %s", route)

            stream_default_route = (
                (self.plugins is not None)
                and (route.get("route") not in self.plugins)
            )

            if stream_default_route:
                self.streaming_user_input = user_input
                self.response_text = None

                if self.barge_in.is_triggered:
                    logger.debug("Barge-in detected after route definition, before streaming")
                    self._handle_immediate_barge_in()
                    return

                self.state = State.RESPONDING
                return

            response_text = self._poll_op(
                lambda: self.route_message(user_input, route),
                "plugin response",
            )
            if response_text is _BARGE_IN:
                return

            self.response_text = response_text
            self.streaming_response_text = response_text

            logger.debug("Response: %s", self.response_text)
            print(f"{self.config.botname}: {self.response_text}\n")

            # Final barge-in check before transitioning to RESPONDING
            if self.barge_in.is_triggered:
                logger.debug("Barge-in detected after processing completed, before RESPONDING")
                self._handle_immediate_barge_in()
                return

            # Transition to RESPONDING state (barge-in detector continues running)
            logger.debug("=== TRANSITIONING TO RESPONDING ===")
            if self.config.debug:
                self.audio.log_mixer_state("BEFORE RESPONDING transition")
            self.state = State.RESPONDING

        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")

            # Clean up recorded audio file on error
            self._remove_recorded_audio()

            # Stop barge-in detector
            self._cleanup_barge_in(timeout=1.0)
            self._reset_streaming_state()

            # Return to IDLE on error
            self.state = State.IDLE

    def _state_responding(self):
        """RESPONDING state: Play streaming TTS response.

        Streaming TTS is the only playback path in wake-word mode.
        Barge-in thread may already be running from PROCESSING state.
        Transitions back to IDLE or LISTENING (if barge-in).
        """
        logger.debug("=== ENTERING RESPONDING === thread=%s", threading.current_thread().name)

        if self.config.visual_state_indicator:
            print("🔊 Responding...")

        if self.streaming_user_input is not None or self.streaming_response_text is not None:
            self._respond_streaming()

        # Signal barge-in detector to stop and wait for it to finish
        # Wait for thread to finish to ensure PyAudio stream is closed before LISTENING reopens it
        barge_in_triggered = self.barge_in is not None and self.barge_in.is_triggered
        self._cleanup_barge_in(timeout=0.3)

        # Clean up temporary recorded audio file
        self._remove_recorded_audio()

        # Reset for next cycle
        self.response_text = None

        # Transition to LISTENING if barge-in occurred, otherwise back to IDLE
        if barge_in_triggered:
            logger.debug("Transitioning to LISTENING after barge-in")

            # Play confirmation beep (consistent with _handle_immediate_barge_in)
            self._play_confirmation_beep()

            self.state = State.LISTENING
        else:
            self.state = State.IDLE

    def _respond_streaming(self):
        """Streaming TTS response path for LLM and plugin responses.

        For LLM default-route responses: streams deltas from ai.stream_response_deltas,
        chunks them, converts to audio via TTS worker, and plays via player worker —
        all concurrently.

        For pre-computed plugin responses (streaming_response_text set): enqueues the
        text directly to the TTS worker, bypassing LLM streaming.

        Delegates to StreamingResponder.respond(). Barge-in cleanup and state
        transition remain in _state_responding.
        """
        user_input = self.streaming_user_input
        self.streaming_user_input = None
        precomputed_text = self.streaming_response_text
        self.streaming_response_text = None

        # Ensure barge-in detection is running (always required in wake-word mode)
        self.barge_in.start()  # no-op if already running

        self.responder.respond(user_input, precomputed_text)

        # Reset streaming metadata
        self._reset_streaming_state()

    def _cleanup(self):
        """Clean up Porcupine, VAD, barge-in thread, and audio resources."""
        logger.info("Cleaning up wake word mode")

        # Clean up barge-in thread if running
        self._cleanup_barge_in(timeout=0.5)

        if self.porcupine is not None:
            try:
                self.porcupine.delete()
            except Exception as e:
                logger.warning("Failed to delete Porcupine instance: %s", e)
            finally:
                self.porcupine = None

        self.running = False
