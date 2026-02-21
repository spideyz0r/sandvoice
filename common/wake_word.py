import glob
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
    return bool(value)


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

    def __init__(self, config, ai_instance, audio_instance, route_message = None, plugins=None):
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
        """
        self.config = config
        self.ai = ai_instance
        self.audio = audio_instance
        self.route_message = route_message
        self.plugins = plugins
        self.state = State.IDLE
        self.running = False

        self.porcupine = None
        self.confirmation_beep_path = None
        self.ack_earcon_path = None
        self.recorded_audio_path = None
        self.response_text = None
        self.tts_files = None
        self.streaming_user_input = None
        self.streaming_route = None
        self.barge_in_event = None  # Event to signal barge-in during TTS
        self.barge_in_stop_flag = None  # Flag to stop barge-in thread immediately
        self.barge_in_thread = None  # Thread for barge-in detection

        if self.config.debug:
            logging.info("Initializing wake word mode")

    def run(self):
        """Main event loop. Runs until user exits with Ctrl+C.

        Manages state machine transitions:
        IDLE → LISTENING → PROCESSING → RESPONDING → IDLE
        """
        if self.config.debug:
            logging.info("Starting wake word mode")

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
            RuntimeError: If Porcupine access key is missing or invalid
        """
        if self.config.debug:
            logging.info("Initializing wake word detection and VAD")

        if not self.config.porcupine_access_key:
            error_msg = (
                "Porcupine access key is required for wake word mode. "
                "Get your free key at https://console.picovoice.ai/ and add it to your config: "
                "porcupine_access_key: YOUR_KEY_HERE"
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
                    if self.config.debug:
                        logging.error(error_msg)
                    print(f"Error: {error_msg}")
                    raise RuntimeError(error_msg)

            # Create main Porcupine instance
            self.porcupine = self._create_porcupine_instance()

            if self.config.debug:
                if keyword_paths:
                    logging.info(f"Porcupine initialized with custom keyword paths: {keyword_paths}")
                else:
                    logging.info(f"Porcupine initialized with built-in wake phrase: '{self.config.wake_phrase}'")

            if self.config.debug:
                logging.info(f"Porcupine sample rate: {self.porcupine.sample_rate}")
                logging.info(f"Porcupine frame length: {self.porcupine.frame_length}")

        except RuntimeError:
            raise
        except Exception as e:
            error_msg = f"Failed to initialize Porcupine: {str(e)}"
            if self.config.debug:
                logging.error(error_msg)
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

        if self.config.wake_confirmation_beep:
            try:
                self.confirmation_beep_path = create_confirmation_beep(
                    freq=self.config.wake_confirmation_beep_freq,
                    duration=self.config.wake_confirmation_beep_duration,
                    tmp_path=self.config.tmp_files_path
                )
                if self.config.debug:
                    logging.info(f"Confirmation beep created at: {self.confirmation_beep_path}")
            except Exception as e:
                if self.config.debug:
                    logging.warning(f"Failed to create confirmation beep: {e}")
                self.confirmation_beep_path = None

        if _is_enabled_flag(getattr(self.config, "bot_voice", False)) and _is_enabled_flag(
            getattr(self.config, "voice_ack_earcon", False)
        ):
            try:
                self.ack_earcon_path = create_ack_earcon(
                    freq=getattr(self.config, "voice_ack_earcon_freq", 600),
                    duration=getattr(self.config, "voice_ack_earcon_duration", 0.06),
                    tmp_path=self.config.tmp_files_path,
                )
                if self.config.debug:
                    logging.info(f"Ack earcon created at: {self.ack_earcon_path}")
            except Exception as e:
                if self.config.debug:
                    logging.warning(f"Failed to create ack earcon: {e}")
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
                    if self.config.debug:
                        logging.info(f"Wake word detected: '{self.config.wake_phrase}'")

                    if self.config.wake_confirmation_beep and self.confirmation_beep_path:
                        try:
                            self.audio.play_audio_file(self.confirmation_beep_path)
                        except Exception as e:
                            if self.config.debug:
                                logging.warning(f"Failed to play confirmation beep: {e}")

                    self.state = State.LISTENING
                    break

        except Exception as e:
            error_msg = f"Wake word detection error: {str(e)}"
            if self.config.debug:
                logging.error(error_msg)
            print(f"Error: {error_msg}")
            self.running = False
        finally:
            if audio_stream is not None:
                try:
                    audio_stream.stop_stream()
                    audio_stream.close()
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to close audio stream: {e}")
            if pa is not None:
                try:
                    pa.terminate()
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to terminate PyAudio: {e}")

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

        if not self.config.vad_enabled:
            if self.config.debug:
                logging.warning("VAD is disabled in config. Skipping recording.")
            self.state = State.PROCESSING
            return

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
            if self.config.debug:
                logging.info(f"VAD requires specific sample rates. Using {vad_sample_rate}Hz instead of {sample_rate}Hz")
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

            if self.config.debug:
                logging.info(f"Recording with VAD: {vad_sample_rate}Hz, frame_duration={frame_duration_ms}ms")

            while self.running and self.state == State.LISTENING:
                # Check timeout
                elapsed = time.time() - recording_start
                if elapsed > self.config.vad_timeout:
                    if self.config.debug:
                        logging.info(f"VAD timeout reached ({self.config.vad_timeout}s)")
                    break

                # Read audio frame
                try:
                    pcm = audio_stream.read(vad_frame_size, exception_on_overflow=False)
                except Exception as e:
                    if self.config.debug:
                        logging.error(f"Error reading audio frame: {e}")
                    break

                frames.append(pcm)

                # Run VAD on frame
                try:
                    is_speech = vad.is_speech(pcm, vad_sample_rate)
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"VAD processing error: {e}")
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
                            if self.config.debug:
                                logging.info(f"Silence detected ({silence_duration:.2f}s)")
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
                    if self.config.debug:
                        logging.warning(f"Failed to get sample width: {e}")
                    sample_width = 2  # 16-bit PCM

                # Close input stream before playing any earcons (improves compatibility on some devices)
                if audio_stream is not None:
                    try:
                        audio_stream.stop_stream()
                        audio_stream.close()
                    except Exception as e:
                        if self.config.debug:
                            logging.warning(f"Failed to close audio stream: {e}")
                    audio_stream = None

                if pa is not None:
                    try:
                        pa.terminate()
                    except Exception as e:
                        if self.config.debug:
                            logging.warning(f"Failed to terminate PyAudio: {e}")
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

                if self.config.debug:
                    logging.info(f"Recorded audio saved: {self.recorded_audio_path}")
                    logging.info(f"Recording duration: {elapsed:.2f}s, {len(frames)} frames")

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
                                self.audio.play_audio_file(self.ack_earcon_path)
                            elif self.config.debug:
                                logging.info("Skipping ack earcon: audio is already playing")
                        except Exception as e:
                            if self.config.debug:
                                logging.warning(f"Failed to play ack earcon: {e}")

                self.state = State.PROCESSING
            else:
                if self.config.debug:
                    logging.warning("No audio recorded, returning to IDLE")
                self.state = State.IDLE

        except Exception as e:
            error_msg = f"Recording error: {str(e)}"
            if self.config.debug:
                logging.error(error_msg)
            print(f"Error: {error_msg}")
            self.state = State.IDLE
        finally:
            if audio_stream is not None:
                try:
                    audio_stream.stop_stream()
                    audio_stream.close()
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to close audio stream: {e}")
            if pa is not None:
                try:
                    pa.terminate()
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to terminate PyAudio: {e}")

    def _start_barge_in_detection(self):
        """Start barge-in detection thread.

        Returns:
            threading.Thread or None: The barge-in thread if started, None otherwise
        """
        barge_in_enabled = getattr(self.config, "barge_in", False)
        if not barge_in_enabled or not self.porcupine:
            if barge_in_enabled and not self.porcupine:
                if self.config.debug:
                    logging.warning(
                        "Barge-in is enabled in configuration, but Porcupine is not initialized. "
                        "Barge-in will be disabled."
                    )
            return None

        self.barge_in_event = threading.Event()
        self.barge_in_stop_flag = threading.Event()
        self.barge_in_thread = threading.Thread(
            target=self._listen_for_barge_in,
            args=(self.barge_in_event, self.barge_in_stop_flag),
            daemon=True
        )
        self.barge_in_thread.start()

        if self.config.debug:
            logging.info("Barge-in detection started")

        return self.barge_in_thread

    def _check_barge_in_interrupt(self):
        """Check if barge-in was triggered.

        Returns:
            bool: True if barge-in detected, False otherwise
        """
        # Note: barge_in_event may be None if Porcupine failed to initialize or if
        # this method is called before _start_barge_in_detection(). The None check
        # provides defensive programming against race conditions or unexpected states.
        barge_in_enabled = getattr(self.config, "barge_in", False)
        if barge_in_enabled and self.barge_in_event and self.barge_in_event.is_set():
            if self.config.debug:
                logging.info("Barge-in interrupt detected")
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
            if getattr(self.config, "debug", False):
                logging.info(
                    f"Barge-in already active before starting {operation_name} - skipping"
                )
            return False, None

        result_holder = [None]
        error_holder = [None]

        def run_in_background():
            try:
                result_holder[0] = operation()
            except Exception as e:
                error_holder[0] = e
                # Log exception so it's not silently swallowed on barge-in
                if getattr(self.config, "debug", False):
                    logging.warning(f"Background {operation_name} failed: {e}")

        thread = threading.Thread(target=run_in_background, daemon=True)
        thread.start()

        # Poll every 50ms for completion or barge-in (faster response)
        poll_count = 0
        while thread.is_alive():
            if self._check_barge_in_interrupt():
                if self.config.debug:
                    logging.info(f"Barge-in during {operation_name} - responding immediately!")
                return False, None
            time.sleep(0.05)
            poll_count += 1
            # Every 2 seconds (40 polls), check if audio is unexpectedly playing
            if self.config.debug and poll_count % 40 == 0:
                try:
                    import pygame
                    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                        logging.warning(f">>> UNEXPECTED: Audio is playing during {operation_name} polling!")
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
        if self.config.debug:
            logging.info(f"=== BARGE-IN TRIGGERED === Current state: {self.state.name}")
            self.audio.log_mixer_state("barge-in BEFORE stop")

        # Immediately stop any audio and do full reset to prevent any cached audio from playing
        self.audio.stop_playback(full_reset=True)

        if self.config.debug:
            self.audio.log_mixer_state("barge-in AFTER stop")

        # Immediately clean up ALL orphaned TTS files (don't wait for scheduled cleanup)
        self._cleanup_all_orphaned_tts_files()

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
                if self.config.debug:
                    logging.debug(f"Failed to remove recorded audio file '{self.recorded_audio_path}': {e}")
        self.recorded_audio_path = None
        self.response_text = None
        self.tts_files = None

        # Schedule cleanup of any orphaned TTS files from interrupted background thread
        self._schedule_orphaned_tts_cleanup()

        # Play confirmation beep
        if self.config.wake_confirmation_beep and self.confirmation_beep_path:
            if os.path.exists(self.confirmation_beep_path):
                try:
                    self.audio.play_audio_file(self.confirmation_beep_path)
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to play beep: {e}")

        # Go directly to LISTENING
        self.state = State.LISTENING

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
        self.tts_files = None

        # Check if we have a recorded audio file before starting barge-in detection
        if not self.recorded_audio_path or not os.path.exists(self.recorded_audio_path):
            if self.config.debug:
                logging.warning("No recorded audio file found, returning to IDLE")
            self.recorded_audio_path = None
            self.state = State.IDLE
            return

        # Start barge-in detection thread (will run through PROCESSING and RESPONDING)
        barge_in_thread = self._start_barge_in_detection()

        try:
            # Capture path locally to avoid race with barge-in clearing self.recorded_audio_path
            audio_path = self.recorded_audio_path

            # Transcribe the audio (with immediate barge-in response if enabled)
            if self.config.debug:
                logging.info(f"Transcribing audio from: {audio_path}")

            if barge_in_thread:
                completed, user_input = self._run_with_barge_in_polling(
                    lambda: self.ai.transcribe_and_translate(audio_file_path=audio_path),
                    "transcription"
                )
                if not completed:
                    self._handle_immediate_barge_in(barge_in_thread)
                    return
            else:
                user_input = self.ai.transcribe_and_translate(audio_file_path=audio_path)

            if self.config.debug:
                logging.info(f"Transcription: {user_input}")

            print(f"You: {user_input}")

            # Check for barge-in before starting response generation
            if barge_in_thread and self._check_barge_in_interrupt():
                if self.config.debug:
                    logging.info("Barge-in detected after transcription, before response generation")
                self._handle_immediate_barge_in(barge_in_thread)
                return

            # Generate response (prefer plugin routing when available)
            # Both paths support barge-in polling for immediate interruption
            if self.route_message is not None:
                # Route through plugin system (with barge-in support if enabled)
                if barge_in_thread:
                    completed, route = self._run_with_barge_in_polling(
                        lambda: self.ai.define_route(user_input),
                        "route definition"
                    )
                    if not completed:
                        self._handle_immediate_barge_in(barge_in_thread)
                        return
                else:
                    route = self.ai.define_route(user_input)

                if self.config.debug:
                    logging.info(f"Route: {route}")

                stream_default_route = (
                    self.config.bot_voice and
                    (getattr(self.config, "stream_responses", False) is True) and
                    (getattr(self.config, "stream_tts", False) is True) and
                    (self.plugins is not None) and
                    (route.get("route") not in self.plugins)
                )

                if stream_default_route:
                    # Skip non-streaming route_message() default behavior and stream in RESPONDING instead.
                    self.streaming_user_input = user_input
                    self.streaming_route = route
                    self.response_text = None
                    self.tts_files = None

                    # Final barge-in check before transitioning to RESPONDING
                    if barge_in_thread and self._check_barge_in_interrupt():
                        if self.config.debug:
                            logging.info("Barge-in detected after route definition, before streaming")
                        self._handle_immediate_barge_in(barge_in_thread)
                        return

                    self.state = State.RESPONDING
                    return

                if barge_in_thread:
                    completed, response_text = self._run_with_barge_in_polling(
                        lambda: self.route_message(user_input, route),
                        "plugin response"
                    )
                    if not completed:
                        self._handle_immediate_barge_in(barge_in_thread)
                        return
                else:
                    response_text = self.route_message(user_input, route)

                self.response_text = response_text
            else:
                # Direct AI response (with barge-in support if enabled)
                stream_default_route = (
                    self.config.bot_voice and
                    (getattr(self.config, "stream_responses", False) is True) and
                    (getattr(self.config, "stream_tts", False) is True)
                )

                if stream_default_route:
                    self.streaming_user_input = user_input
                    self.streaming_route = {"route": "default-route", "reason": "direct"}
                    self.response_text = None
                    self.tts_files = None

                    if barge_in_thread and self._check_barge_in_interrupt():
                        if self.config.debug:
                            logging.info("Barge-in detected before streaming")
                        self._handle_immediate_barge_in(barge_in_thread)
                        return

                    self.state = State.RESPONDING
                    return

                if barge_in_thread:
                    completed, response = self._run_with_barge_in_polling(
                        lambda: self.ai.generate_response(user_input),
                        "response generation"
                    )
                    if not completed:
                        self._handle_immediate_barge_in(barge_in_thread)
                        return
                else:
                    response = self.ai.generate_response(user_input)

                self.response_text = response.content if hasattr(response, 'content') else str(response)

            if self.config.debug:
                logging.info(f"Response: {self.response_text}")

            print(f"{self.config.botname}: {self.response_text}\n")

            # Check for barge-in before starting TTS generation
            if barge_in_thread and self._check_barge_in_interrupt():
                if self.config.debug:
                    logging.info("Barge-in detected after response, before TTS generation")
                self._handle_immediate_barge_in(barge_in_thread)
                return

            # Generate TTS if bot_voice is enabled (with immediate barge-in response if enabled)
            if self.config.bot_voice:
                # Clean up any orphaned TTS files from interrupted previous requests
                # This prevents leftover files from affecting the new response
                self._cleanup_all_orphaned_tts_files()

                # Capture response text locally to avoid race with barge-in clearing self.response_text
                response_text_for_tts = self.response_text
                if barge_in_thread:
                    completed, tts_files = self._run_with_barge_in_polling(
                        lambda: self.ai.text_to_speech(response_text_for_tts),
                        "TTS generation"
                    )
                    if not completed:
                        self._handle_immediate_barge_in(barge_in_thread)
                        return
                else:
                    tts_files = self.ai.text_to_speech(response_text_for_tts)

                self.tts_files = tts_files

                if self.config.debug:
                    if self.tts_files:
                        tts_file_info = [os.path.basename(f) for f in self.tts_files]
                        logging.info(f"Generated {len(self.tts_files)} TTS files: {tts_file_info}")
                    else:
                        logging.warning("No TTS files generated")

            # Final barge-in check before transitioning to RESPONDING
            # This catches barge-in detected between last polling check and now
            if barge_in_thread and self._check_barge_in_interrupt():
                if self.config.debug:
                    logging.info("Barge-in detected after processing completed, before RESPONDING")
                # Clean up TTS files we just generated since we're not going to play them
                if self.tts_files:
                    self._cleanup_remaining_tts_files(self.tts_files)
                    self.tts_files = None
                self._handle_immediate_barge_in(barge_in_thread)
                return

            # Transition to RESPONDING state (barge-in thread continues running)
            if self.config.debug:
                logging.info(f"=== TRANSITIONING TO RESPONDING === TTS files: {len(self.tts_files) if self.tts_files else 0}")
                self.audio.log_mixer_state("BEFORE RESPONDING transition")
            self.state = State.RESPONDING

        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            if self.config.debug:
                logging.error(error_msg)
            print(f"Error: {error_msg}")

            # Clean up recorded audio file on error
            if self.recorded_audio_path and os.path.exists(self.recorded_audio_path):
                try:
                    os.remove(self.recorded_audio_path)
                    if self.config.debug:
                        logging.info(f"Cleaned up recording after error: {self.recorded_audio_path}")
                except Exception as cleanup_error:
                    if self.config.debug:
                        logging.warning(f"Failed to clean up recording file after error: {cleanup_error}")

            # Stop barge-in thread if it was started
            if barge_in_thread:
                try:
                    self.barge_in_stop_flag.set()
                    barge_in_thread.join(timeout=1.0)
                except Exception as thread_error:
                    if self.config.debug:
                        logging.warning(f"Failed to stop barge-in thread: {thread_error}")

            # Reset state
            self.barge_in_thread = None
            self.barge_in_event = None
            self.barge_in_stop_flag = None
            self.recorded_audio_path = None
            self.response_text = None
            self.tts_files = None

            # Return to IDLE on error
            self.state = State.IDLE

    def _cleanup_remaining_tts_files(self, file_list):
        """Clean up a list of TTS files.
        
        Args:
            file_list: List of file paths to delete
        """
        for file_path in file_list:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError as e:
                if self.config.debug:
                    logging.warning(f"Failed to delete TTS file '{file_path}': {e}")

    def _cleanup_specific_tts_files(self, file_list):
        """Clean up specific TTS files from a pre-captured list.

        Args:
            file_list: List of file paths to delete (captured before delay)
        """
        for file_path in file_list:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    if self.config.debug:
                        logging.info(f"Cleaned up orphaned TTS file: {file_path}")
            except OSError as e:
                if self.config.debug:
                    logging.warning(f"Failed to delete orphaned TTS file: {e}")

    def _cleanup_all_orphaned_tts_files(self):
        """Immediately clean up all orphaned TTS files.

        This is called before generating new TTS to ensure no leftover files
        from interrupted requests could cause issues.
        """
        try:
            pattern = os.path.join(self.config.tmp_files_path, "tts-response-*.mp3")
            orphaned_files = glob.glob(pattern)
            if orphaned_files and self.config.debug:
                orphaned_info = [os.path.basename(f) for f in orphaned_files]
                logging.info(f"Cleaning up {len(orphaned_files)} orphaned TTS files: {orphaned_info}")
            self._cleanup_specific_tts_files(orphaned_files)
        except Exception as e:
            if self.config.debug:
                logging.warning(f"Error cleaning up orphaned TTS files: {e}")

    def _schedule_orphaned_tts_cleanup(self):
        """Schedule cleanup of orphaned TTS files after a short delay.

        Snapshots existing TTS files before the delay, then deletes only those
        files after the delay. This prevents accidentally deleting TTS files
        from a new interaction that started after barge-in.
        """
        # Snapshot current TTS files before delay
        try:
            pattern = os.path.join(self.config.tmp_files_path, "tts-response-*.mp3")
            files_to_cleanup = glob.glob(pattern)
        except Exception as e:
            if self.config.debug:
                logging.warning(f"Error finding orphaned TTS files: {e}")
            return

        if not files_to_cleanup:
            return

        def delayed_cleanup():
            time.sleep(2.0)  # Wait for background thread to complete
            self._cleanup_specific_tts_files(files_to_cleanup)

        cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
        cleanup_thread.start()

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
            if self.config.debug:
                logging.info("Barge-in thread: Creating Porcupine instance...")
            porcupine_instance = self._create_porcupine_instance()
            if self.config.debug:
                logging.info("Barge-in thread: Porcupine created successfully")

            if self.config.debug:
                logging.info("Barge-in thread: Opening PyAudio stream...")
            pa = pyaudio.PyAudio()
            audio_stream = pa.open(
                rate=porcupine_instance.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=porcupine_instance.frame_length
            )

            if self.config.debug:
                logging.info("Barge-in thread: Audio stream opened, listening for wake word...")

            while self.running and not barge_in_event.is_set() and not stop_flag.is_set():
                try:
                    pcm = audio_stream.read(porcupine_instance.frame_length, exception_on_overflow=False)
                    pcm = struct.unpack_from("h" * porcupine_instance.frame_length, pcm)

                    keyword_index = porcupine_instance.process(pcm)

                    if keyword_index >= 0:
                        if self.config.debug:
                            logging.info(f"Barge-in: Wake word detected! Interrupting...")
                        barge_in_event.set()
                        break

                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Barge-in thread error reading audio: {e}")
                    break

        except Exception as e:
            if self.config.debug:
                logging.error(f"Barge-in detection thread error: {e}")
        finally:
            if audio_stream is not None:
                try:
                    audio_stream.stop_stream()
                    audio_stream.close()
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to close barge-in audio stream: {e}")
            if pa is not None:
                try:
                    pa.terminate()
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to terminate barge-in PyAudio: {e}")
            if porcupine_instance is not None:
                try:
                    porcupine_instance.delete()
                except Exception as e:
                    if self.config.debug:
                        logging.warning(f"Failed to delete barge-in Porcupine instance: {e}")

    def _state_responding(self):
        """RESPONDING state: Play TTS response audio.

        Plays TTS files one by one using play_audio_file().
        Supports barge-in if enabled: interrupts TTS mid-playback when wake word detected.
        Barge-in thread may already be running from PROCESSING state.
        Transitions back to IDLE or LISTENING (if barge-in).
        """
        import threading
        if self.config.debug:
            tts_file_info = [os.path.basename(f) for f in self.tts_files] if self.tts_files else None
            # Log what files actually exist in temp directory
            try:
                pattern = os.path.join(self.config.tmp_files_path, "tts-response-*.mp3")
                all_tts_on_disk = [os.path.basename(f) for f in glob.glob(pattern)]
                logging.info(f"=== ENTERING RESPONDING === thread={threading.current_thread().name}")
                logging.info(f"  self.tts_files = {tts_file_info}")
                logging.info(f"  files_on_disk = {all_tts_on_disk}")
            except Exception as e:
                logging.info(f"=== ENTERING RESPONDING === thread={threading.current_thread().name}, TTS files: {tts_file_info}")

        if self.config.visual_state_indicator:
            print("🔊 Responding...")

        barge_in_enabled = getattr(self.config, "barge_in", False)

        # Plan 08 Phase 3: streaming TTS for wake word mode (default route only)
        if self.streaming_user_input:
            user_input = self.streaming_user_input
            self.streaming_user_input = None

            # Ensure barge-in detection is running (if enabled)
            thread_already_running = (
                self.barge_in_thread is not None and
                self.barge_in_thread.is_alive()
            )

            if not thread_already_running:
                if barge_in_enabled and self.porcupine:
                    self._start_barge_in_detection()
                elif barge_in_enabled and not self.porcupine:
                    if self.config.debug:
                        logging.warning(
                            "Barge-in is enabled in configuration, but Porcupine is not initialized. "
                            "Barge-in will be disabled for this response."
                        )

            barge_in_event = self.barge_in_event if (barge_in_enabled and self.barge_in_event) else None
            interrupt_event = threading.Event()
            production_failed_event = threading.Event()

            class _CompositeStopEvent:
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

            stop_event = _CompositeStopEvent(interrupt_event, barge_in_event)

            # Clean up any orphaned TTS files from interrupted previous requests
            self._cleanup_all_orphaned_tts_files()

            stream_tts_buffer_chunks = max(1, int(getattr(self.config, "stream_tts_buffer_chunks", 2) or 2))
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
                            if self.config.debug:
                                logging.warning("Timed out enqueueing streaming text chunk")
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

                        try:
                            tts_files = self.ai.text_to_speech(chunk)
                        except Exception as e:
                            tts_files = []
                            tts_error[0] = str(e)

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
                success, failed_file, error = self.audio.play_audio_queue(audio_queue, stop_event=stop_event)
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
            try:
                target_s = int(getattr(self.config, "stream_tts_first_chunk_target_s", 6) or 6)
            except Exception:
                target_s = 6

            # Rough heuristic for English: ~35 characters/sec spoken.
            chars_per_second = 35
            first_min_chars = max(120, int(target_s * chars_per_second))
            next_min_chars = 200

            stream_print_deltas = (getattr(self.config, "stream_print_deltas", False) is True)
            buffer = ""
            full_parts = []
            is_first = True
            stream_completed = False

            if self.config.debug and stream_print_deltas:
                print(f"{self.config.botname}: ", end="", flush=True)

            try:
                for delta in self.ai.stream_response_deltas(user_input):
                    full_parts.append(delta)

                    # Stop immediately on barge-in (user is starting a new request).
                    if barge_in_event and barge_in_event.is_set():
                        break

                    # If playback is interrupted (player failure), stop producing.
                    if interrupt_event.is_set():
                        break

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

            except Exception as e:
                interrupt_event.set()
                print(handle_api_error(e, service_name="OpenAI GPT (streaming)"))

            # If streaming did not complete, remove the last user turn to avoid dangling history.
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
            if not sentinel_enqueued and self.config.debug:
                logging.warning("Failed to enqueue wake-word streaming sentinel")
                interrupt_event.set()

            tts_join_timeout = int(getattr(self.config, "stream_tts_tts_join_timeout_s", 30) or 30)
            player_join_timeout = int(getattr(self.config, "stream_tts_player_join_timeout_s", 60) or 60)
            tts_thread.join(timeout=tts_join_timeout)
            player_thread.join(timeout=player_join_timeout)

            if self.config.debug:
                if tts_thread.is_alive():
                    logging.warning(
                        "Wake-word streaming TTS thread did not exit within %s seconds",
                        tts_join_timeout,
                    )
                if player_thread.is_alive():
                    logging.warning(
                        "Wake-word streaming player thread did not exit within %s seconds",
                        player_join_timeout,
                    )

            response_text = "".join(full_parts).strip()
            # Print final text (unless we are streaming deltas in debug or barge-in occurred)
            if response_text and (not (self.config.debug and stream_print_deltas)):
                if not (barge_in_event and barge_in_event.is_set()):
                    print(f"{self.config.botname}: {response_text}\n")

            if production_failed_event.is_set() and tts_error[0] and self.config.debug:
                logging.warning(f"Wake-word streaming TTS production failed: {tts_error[0]}")

            if not player_success[0]:
                if self.config.debug:
                    logging.warning(
                        f"Wake-word streaming audio playback failed for file '{player_failed_file[0]}': {player_error[0]}"
                    )

            # Reset streaming metadata
            self.streaming_route = None

            # Note: do not set self.tts_files; audio_queue playback already handled cleanup.
            self.tts_files = None
            self.response_text = None

        # Play TTS audio if available
        if self.tts_files and len(self.tts_files) > 0:
            # Check if barge-in thread is already running from PROCESSING state
            thread_already_running = (
                self.barge_in_thread is not None and
                self.barge_in_thread.is_alive()
            )

            # Start barge-in detection thread if not already running
            if not thread_already_running:
                if barge_in_enabled and self.porcupine:
                    self._start_barge_in_detection()
                elif barge_in_enabled and not self.porcupine:
                    # Only log in debug mode to be consistent with other conditional warnings
                    if self.config.debug:
                        logging.warning(
                            "Barge-in is enabled in configuration, but Porcupine is not initialized. "
                            "Barge-in will be disabled for this response."
                        )
            else:
                if self.config.debug:
                    logging.info("Barge-in thread already running from PROCESSING, reusing it")
            try:
                if self.config.debug:
                    logging.info(f"Playing {len(self.tts_files)} TTS files")

                # Play files with barge-in support via stop_event in play_audio_file()
                for idx, file_path in enumerate(self.tts_files):
                    # Play the file, passing stop_event for mid-playback interruption
                    try:
                        self.audio.play_audio_file(
                            file_path,
                            stop_event=self.barge_in_event if barge_in_enabled else None
                        )
                    except Exception as e:
                        if self.config.debug:
                            logging.error(f"Audio playback failed for file '{file_path}': {e}")
                            # In debug mode, preserve the failed file itself for diagnostics.
                            # The failed file will remain in the temp directory for manual inspection.
                            # Only clean up unplayed files after it (start at idx + 1).
                            self._cleanup_remaining_tts_files(self.tts_files[idx + 1:])
                        else:
                            print("Audio playback failed. Continuing with text only.")
                            # In non-debug mode, clean up the failed file and all remaining files
                            # by starting cleanup at the failed file (start at idx).
                            self._cleanup_remaining_tts_files(self.tts_files[idx:])
                        break

                    # Check for barge-in after playing file (might have interrupted mid-playback)
                    # Note: barge_in_event may be None if Porcupine failed to initialize
                    if barge_in_enabled and self.barge_in_event and self.barge_in_event.is_set():
                        if self.config.debug:
                            logging.info("Barge-in detected, interrupted during playback")
                        # First, clean up the file we just played successfully
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        except OSError as e:
                            if self.config.debug:
                                logging.warning(f"Failed to delete TTS file after barge-in: {e}")
                        # Then, clean up remaining unplayed files
                        self._cleanup_remaining_tts_files(self.tts_files[idx + 1:])
                        break
                    
                    # Clean up the file we just played successfully
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except OSError as e:
                        if self.config.debug:
                            logging.warning(f"Failed to delete TTS file: {e}")

            except Exception as e:
                if self.config.debug:
                    logging.error(f"TTS playback error: {e}")
                print(f"Error playing TTS: {str(e)}")

        else:
            if self.config.debug:
                logging.info("No TTS files to play (bot_voice disabled or TTS generation failed)")

        # Signal barge-in thread to stop and wait for it to finish
        if self.barge_in_stop_flag is not None:
            self.barge_in_stop_flag.set()
            if self.config.debug:
                logging.info("Signaled barge-in thread to stop")
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
                if self.config.debug:
                    logging.info(f"Cleaned up recording: {self.recorded_audio_path}")
            except Exception as e:
                if self.config.debug:
                    logging.warning(f"Failed to clean up recording file: {e}")

        # Reset for next cycle
        self.recorded_audio_path = None
        self.response_text = None
        self.tts_files = None

        # Transition to LISTENING if barge-in occurred, otherwise back to IDLE
        # Note: barge_in_event may be None if Porcupine failed to initialize
        if barge_in_enabled and self.barge_in_event and self.barge_in_event.is_set():
            if self.config.debug:
                logging.info("Transitioning to LISTENING after barge-in")

            # Play confirmation beep (consistent with _handle_immediate_barge_in)
            if self.config.wake_confirmation_beep and self.confirmation_beep_path:
                if os.path.exists(self.confirmation_beep_path):
                    try:
                        self.audio.play_audio_file(self.confirmation_beep_path)
                    except Exception as e:
                        if self.config.debug:
                            logging.warning(f"Failed to play beep: {e}")

            self.barge_in_thread = None
            self.barge_in_event = None
            self.barge_in_stop_flag = None
            self.state = State.LISTENING
        else:
            self.barge_in_thread = None
            self.barge_in_event = None
            self.barge_in_stop_flag = None
            self.state = State.IDLE

    def _cleanup(self):
        """Clean up Porcupine, VAD, barge-in thread, and audio resources."""
        if self.config.debug:
            logging.info("Cleaning up wake word mode")

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
                if self.config.debug:
                    logging.warning(f"Failed to delete Porcupine instance: {e}")
            finally:
                self.porcupine = None

        self.running = False
