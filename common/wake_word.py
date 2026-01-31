import os
import logging
import struct
from enum import Enum

import pvporcupine
import pyaudio

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

    def __init__(self, config, ai_instance, audio_instance):
        """Initialize wake word mode.

        Args:
            config: Configuration object with wake word settings
            ai_instance: AI instance for transcription and responses
            audio_instance: Audio instance for playback
        """
        self.config = config
        self.ai = ai_instance
        self.audio = audio_instance
        self.state = State.IDLE
        self.running = False

        self.porcupine = None
        self.vad = None
        self.confirmation_beep_path = None

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
            self.porcupine = pvporcupine.create(
                access_key=self.config.porcupine_access_key,
                keywords=[self.config.wake_phrase.lower()],
                sensitivities=[self.config.wake_word_sensitivity]
            )

            if self.config.debug:
                logging.info(f"Porcupine initialized with wake phrase: '{self.config.wake_phrase}'")
                logging.info(f"Porcupine sample rate: {self.porcupine.sample_rate}")
                logging.info(f"Porcupine frame length: {self.porcupine.frame_length}")

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

    def _state_idle(self):
        """IDLE state: Listen for wake word using Porcupine.

        Listens for wake word in a blocking loop until detected.
        Plays confirmation beep and transitions to LISTENING.
        """
        if self.config.visual_state_indicator:
            print(f"⏸️  Waiting for wake word ('{self.config.wake_phrase}')...")

        pa = pyaudio.PyAudio()
        audio_stream = None

        try:
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
                audio_stream.stop_stream()
                audio_stream.close()
            pa.terminate()

    def _state_listening(self):
        """LISTENING state: Record audio with VAD until silence detected.

        Records audio frames and runs VAD to detect end of speech.
        Saves recording and transitions to PROCESSING.
        """
        if self.config.visual_state_indicator:
            print("🎤 Listening...")

        # Will be implemented in Phase 3
        self.state = State.PROCESSING

    def _state_processing(self):
        """PROCESSING state: Transcribe audio and generate response.

        Uses existing AI methods for transcription, routing, and response.
        Transitions to RESPONDING.
        """
        if self.config.visual_state_indicator:
            print("🤔 Processing...")

        # Will be implemented in Phase 4
        self.state = State.RESPONDING

    def _state_responding(self):
        """RESPONDING state: Play TTS response audio.

        Uses existing audio.play_audio_files() method.
        Transitions back to IDLE.
        """
        if self.config.visual_state_indicator:
            print("🔊 Responding...")

        # Will be implemented in Phase 4
        self.state = State.IDLE

    def _cleanup(self):
        """Clean up Porcupine, VAD, and audio resources."""
        if self.config.debug:
            logging.info("Cleaning up wake word mode")

        if self.porcupine is not None:
            self.porcupine.delete()
            self.porcupine = None

        self.running = False
