#import re, os, pyaudio, wave
#from pydub import AudioSegment
import re, os, pyaudio, wave, lameenc, logging
from pynput import keyboard
from ctypes import *
from common.error_handling import handle_file_error

# this is necessary to mute some outputs from pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

class Audio:
    def __init__(self, config):
        self.format = pyaudio.paInt16
        self.config = config
        self.audio = None
        self.initialize_audio()

    def init_recording(self):
        listener = keyboard.Listener(on_press=self.on_press)
        listener.start()
        self.start_recording()
        self.convert_to_mp3()

    def initialize_audio(self):
        try:
            if not self.config.linux_warnings:
                ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
                c_error_handler = ERROR_HANDLER_FUNC(self.py_error_handler)
                f = self.get_libasound_path()
                if f is None:
                    error_msg = "libasound library not found. Please install ALSA (libasound2) or ensure it is available in a standard library path."
                    if self.config.debug:
                        logging.error(error_msg)
                    raise RuntimeError(error_msg)
                if self.config.debug:
                    print("Loading libasound from: " + f)
                asound = cdll.LoadLibrary(f)
                asound.snd_lib_error_set_handler(c_error_handler)
            self.audio = pyaudio.PyAudio()
        except OSError as e:
            error_msg = "Audio hardware not found. Please connect audio device."
            if self.config.debug:
                logging.error(f"Audio initialization error: {e}")
            print(f"Error: {error_msg}")
            if self.config.fallback_to_text_on_audio_error:
                print("Continuing in text-only mode. Use --cli flag for better experience.")
                self.audio = None
            else:
                raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Failed to initialize audio: {str(e)}"
            if self.config.debug:
                logging.error(f"Audio initialization error: {e}")
            print(f"Error: {error_msg}")
            if self.config.fallback_to_text_on_audio_error:
                print("Continuing in text-only mode. Use --cli flag for better experience.")
                self.audio = None
            else:
                raise

    def get_libasound_path(self):
        lib_paths = [
            '/usr/lib',
            '/usr/lib64',
            '/lib',
            '/lib64',
        ]
        lib_pattern = re.compile(r'libasound\.so\..*')
        for file in lib_paths:
            if not os.path.isdir(file):
                continue
            for f in os.listdir(file):
                if lib_pattern.match(f):
                    return os.path.join(file, f)
        return None

    def py_error_handler(self, filename, line, function, err, fmt):
        pass

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
            if self.config.debug:
                logging.error(f"Recording file error: {e}")
            print(error_msg)
            raise
        except Exception as e:
            error_msg = f"Recording failed: {str(e)}"
            if self.config.debug:
                logging.error(f"Recording error: {e}")
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
            if self.config.debug:
                logging.error(f"MP3 conversion file error: {e}")
            print(error_msg)
            raise
        except Exception as e:
            error_msg = f"MP3 conversion failed: {str(e)}"
            if self.config.debug:
                logging.error(f"MP3 conversion error: {e}")
            print(f"Error: {error_msg}")
            raise

    def play_audio(self):
        return self.play_audio_file(self.config.tmp_recording + ".mp3")

    def play_audio_file(self, file_path):
        try:
            if not pygame.mixer.get_init():
                try:
                    pygame.mixer.init()
                except Exception as init_error:
                    if self.config.debug:
                        logging.error(f"pygame mixer.init() raised an exception: {init_error}")
                    raise

                if not pygame.mixer.get_init():
                    error_msg = "pygame mixer initialization failed: pygame.mixer.get_init() returned None after mixer.init()"
                    if self.config.debug:
                        logging.error(error_msg)
                    raise RuntimeError(error_msg)
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except FileNotFoundError as e:
            error_msg = handle_file_error(e, operation="read", filename=os.path.basename(file_path))
            if self.config.debug:
                logging.error(f"Audio playback file error: {e}")
            print(error_msg)
            raise
        except Exception as e:
            error_msg = f"Audio playback failed: {str(e)}"
            if self.config.debug:
                logging.error(f"Audio playback error: {e}")
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
                        if self.config.debug:
                            logging.warning(
                                f"Failed to delete remaining temporary audio chunk file '{remaining_file}': {cleanup_error}"
                            )
                break
            finally:
                if delete_file:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except OSError as cleanup_error:
                        # Best-effort cleanup: ignore file deletion errors.
                        if self.config.debug:
                            logging.warning(
                                f"Failed to delete temporary audio file '{file_path}': {cleanup_error}"
                            )

        return failed_file is None, failed_file, error
