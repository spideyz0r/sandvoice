import re, os, pyaudio, wave, lameenc
from pynput import keyboard
from ctypes import *

# this is necessary to mute some outputs from pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

class Audio:
    def __init__(self, config):
        self.format = pyaudio.paInt16
        self.config = config
        self.initialize_audio()
        listener = keyboard.Listener(on_press=self.on_press)
        listener.start()
        self.start_recording()
        self.convert_to_mp3()

    def initialize_audio(self):
        if not self.config.linux_warnings:
            ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
            c_error_handler = ERROR_HANDLER_FUNC(self.py_error_handler)
            f = self.get_libasound_path()
            if self.config.debug:
                print("Loading libasound from: " + f)
            asound = cdll.LoadLibrary(f)
            asound.snd_lib_error_set_handler(c_error_handler)
        self.audio = pyaudio.PyAudio()

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
                    return f
        return None

    def py_error_handler(self, filename, line, function, err, fmt):
        pass

    def on_press(self, key):
        if key == keyboard.Key.esc:
            self.is_recording = False

    def start_recording(self):
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
        self.audio.terminate()

    def convert_to_mp3(self):
        lame = lameenc.Encoder()
        lame.set_bit_rate(self.config.bitrate)
        lame.set_in_sample_rate(self.config.rate)
        lame.set_channels(self.config.channels)
        lame.set_quality(self.config.channels)
        with open(self.config.tmp_recording + ".wav", "rb") as wav_file, open(self.config.tmp_recording + ".mp3", "wb") as mp3_file:
            mp3_data = lame.encode(wav_file.read())
            mp3_file.write(mp3_data)

    def play_audio(self):
        pygame.mixer.init()
        pygame.mixer.music.load(self.config.tmp_recording + ".mp3")
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
