#import re, os, pyaudio, wave
#from pydub import AudioSegment
import contextlib
import re, os, time, threading, pyaudio, wave, lameenc, logging, queue
from pynput import keyboard
from common.error_handling import handle_file_error

logger = logging.getLogger(__name__)

# this is necessary to mute some outputs from pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

class Audio:
    def __init__(self, config):
        self.format = pyaudio.paInt16
        self.config = config
        self.audio = None
        self.initialize_audio()

    def log_mixer_state(self, context=""):
        """Log the current state of pygame.mixer.music for debugging."""
        if not logger.isEnabledFor(logging.DEBUG):
            return
        try:
            mixer_init = pygame.mixer.get_init()
            music_busy = pygame.mixer.music.get_busy() if mixer_init else None
            logger.debug(">>> MIXER STATE [%s]: thread=%s, mixer_init=%s, music_busy=%s",
                         context, threading.current_thread().name, mixer_init is not None, music_busy)
        except Exception as e:
            logger.debug(">>> MIXER STATE [%s]: Error getting state: %s", context, e)

    def init_recording(self):
        listener = keyboard.Listener(on_press=self.on_press)
        listener.start()
        self.start_recording()
        self.convert_to_mp3()

    def initialize_audio(self):
        try:
            self.audio = pyaudio.PyAudio()
        except OSError as e:
            error_msg = "Audio hardware not found. Please connect audio device."
            logger.error("Audio initialization error: %s", e)
            print(f"Error: {error_msg}")
            print("Continuing in text-only mode. Use --cli flag for better experience.")
            self.audio = None
        except Exception as e:
            error_msg = f"Failed to initialize audio: {str(e)}"
            logger.error("Audio initialization error: %s", e)
            print(f"Error: {error_msg}")
            print("Continuing in text-only mode. Use --cli flag for better experience.")
            self.audio = None

    def on_press(self, key):
        if key == keyboard.Key.esc:
            self.is_recording = False

    def start_recording(self):
        if self.audio is None:
            error_msg = "Cannot record audio - audio hardware not initialized"
            print(f"Error: {error_msg}")
            raise RuntimeError(error_msg)

        try:
            self.is_recording = True
            print(">> Listening... press ^ to stop")
            stream = self.audio.open(format=self.format, channels=self.config.channels,
                                rate=self.config.rate, input=True,
                                frames_per_buffer=self.config.chunk)
            frames = []

            while self.is_recording:
                data = stream.read(self.config.chunk)
                frames.append(data)

            stream.stop_stream()
            stream.close()
            if self.config.debug:
                print("Recording stopped.")

            wf = wave.open(self.config.tmp_recording + ".wav", 'wb')
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.config.rate)
            wf.writeframes(b''.join(frames))
            wf.close()
        except OSError as e:
            error_msg = handle_file_error(e, operation="write", filename="recording.wav")
            logger.error("Recording file error: %s", e)
            print(error_msg)
            raise
        except Exception as e:
            error_msg = f"Recording failed: {str(e)}"
            logger.error("Recording error: %s", e)
            print(f"Error: {error_msg}")
            raise

    def convert_to_mp3(self):
        try:
            #file = AudioSegment.from_wav(self.config.tmp_recording + ".wav")
            #file.export(self.config.tmp_recording + ".mp3", format="mp3")
            lame = lameenc.Encoder()
            lame.set_bit_rate(self.config.bitrate)
            lame.set_in_sample_rate(self.config.rate)
            lame.set_channels(self.config.channels)
            lame.set_quality(self.config.channels)
            with open(self.config.tmp_recording + ".wav", "rb") as wav_file, open(self.config.tmp_recording + ".mp3", "wb") as mp3_file:
                mp3_data = lame.encode(wav_file.read())
                mp3_file.write(mp3_data)
        except FileNotFoundError as e:
            error_msg = handle_file_error(e, operation="read", filename="recording.wav")
            logger.error("MP3 conversion file error: %s", e)
            print(error_msg)
            raise
        except Exception as e:
            error_msg = f"MP3 conversion failed: {str(e)}"
            logger.error("MP3 conversion error: %s", e)
            print(f"Error: {error_msg}")
            raise

    def play_audio(self):
        return self.play_audio_file(self.config.tmp_recording + ".mp3")

    def stop_playback(self, full_reset=False):
        """Stop audio playback immediately.

        This method stops pygame mixer music playback, which is used for TTS.
        Safe to call even if no audio is playing.

        Args:
            full_reset: If True, completely quit and reinitialize the mixer
                       to ensure no cached audio can play.
        """
        try:
            current_thread = threading.current_thread().name
            self.log_mixer_state("stop_playback BEFORE")
            if pygame.mixer.get_init():
                was_busy = pygame.mixer.music.get_busy()
                pygame.mixer.music.stop()
                logger.debug(">>> stop_playback called: thread=%s, was_busy=%s", current_thread, was_busy)
                if full_reset:
                    pygame.mixer.quit()
                    logger.debug(">>> pygame.mixer.quit() called for full reset")
            self.log_mixer_state("stop_playback AFTER")
        except Exception as e:
            logger.warning("Error stopping audio playback: %s", e)

    def is_playing(self):
        """Return True if pygame mixer music is currently playing."""
        try:
            if pygame.mixer.get_init():
                return bool(pygame.mixer.music.get_busy())
        except Exception:
            return False
        return False

    def play_audio_file(self, file_path, stop_event=None):
        """Play an audio file, with optional early termination via stop_event.

        Args:
            file_path: Path to the audio file to play
            stop_event: Optional threading.Event - if set, playback stops early
        """
        try:
            current_thread = threading.current_thread().name

            self.log_mixer_state(f"play_audio_file ENTER - {os.path.basename(file_path) if file_path else 'None'}")

            if not pygame.mixer.get_init():
                try:
                    pygame.mixer.init()
                except Exception as init_error:
                    logger.error("pygame mixer.init() raised an exception: %s", init_error)
                    raise

                if not pygame.mixer.get_init():
                    error_msg = "pygame mixer initialization failed: pygame.mixer.get_init() returned None after mixer.init()"
                    logger.error("%s", error_msg)
                    raise RuntimeError(error_msg)
            # Stop any currently playing audio before loading new file
            if pygame.mixer.music.get_busy():
                logger.debug(">>> STOPPING PREVIOUS AUDIO: thread=%s", current_thread)
                pygame.mixer.music.stop()
            logger.debug(">>> AUDIO PLAYBACK STARTING: thread=%s, file=%s", current_thread, file_path)
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            logger.debug(">>> AUDIO PLAYBACK play() CALLED: thread=%s", current_thread)

            while pygame.mixer.music.get_busy():
                # Check for early termination signal
                if stop_event and stop_event.is_set():
                    pygame.mixer.music.stop()
                    logger.debug(">>> Playback interrupted by stop_event: thread=%s", current_thread)
                    break
                pygame.time.Clock().tick(10)

            logger.debug(">>> play_audio_file EXIT: thread=%s, file=%s", current_thread, file_path)
        except FileNotFoundError as e:
            error_msg = handle_file_error(e, operation="read", filename=os.path.basename(file_path))
            logger.error("Audio playback file error: %s", e)
            print(error_msg)
            raise
        except Exception as e:
            error_msg = f"Audio playback failed: {str(e)}"
            logger.error("Audio playback error: %s", e)
            print(f"Error: {error_msg}")
            raise

    def play_audio_files(self, file_paths):
        """Play a list of audio files sequentially.

        Returns:
            (success, failed_file, error):
                - success: True if all files played successfully
                - failed_file: path that failed (or None)
                - error: exception instance (or None)
        """

        failed_file = None
        error = None

        for idx, file_path in enumerate(file_paths):
            delete_file = True
            try:
                self.play_audio_file(file_path)
            except Exception as e:
                failed_file = file_path
                error = e

                if self.config.debug:
                    delete_file = False

                # Always clean up remaining, unplayed chunk files to avoid leaks.
                for remaining_file in file_paths[idx + 1:]:
                    try:
                        if os.path.exists(remaining_file):
                            os.remove(remaining_file)
                    except OSError as cleanup_error:
                        # Best-effort cleanup: ignore file deletion errors.
                        logger.debug("Failed to delete remaining temporary audio chunk file '%s': %s",
                                     remaining_file, cleanup_error)
                break
            finally:
                if delete_file:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except OSError as cleanup_error:
                        # Best-effort cleanup: ignore file deletion errors.
                        logger.debug("Failed to delete temporary audio file '%s': %s",
                                     file_path, cleanup_error)

        return failed_file is None, failed_file, error

    def play_audio_queue(self, audio_queue, stop_event=None, delete_files=True, playback_lock=None):
        """Play audio files from a queue until a sentinel None is received.

        Args:
            audio_queue: queue.Queue yielding file paths (str). Use None as sentinel.
            stop_event: optional threading.Event; when set, playback stops early and the queue is drained.
            delete_files: if True, delete files after playing.
            playback_lock: optional threading.Lock (or compatible) acquired around each
                play_audio_file() call to serialize mixer usage across threads. If None,
                no external locking is applied.

        Returns:
            (success, failed_file, error)
        """
        failed_file = None
        error = None
        interrupted = False

        def _cleanup_path(path):
            if not delete_files:
                return
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError as cleanup_error:
                logger.debug("Failed to delete temporary audio file '%s': %s", path, cleanup_error)

        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    interrupted = True
                    break

                try:
                    item = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if item is None:
                    break

                delete_this_file = delete_files
                try:
                    with (playback_lock or contextlib.nullcontext()):
                        self.play_audio_file(item, stop_event=stop_event)
                except Exception as e:
                    failed_file = item
                    error = e
                    if stop_event is not None:
                        stop_event.set()
                    interrupted = True
                    if self.config.debug:
                        delete_this_file = False
                    break
                finally:
                    if delete_this_file:
                        _cleanup_path(item)

        finally:
            # Drain any queued items and delete to avoid leaks.
            # If interrupted (stop_event set or playback error), a producer may still enqueue paths
            # briefly before it notices. Drain until we see a sentinel, or until the queue has been
            # inactive for a short period.
            drain_with_inactivity_timeout = interrupted or (stop_event is not None and stop_event.is_set())
            inactivity_timeout_s = 2.0
            last_activity = time.monotonic() if drain_with_inactivity_timeout else 0.0

            while True:
                try:
                    if not drain_with_inactivity_timeout:
                        item = audio_queue.get_nowait()
                    else:
                        item = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    if not drain_with_inactivity_timeout:
                        break
                    if time.monotonic() - last_activity >= inactivity_timeout_s:
                        break
                    continue

                if drain_with_inactivity_timeout:
                    last_activity = time.monotonic()

                if item is None:
                    break
                _cleanup_path(item)

        if failed_file is None and error is None and interrupted:
            return False, None, None

        return failed_file is None, failed_file, error
