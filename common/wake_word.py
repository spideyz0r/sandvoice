import contextlib
import logging
import os
import queue
import struct
import threading
import time
import wave
from enum import Enum

import pvporcupine
import pyaudio
import webrtcvad

from common.beep_generator import create_confirmation_beep, create_ack_earcon
from common.ai import pop_streaming_chunk
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


# Sentinel returned by _poll_op when barge-in interrupted the operation.
_BARGE_IN = object()


def _is_enabled_flag(value):
    """Interpret common enabled/disabled flag representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"enabled", "true", "yes", "1", "on"}:
            return True
        if normalized in {"disabled", "false", "no", "0", "off"}:
            return False
        return False
    if isinstance(value, int):
        return value != 0
    # For unknown types (e.g. mocks), default to disabled to avoid accidental enablement.
    return False


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

    def __init__(self, config, ai_instance, audio_instance, route_message=None, plugins=None, audio_lock=None):
        """Initialize wake word mode.

        Args:
            config: Configuration object with wake word settings
            ai_instance: AI instance for transcription and responses
            audio_instance: Audio instance for playback
            route_message: Optional callback to route messages through SandVoice plugins.
                Signature: route_message(user_input: str, route: dict) -> str
            plugins: Optional dict of plugin route handlers (used to decide when "default route"
                streaming is safe). If not provided, wake word mode will not attempt streaming
                for routed requests.
            audio_lock: Optional threading.Lock (or compatible) acquired around every
                audio playback call to serialize mixer usage with other threads (e.g.,
                the scheduler's TTS output). If None, no external locking is applied.
        """
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
        self.streaming_route = None
        self.streaming_response_text = None  # Pre-computed plugin response for TTS
        self.barge_in_event = None  # Event to signal barge-in during TTS
        self.barge_in_stop_flag = None  # Flag to stop barge-in thread immediately
        self.barge_in_thread = None  # Thread for barge-in detection

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

        if not _is_enabled_flag(getattr(self.config, "vad_enabled", False)):
            error_msg = (
                "Wake-word mode requires VAD-based recording. "
                "Enable it in your config: vad_enabled: enabled"
            )
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

        if not _is_enabled_flag(getattr(self.config, "bot_voice", False)):
            error_msg = (
                "Wake-word mode requires voice output to be enabled. "
                "Enable it in your config: bot_voice: enabled"
            )
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

        if not _is_enabled_flag(getattr(self.config, "stream_responses", False)):
            error_msg = (
                "Wake-word mode requires streaming responses. "
                "Enable it in your config: stream_responses: enabled"
            )
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

        if not _is_enabled_flag(getattr(self.config, "stream_tts", False)):
            error_msg = (
                "Wake-word mode requires streaming TTS. "
                "Enable it in your config: stream_tts: enabled"
            )
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

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

        except RuntimeError:
            raise
        except Exception as e:
            error_msg = f"Failed to initialize Porcupine: {str(e)}"
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

        if _is_enabled_flag(getattr(self.config, "bot_voice", False)) and _is_enabled_flag(
            getattr(self.config, "voice_ack_earcon", False)
        ):
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

                    if self.config.wake_confirmation_beep and self.confirmation_beep_path:
                        try:
                            with (self._audio_lock or contextlib.nullcontext()):
                                self.audio.play_audio_file(self.confirmation_beep_path)
                        except Exception as e:
                            logger.warning("Failed to play confirmation beep: %s", e)

                    self.state = State.LISTENING
                    break

        except Exception as e:
            error_msg = f"Wake word detection error: {str(e)}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")
            self.running = False
        finally:
            if audio_stream is not None:
                try:
                    audio_stream.stop_stream()
                    audio_stream.close()
                except Exception as e:
                    logger.warning("Failed to close audio stream: %s", e)
            if pa is not None:
                try:
                    pa.terminate()
                except Exception as e:
                    logger.warning("Failed to terminate PyAudio: %s", e)

    def _state_listening(self):
        """LISTENING state: Record audio with VAD until silence detected.

        Records audio frames and runs VAD to detect end of speech.
        Saves recording and transitions to PROCESSING.
        """
        if self.config.visual_state_indicator:
            print("🎤 Listening...")

        # Debug: Check if any audio is unexpectedly playing when we enter LISTENING
        if self.config.debug:
            self.audio.log_mixer_state("LISTENING state entered")

        # Initialize VAD
        vad = webrtcvad.Vad(self.config.vad_aggressiveness)

        # Audio parameters
        sample_rate = self.config.rate
        frame_duration_ms = self.config.vad_frame_duration

        # VAD requires 16-bit PCM audio at 8kHz, 16kHz, 32kHz, or 48kHz
        # If config.rate doesn't match, we need to handle it
        vad_sample_rates = [8000, 16000, 32000, 48000]
        if sample_rate not in vad_sample_rates:
            # Find closest supported rate
            vad_sample_rate = min(vad_sample_rates, key=lambda x: abs(x - sample_rate))
            logger.debug("VAD requires specific sample rates. Using %sHz instead of %sHz", vad_sample_rate, sample_rate)
        else:
            vad_sample_rate = sample_rate

        # Recalculate frame size for VAD sample rate
        vad_frame_size = int(vad_sample_rate * frame_duration_ms / 1000)

        pa = None
        audio_stream = None
        frames = []
        silence_start = None
        recording_start = time.time()

        try:
            pa = pyaudio.PyAudio()
            audio_stream = pa.open(
                rate=vad_sample_rate,
                channels=1,  # VAD requires mono
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=vad_frame_size
            )

            logger.debug("Recording with VAD: %sHz, frame_duration=%sms", vad_sample_rate, frame_duration_ms)

            while self.running and self.state == State.LISTENING:
                # Check timeout
                elapsed = time.time() - recording_start
                if elapsed > self.config.vad_timeout:
                    logger.debug("VAD timeout reached (%ss)", self.config.vad_timeout)
                    break

                # Read audio frame
                try:
                    pcm = audio_stream.read(vad_frame_size, exception_on_overflow=False)
                except Exception as e:
                    logger.error("Error reading audio frame: %s", e)
                    break

                frames.append(pcm)

                # Run VAD on frame
                try:
                    is_speech = vad.is_speech(pcm, vad_sample_rate)
                except Exception as e:
                    logger.warning("VAD processing error: %s", e)
                    is_speech = True  # Assume speech on error

                if is_speech:
                    # Reset silence timer
                    silence_start = None
                else:
                    # Track silence duration
                    if silence_start is None:
                        silence_start = time.time()
                    else:
                        silence_duration = time.time() - silence_start
                        if silence_duration >= self.config.vad_silence_duration:
                            logger.debug("Silence detected (%.2fs)", silence_duration)
                            break

            # Save recorded audio to temporary WAV file
            if frames:
                # Calculate final recording duration
                elapsed = time.time() - recording_start

                # Capture audio format info before we terminate PyAudio
                sample_width = None
                try:
                    sample_width = pa.get_sample_size(pyaudio.paInt16)
                except Exception as e:
                    logger.warning("Failed to get sample width: %s", e)
                    sample_width = 2  # 16-bit PCM

                # Close input stream before playing any earcons (improves compatibility on some devices)
                if audio_stream is not None:
                    try:
                        audio_stream.stop_stream()
                        audio_stream.close()
                    except Exception as e:
                        logger.warning("Failed to close audio stream: %s", e)
                    audio_stream = None

                if pa is not None:
                    try:
                        pa.terminate()
                    except Exception as e:
                        logger.warning("Failed to terminate PyAudio: %s", e)
                    pa = None

                self.recorded_audio_path = os.path.join(
                    self.config.tmp_files_path,
                    f"wake_word_recording_{int(time.time())}.wav"
                )

                # Ensure tmp directory exists
                os.makedirs(self.config.tmp_files_path, exist_ok=True)

                # Write WAV file
                try:
                    with wave.open(self.recorded_audio_path, 'wb') as wf:
                        wf.setnchannels(1)  # Mono
                        wf.setsampwidth(sample_width)
                        wf.setframerate(vad_sample_rate)
                        wf.writeframes(b''.join(frames))
                except Exception:
                    try:
                        if self.recorded_audio_path and os.path.exists(self.recorded_audio_path):
                            os.remove(self.recorded_audio_path)
                    finally:
                        self.recorded_audio_path = None
                    raise

                logger.debug("Recorded audio saved: %s", self.recorded_audio_path)
                logger.debug("Recording duration: %.2fs, %s frames", elapsed, len(frames))

                # Voice UX: play a short ack earcon before PROCESSING begins
                if _is_enabled_flag(getattr(self.config, "bot_voice", False)) and _is_enabled_flag(
                    getattr(self.config, "voice_ack_earcon", False)
                ):
                    if self.ack_earcon_path and os.path.exists(self.ack_earcon_path):
                        try:
                            audio_playing = False
                            is_playing_fn = getattr(self.audio, "is_playing", None)
                            if callable(is_playing_fn):
                                audio_playing = bool(is_playing_fn())

                            if not audio_playing:
                                with (self._audio_lock or contextlib.nullcontext()):
                                    self.audio.play_audio_file(self.ack_earcon_path)
                            else:
                                logger.debug("Skipping ack earcon: audio is already playing")
                        except Exception as e:
                            logger.warning("Failed to play ack earcon: %s", e)

                self.state = State.PROCESSING
            else:
                logger.warning("No audio recorded, returning to IDLE")
                self.state = State.IDLE

        except Exception as e:
            error_msg = f"Recording error: {str(e)}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")
            self.state = State.IDLE
        finally:
            if audio_stream is not None:
                try:
                    audio_stream.stop_stream()
                    audio_stream.close()
                except Exception as e:
                    logger.warning("Failed to close audio stream: %s", e)
            if pa is not None:
                try:
                    pa.terminate()
                except Exception as e:
                    logger.warning("Failed to terminate PyAudio: %s", e)

    def _start_barge_in_detection(self):
        """Start barge-in detection thread.

        Returns:
            threading.Thread: The barge-in detection thread.

        Raises:
            RuntimeError: If Porcupine is not initialized (invariant violation —
                _initialize() must be called before entering the state machine).
        """
        if not self.porcupine:
            raise RuntimeError(
                "Cannot start barge-in detection: Porcupine is not initialized. "
                "Wake-word mode requires barge-in and Porcupine must be initialized "
                "by _initialize() before the state machine runs."
            )

        self.barge_in_event = threading.Event()
        self.barge_in_stop_flag = threading.Event()
        self.barge_in_thread = threading.Thread(
            target=self._listen_for_barge_in,
            args=(self.barge_in_event, self.barge_in_stop_flag),
            daemon=True
        )
        self.barge_in_thread.start()

        logger.debug("Barge-in detection started")

        return self.barge_in_thread

    def _check_barge_in_interrupt(self):
        """Check if barge-in was triggered.

        Returns:
            bool: True if barge-in detected, False otherwise
        """
        # Note: barge_in_event may be None if Porcupine failed to initialize or if
        # this method is called before _start_barge_in_detection(). The None check
        # provides defensive programming against race conditions or unexpected states.
        if self.barge_in_event and self.barge_in_event.is_set():
            logger.debug("Barge-in interrupt detected")
            return True
        return False

    def _run_with_barge_in_polling(self, operation, operation_name="operation"):
        """Run an operation in background thread, polling for barge-in every 50ms.

        If barge-in is detected, returns immediately without waiting for operation.
        The operation continues in background but result is discarded.

        Note: On barge-in, the background thread (daemon) continues running until
        completion. This is a deliberate tradeoff for responsiveness - cancelling
        API calls mid-flight would require significant client changes. The daemon
        thread will complete naturally and be cleaned up by the runtime. In practice,
        users rarely barge-in repeatedly in quick succession, so thread buildup is
        minimal.

        Limitation: Operations with side effects (e.g., AI conversation history
        updates, plugin actions) will still complete even after barge-in. This is
        acceptable for the current use case where barge-in is primarily about
        responsiveness, not transaction rollback.

        Args:
            operation: Callable to run
            operation_name: Name for debug logging

        Returns:
            tuple: (completed: bool, result: any)
                - (True, result) if operation completed normally
                - (False, None) if interrupted by barge-in
        """
        # If barge-in is already active, skip starting the operation
        if self._check_barge_in_interrupt():
            logger.debug("Barge-in already active before starting %s - skipping", operation_name)
            return False, None

        result_holder = [None]
        error_holder = [None]

        def run_in_background():
            try:
                result_holder[0] = operation()
            except Exception as e:
                error_holder[0] = e
                # Log at DEBUG only — if no barge-in, the error is re-raised and
                # logged by the outer handler; a WARNING here would duplicate it.
                logger.debug("Background %s failed: %s", operation_name, e)

        thread = threading.Thread(target=run_in_background, daemon=True)
        thread.start()

        # Poll every 50ms for completion or barge-in (faster response)
        poll_count = 0
        while thread.is_alive():
            if self._check_barge_in_interrupt():
                logger.debug("Barge-in during %s - responding immediately!", operation_name)
                return False, None
            time.sleep(0.05)
            poll_count += 1
            # Every 2 seconds (40 polls), check if audio is unexpectedly playing
            if logger.isEnabledFor(logging.DEBUG) and poll_count % 40 == 0:
                try:
                    import pygame
                    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                        logger.debug(">>> UNEXPECTED: Audio is playing during %s polling!", operation_name)
                except Exception:
                    pass

        # Operation completed - check for errors
        if error_holder[0] is not None:
            raise error_holder[0]

        return True, result_holder[0]

    def _handle_immediate_barge_in(self, barge_in_thread):
        """Handle barge-in with immediate beep and transition to LISTENING.

        Args:
            barge_in_thread: The barge-in detection thread to stop
        """
        logger.info("=== BARGE-IN TRIGGERED === Current state: %s", self.state.name)
        if self.config.debug:
            self.audio.log_mixer_state("barge-in BEFORE stop")

        # Immediately stop any audio and do full reset to prevent any cached audio from playing
        self.audio.stop_playback(full_reset=True)

        if self.config.debug:
            self.audio.log_mixer_state("barge-in AFTER stop")

        # Signal barge-in thread to stop and give it a brief chance to clean up
        if barge_in_thread and self.barge_in_stop_flag:
            self.barge_in_stop_flag.set()
            if barge_in_thread.is_alive():
                try:
                    # Short timeout to allow PyAudio stream to close before LISTENING reopens it
                    barge_in_thread.join(timeout=0.3)
                except RuntimeError:
                    # Thread may already be stopped or not started; ignore and continue
                    pass

        # Clean up thread and events
        self.barge_in_thread = None
        self.barge_in_event = None
        self.barge_in_stop_flag = None

        # Clean up any partial data
        if self.recorded_audio_path and os.path.exists(self.recorded_audio_path):
            try:
                os.remove(self.recorded_audio_path)
            except OSError as e:
                logger.debug("Failed to remove recorded audio file '%s': %s", self.recorded_audio_path, e)
        self.recorded_audio_path = None
        self.response_text = None
        self.streaming_response_text = None
        self.streaming_user_input = None
        self.streaming_route = None

        # Play confirmation beep
        if self.config.wake_confirmation_beep and self.confirmation_beep_path:
            if os.path.exists(self.confirmation_beep_path):
                try:
                    with (self._audio_lock or contextlib.nullcontext()):
                        self.audio.play_audio_file(self.confirmation_beep_path)
                except Exception as e:
                    logger.warning("Failed to play beep: %s", e)

        # Go directly to LISTENING
        self.state = State.LISTENING

    def _should_stream_default_route(self):
        """Return True — streaming is always active in wake-word mode (Plan 29)."""
        return True

    def _poll_op(self, operation, name, barge_in_thread):
        """Run *operation* with barge-in polling.

        Always polls for barge-in interruption (barge-in is unconditionally
        active in wake-word mode).  If barge-in interrupts, calls
        _handle_immediate_barge_in and returns the _BARGE_IN sentinel.
        Otherwise returns the operation result directly.
        """
        completed, result = self._run_with_barge_in_polling(operation, name)
        if not completed:
            self._handle_immediate_barge_in(barge_in_thread)
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
        self.response_text = None
        self.streaming_response_text = None
        self.streaming_user_input = None
        self.streaming_route = None

        # Check if we have a recorded audio file before starting barge-in detection
        if not self.recorded_audio_path or not os.path.exists(self.recorded_audio_path):
            logger.warning("No recorded audio file found, returning to IDLE")
            self.recorded_audio_path = None
            self.state = State.IDLE
            return

        # Start barge-in detection thread (will run through PROCESSING and RESPONDING)
        barge_in_thread = self._start_barge_in_detection()

        try:
            # Capture path locally to avoid race with barge-in clearing self.recorded_audio_path
            audio_path = self.recorded_audio_path

            # Transcribe the audio
            logger.debug("Transcribing audio from: %s", audio_path)
            user_input = self._poll_op(
                lambda: self.ai.transcribe_and_translate(audio_file_path=audio_path),
                "transcription",
                barge_in_thread,
            )
            if user_input is _BARGE_IN:
                return

            logger.debug("Transcription: %s", user_input)
            print(f"You: {user_input}")

            # Check for barge-in before starting response generation
            if barge_in_thread and self._check_barge_in_interrupt():
                logger.debug("Barge-in detected after transcription, before response generation")
                self._handle_immediate_barge_in(barge_in_thread)
                return

            # Generate response (prefer plugin routing when available)
            if self.route_message is not None:
                route = self._poll_op(
                    lambda: self.ai.define_route(user_input),
                    "route definition",
                    barge_in_thread,
                )
                if route is _BARGE_IN:
                    return

                logger.debug("Route: %s", route)

                stream_default_route = (
                    self._should_stream_default_route() and
                    (self.plugins is not None) and
                    (route.get("route") not in self.plugins)
                )

                if stream_default_route:
                    self.streaming_user_input = user_input
                    self.streaming_route = route
                    self.response_text = None

                    if barge_in_thread and self._check_barge_in_interrupt():
                        logger.debug("Barge-in detected after route definition, before streaming")
                        self._handle_immediate_barge_in(barge_in_thread)
                        return

                    self.state = State.RESPONDING
                    return

                response_text = self._poll_op(
                    lambda: self.route_message(user_input, route),
                    "plugin response",
                    barge_in_thread,
                )
                if response_text is _BARGE_IN:
                    return

                self.response_text = response_text
                self.streaming_response_text = response_text
            else:
                # No route_message: streaming is always active (required by Plan 29)
                self.streaming_user_input = user_input
                self.streaming_route = {"route": "default-route", "reason": "direct"}
                self.response_text = None

                if barge_in_thread and self._check_barge_in_interrupt():
                    logger.debug("Barge-in detected before streaming")
                    self._handle_immediate_barge_in(barge_in_thread)
                    return

                self.state = State.RESPONDING
                return

            logger.debug("Response: %s", self.response_text)
            print(f"{self.config.botname}: {self.response_text}\n")

            # Final barge-in check before transitioning to RESPONDING
            if barge_in_thread and self._check_barge_in_interrupt():
                logger.debug("Barge-in detected after processing completed, before RESPONDING")
                self._handle_immediate_barge_in(barge_in_thread)
                return

            # Transition to RESPONDING state (barge-in thread continues running)
            logger.debug("=== TRANSITIONING TO RESPONDING ===")
            if self.config.debug:
                self.audio.log_mixer_state("BEFORE RESPONDING transition")
            self.state = State.RESPONDING

        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")

            # Clean up recorded audio file on error
            if self.recorded_audio_path and os.path.exists(self.recorded_audio_path):
                try:
                    os.remove(self.recorded_audio_path)
                    logger.debug("Cleaned up recording after error: %s", self.recorded_audio_path)
                except Exception as cleanup_error:
                    logger.warning("Failed to clean up recording file after error: %s", cleanup_error)

            # Stop barge-in thread if it was started
            if barge_in_thread:
                try:
                    self.barge_in_stop_flag.set()
                    barge_in_thread.join(timeout=1.0)
                except Exception as thread_error:
                    logger.warning("Failed to stop barge-in thread: %s", thread_error)

            # Reset state
            self.barge_in_thread = None
            self.barge_in_event = None
            self.barge_in_stop_flag = None
            self.recorded_audio_path = None
            self.response_text = None
            self.streaming_response_text = None

            # Return to IDLE on error
            self.state = State.IDLE

    def _listen_for_barge_in(self, barge_in_event, stop_flag):
        """Background thread to listen for wake word during TTS playback.

        Creates its own Porcupine instance to avoid thread-safety issues.

        Args:
            barge_in_event: threading.Event to signal when wake word detected
            stop_flag: threading.Event to signal immediate thread termination
        """
        porcupine_instance = None
        pa = None
        audio_stream = None

        try:
            # Create dedicated Porcupine instance for this thread (thread-safety)
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
                frames_per_buffer=porcupine_instance.frame_length
            )

            logger.debug("Barge-in thread: Audio stream opened, listening for wake word...")

            while self.running and not barge_in_event.is_set() and not stop_flag.is_set():
                try:
                    pcm = audio_stream.read(porcupine_instance.frame_length, exception_on_overflow=False)
                    pcm = struct.unpack_from("h" * porcupine_instance.frame_length, pcm)

                    keyword_index = porcupine_instance.process(pcm)

                    if keyword_index >= 0:
                        logger.debug("Barge-in: Wake word detected! Interrupting...")
                        barge_in_event.set()
                        break

                except Exception as e:
                    logger.warning("Barge-in thread error reading audio: %s", e)
                    break

        except Exception as e:
            logger.error("Barge-in detection thread error: %s", e)
        finally:
            if audio_stream is not None:
                try:
                    audio_stream.stop_stream()
                    audio_stream.close()
                except Exception as e:
                    logger.warning("Failed to close barge-in audio stream: %s", e)
            if pa is not None:
                try:
                    pa.terminate()
                except Exception as e:
                    logger.warning("Failed to terminate barge-in PyAudio: %s", e)
            if porcupine_instance is not None:
                try:
                    porcupine_instance.delete()
                except Exception as e:
                    logger.warning("Failed to delete barge-in Porcupine instance: %s", e)

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

        # Signal barge-in thread to stop and wait for it to finish
        if self.barge_in_stop_flag is not None:
            self.barge_in_stop_flag.set()
            logger.debug("Signaled barge-in thread to stop")
            # Wait for thread to finish to ensure PyAudio stream is closed before LISTENING reopens it
            if self.barge_in_thread is not None and self.barge_in_thread.is_alive():
                try:
                    self.barge_in_thread.join(timeout=0.3)
                except RuntimeError:
                    pass  # Thread may already be stopped

        # Clean up temporary recorded audio file
        if self.recorded_audio_path and os.path.exists(self.recorded_audio_path):
            try:
                os.remove(self.recorded_audio_path)
                logger.debug("Cleaned up recording: %s", self.recorded_audio_path)
            except Exception as e:
                logger.warning("Failed to clean up recording file: %s", e)

        # Reset for next cycle
        self.recorded_audio_path = None
        self.response_text = None

        # Transition to LISTENING if barge-in occurred, otherwise back to IDLE
        # Note: barge_in_event may be None if Porcupine failed to initialize
        if self.barge_in_event and self.barge_in_event.is_set():
            logger.debug("Transitioning to LISTENING after barge-in")

            # Play confirmation beep (consistent with _handle_immediate_barge_in)
            if self.config.wake_confirmation_beep and self.confirmation_beep_path:
                if os.path.exists(self.confirmation_beep_path):
                    try:
                        with (self._audio_lock or contextlib.nullcontext()):
                            self.audio.play_audio_file(self.confirmation_beep_path)
                    except Exception as e:
                        logger.warning("Failed to play beep: %s", e)

            self.barge_in_thread = None
            self.barge_in_event = None
            self.barge_in_stop_flag = None
            self.state = State.LISTENING
        else:
            self.barge_in_thread = None
            self.barge_in_event = None
            self.barge_in_stop_flag = None
            self.state = State.IDLE

    def _respond_streaming(self):
        """Streaming TTS response path for LLM and plugin responses.

        For LLM default-route responses: streams deltas from ai.stream_response_deltas,
        chunks them, converts to audio via TTS worker, and plays via player worker —
        all concurrently.

        For pre-computed plugin responses (streaming_response_text set): enqueues the
        text directly to the TTS worker, bypassing LLM streaming.

        Resets streaming state on return; barge-in cleanup and state transition remain
        in _state_responding.
        """
        user_input = self.streaming_user_input
        self.streaming_user_input = None
        precomputed_text = self.streaming_response_text
        self.streaming_response_text = None

        # Ensure barge-in detection is running (always required in wake-word mode)
        thread_already_running = (
            self.barge_in_thread is not None and
            self.barge_in_thread.is_alive()
        )

        if not thread_already_running:
            self._start_barge_in_detection()

        barge_in_event = self.barge_in_event
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

                    tts_files = self.ai.text_to_speech(chunk)

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
            success, failed_file, error = self.audio.play_audio_queue(
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

        boundary = str(getattr(self.config, "stream_tts_boundary", "sentence") or "sentence").strip().lower()
        # Rough heuristic for English: ~35 characters/sec spoken.
        chars_per_second = 35
        target_s = 6
        first_min_chars = max(120, int(target_s * chars_per_second))
        next_min_chars = 200

        buffer = ""
        full_parts = []
        is_first = True
        stream_completed = False

        if precomputed_text is not None:
            # Pre-computed plugin response — enqueue directly without LLM streaming.
            if not (barge_in_event and barge_in_event.is_set()) and not stop_event.is_set():
                if _put_text_queue(precomputed_text):
                    stream_completed = True
                else:
                    interrupt_event.set()
        else:
            if self.config.debug:
                print(f"{self.config.botname}: ", end="", flush=True)

            try:
                for delta in self.ai.stream_response_deltas(user_input):
                    full_parts.append(delta)
                    if self.config.debug:
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
                        chunk, buffer = pop_streaming_chunk(buffer, boundary=boundary, min_chars=min_chars)
                        if chunk is None:
                            break
                        is_first = False
                        if not _put_text_queue(chunk):
                            interrupt_event.set()
                            break

                else:
                    stream_completed = True
                    if self.config.debug:
                        print()  # terminate the debug delta line

            except Exception as e:
                interrupt_event.set()
                if self.config.debug:
                    print()
                print(handle_api_error(e, service_name="OpenAI GPT (streaming)"))

            # If LLM streaming did not complete, remove the last user turn to avoid dangling history.
            if not stream_completed:
                try:
                    last_user = "User: " + user_input
                    if getattr(self.ai, "conversation_history", None) and self.ai.conversation_history[-1] == last_user:
                        self.ai.conversation_history.pop()
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

        response_text = "".join(full_parts).strip()
        # Print final text (unless we are in debug mode or barge-in occurred)
        if response_text and not self.config.debug:
            if not (barge_in_event and barge_in_event.is_set()):
                print(f"{self.config.botname}: {response_text}\n")

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

        # Reset streaming metadata
        self.streaming_route = None
        self.response_text = None

    def _cleanup(self):
        """Clean up Porcupine, VAD, barge-in thread, and audio resources."""
        logger.info("Cleaning up wake word mode")

        # Clean up barge-in thread if running
        if self.barge_in_stop_flag is not None:
            self.barge_in_stop_flag.set()
        if self.barge_in_thread is not None and self.barge_in_thread.is_alive():
            try:
                self.barge_in_thread.join(timeout=0.5)
            except RuntimeError:
                pass  # Thread may already be stopped
        self.barge_in_thread = None
        self.barge_in_event = None
        self.barge_in_stop_flag = None

        if self.porcupine is not None:
            try:
                self.porcupine.delete()
            except Exception as e:
                logger.warning("Failed to delete Porcupine instance: %s", e)
            finally:
                self.porcupine = None

        self.running = False
