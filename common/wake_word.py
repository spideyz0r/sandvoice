import logging
import os
import struct
import threading
import time
import wave
from enum import Enum

import pvporcupine
import pyaudio
import webrtcvad

from common.beep_generator import create_confirmation_beep


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

    def __init__(self, config, ai_instance, audio_instance, route_message = None):
        """Initialize wake word mode.

        Args:
            config: Configuration object with wake word settings
            ai_instance: AI instance for transcription and responses
            audio_instance: Audio instance for playback
            route_message: Optional callback to route messages through SandVoice plugins.
                Signature: route_message(user_input: str, route: dict) -> str
        """
        self.config = config
        self.ai = ai_instance
        self.audio = audio_instance
        self.route_message = route_message
        self.state = State.IDLE
        self.running = False

        self.porcupine = None
        self.confirmation_beep_path = None
        self.recorded_audio_path = None
        self.response_text = None
        self.tts_files = None
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

                self.recorded_audio_path = os.path.join(
                    self.config.tmp_files_path,
                    f"wake_word_recording_{int(time.time())}.wav"
                )

                # Ensure tmp directory exists
                os.makedirs(self.config.tmp_files_path, exist_ok=True)

                # Write WAV file
                with wave.open(self.recorded_audio_path, 'wb') as wf:
                    wf.setnchannels(1)  # Mono
                    wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
                    wf.setframerate(vad_sample_rate)
                    wf.writeframes(b''.join(frames))

                if self.config.debug:
                    logging.info(f"Recorded audio saved: {self.recorded_audio_path}")
                    logging.info(f"Recording duration: {elapsed:.2f}s, {len(frames)} frames")

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
        if not self.config.barge_in or not self.porcupine:
            if self.config.barge_in and not self.porcupine:
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
        # Note: barge_in_event may be None if Porcupine failed to initialize
        if self.config.barge_in and self.barge_in_event and self.barge_in_event.is_set():
            if self.config.debug:
                logging.info("Barge-in interrupt detected")
            return True
        return False

    def _run_with_barge_in_polling(self, operation, operation_name="operation"):
        """Run an operation in background thread, polling for barge-in every 100ms.

        If barge-in is detected, returns immediately without waiting for operation.
        The operation continues in background but result is discarded.

        Args:
            operation: Callable to run
            operation_name: Name for debug logging

        Returns:
            tuple: (completed: bool, result: any)
                - (True, result) if operation completed normally
                - (False, None) if interrupted by barge-in
        """
        result_holder = [None]
        error_holder = [None]

        def run_in_background():
            try:
                result_holder[0] = operation()
            except Exception as e:
                error_holder[0] = e

        thread = threading.Thread(target=run_in_background, daemon=True)
        thread.start()

        # Poll every 50ms for completion or barge-in (faster response)
        while thread.is_alive():
            if self._check_barge_in_interrupt():
                if self.config.debug:
                    logging.info(f"Barge-in during {operation_name} - responding immediately!")
                return False, None
            time.sleep(0.05)

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
            logging.info("Handling immediate barge-in response")

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

        # Reset response data
        self.response_text = None
        self.tts_files = None

        # Start barge-in detection thread (will run through PROCESSING and RESPONDING)
        barge_in_thread = self._start_barge_in_detection()

        # Check if we have a recorded audio file
        if not self.recorded_audio_path or not os.path.exists(self.recorded_audio_path):
            if self.config.debug:
                logging.warning("No recorded audio file found, returning to IDLE")
            # Clear any stale recorded audio path to avoid repeated processing attempts
            self.recorded_audio_path = None
            # Stop barge-in thread before returning
            if barge_in_thread:
                self.barge_in_stop_flag.set()
                barge_in_thread.join(timeout=1.0)
            self.state = State.IDLE
            return

        try:
            # Capture path locally to avoid race with barge-in clearing self.recorded_audio_path
            audio_path = self.recorded_audio_path

            # Transcribe the audio (with immediate barge-in response if enabled)
            if self.config.debug:
                logging.info(f"Transcribing audio from: {audio_path}")

            if self.config.barge_in and barge_in_thread:
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

            # Generate response (prefer plugin routing when available)
            # Both paths support barge-in polling for immediate interruption
            if self.route_message is not None:
                # Route through plugin system (with barge-in support if enabled)
                if self.config.barge_in and barge_in_thread:
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

                if self.config.barge_in and barge_in_thread:
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
                if self.config.barge_in and barge_in_thread:
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

            # Generate TTS if bot_voice is enabled (with immediate barge-in response if enabled)
            if self.config.bot_voice:
                # Capture response text locally to avoid race with barge-in clearing self.response_text
                response_text_for_tts = self.response_text
                if self.config.barge_in and barge_in_thread:
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
                        logging.info(f"Generated {len(self.tts_files)} TTS files")
                    else:
                        logging.warning("No TTS files generated")

            # Transition to RESPONDING state (barge-in thread continues running)
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

            frame_count = 0
            while self.running and not barge_in_event.is_set() and not stop_flag.is_set():
                try:
                    pcm = audio_stream.read(porcupine_instance.frame_length, exception_on_overflow=False)
                    pcm = struct.unpack_from("h" * porcupine_instance.frame_length, pcm)

                    keyword_index = porcupine_instance.process(pcm)
                    frame_count += 1

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
        if self.config.visual_state_indicator:
            print("🔊 Responding...")

        # Check if barge-in thread is already running from PROCESSING state
        thread_already_running = (
            self.barge_in_thread is not None and
            self.barge_in_thread.is_alive()
        )

        # Start barge-in detection thread if not already running
        if not thread_already_running:
            if self.config.barge_in and self.porcupine:
                self._start_barge_in_detection()
            elif self.config.barge_in and not self.porcupine:
                if self.config.debug:
                    logging.warning(
                        "Barge-in is enabled in configuration, but Porcupine is not initialized. "
                        "Barge-in will be disabled for this response."
                    )
        else:
            if self.config.debug:
                logging.info("Barge-in thread already running from PROCESSING, reusing it")

        # Play TTS audio if available
        if self.tts_files and len(self.tts_files) > 0:
            try:
                if self.config.debug:
                    logging.info(f"Playing {len(self.tts_files)} TTS files")

                # Play files with barge-in support via stop_event in play_audio_file()
                for idx, file_path in enumerate(self.tts_files):
                    # Play the file, passing stop_event for mid-playback interruption
                    try:
                        self.audio.play_audio_file(
                            file_path,
                            stop_event=self.barge_in_event if self.config.barge_in else None
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
                    if self.config.barge_in and self.barge_in_event and self.barge_in_event.is_set():
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
        if self.config.barge_in and self.barge_in_event and self.barge_in_event.is_set():
            if self.config.debug:
                logging.info("Transitioning to LISTENING after barge-in")

            # Skip confirmation beep after barge-in to avoid blocking responsiveness
            if self.config.wake_confirmation_beep and self.config.debug:
                logging.info(
                    "Skipping confirmation beep after barge-in to keep wake word detection responsive"
                )

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
        """Clean up Porcupine, VAD, and audio resources."""
        if self.config.debug:
            logging.info("Cleaning up wake word mode")

        if self.porcupine is not None:
            try:
                self.porcupine.delete()
            except Exception as e:
                if self.config.debug:
                    logging.warning(f"Failed to delete Porcupine instance: {e}")
            finally:
                self.porcupine = None

        self.running = False
